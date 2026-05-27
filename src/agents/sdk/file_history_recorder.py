from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agents.kernel.schema import RuntimeEvent
from agents.kernel.state.runs import RunRecord
from agents.sdk.file_history_paths import (
    _file_history_backup_name,
    _next_file_history_backup_version,
    _resolve_file_history_backup_path,
)
from agents.sdk.file_history_snapshots import (
    _file_history_backup_payload_from_ref,
    _file_history_snapshots_from_records,
    _latest_file_history_backup,
)
from agents.sdk.file_history_types import _FileHistoryBackupRef, _FileHistorySnapshot
from agents.sdk.file_rewind import (
    _RewindFileEntry,
    _read_content_from_tool_result,
    _rewind_entries_from_tool_result,
    _rewind_tool_result_payload_data,
    _safe_rewind_path,
)
from agents.sdk.types import SDKOptions


@dataclass
class _SDKFileHistoryRecorder:
    root: Path
    config_dir: Path
    session_id: str
    message_id: str
    backups: dict[str, dict[str, Any]] = field(default_factory=dict)
    read_cache: dict[str, str] = field(default_factory=dict)

    @property
    def backup_root(self) -> Path:
        return self.config_dir / "file-history" / self.session_id

    def initial_event(self) -> RuntimeEvent:
        return self._snapshot_event(is_update=False)

    def seed_from_previous(self, records: list[RunRecord], options: SDKOptions) -> None:
        snapshots = _file_history_snapshots_from_records(records)
        tracked_paths = sorted({path for snapshot in snapshots for path in snapshot.backups})
        for tracking_path in tracked_paths:
            latest = _latest_file_history_backup(tracking_path, snapshots)
            if latest is None:
                continue
            snapshot, backup = latest
            try:
                self.backups[tracking_path] = self._seed_backup_payload(
                    tracking_path,
                    backup,
                    snapshot,
                    options,
                    records,
                )
            except (OSError, UnicodeError, ValueError):
                continue

    def observe(self, event: RuntimeEvent) -> list[RuntimeEvent]:
        if event.type != "tool_result":
            return []
        payload = _rewind_tool_result_payload_data(event.payload)
        read_path, read_content = _read_content_from_tool_result(event, payload)
        if read_path:
            self.read_cache[read_path] = read_content
            return []
        entries, _ = _rewind_entries_from_tool_result(event, payload, self.read_cache)
        changed = False
        for entry in entries:
            if entry.path in self.backups:
                continue
            try:
                self.backups[entry.path] = self._backup_payload(entry)
            except (OSError, UnicodeError, ValueError):
                continue
            changed = True
        return [self._snapshot_event(is_update=True)] if changed else []

    def _backup_payload(self, entry: _RewindFileEntry) -> dict[str, Any]:
        backup = self._backup_payload_base(1)
        target = _safe_rewind_path(self.root, entry.path)
        if not entry.existed:
            return backup
        version = _next_file_history_backup_version(self.backup_root, target)
        backup_name = _file_history_backup_name(target, version)
        self.backup_root.mkdir(parents=True, exist_ok=True)
        backup_path = self.backup_root / backup_name
        data = entry.before_bytes
        if data is None:
            data = entry.before.encode(entry.encoding or "utf-8")
        backup_path.write_bytes(data)
        if entry.mode is not None:
            os.chmod(backup_path, entry.mode)
        elif target.exists() and target.is_file():
            os.chmod(backup_path, target.stat().st_mode)
        backup["backupFileName"] = backup_name
        backup["version"] = version
        return backup

    def _seed_backup_payload(
        self,
        tracking_path: str,
        latest_backup: _FileHistoryBackupRef,
        snapshot: _FileHistorySnapshot,
        options: SDKOptions,
        records: list[RunRecord],
    ) -> dict[str, Any]:
        target = _safe_rewind_path(self.root, tracking_path)
        next_version = max(1, int(latest_backup.version or 0) + 1)
        if not target.exists():
            return self._backup_payload_base(next_version)
        if not target.is_file():
            raise ValueError("file history path is not a file: %s" % tracking_path)
        if latest_backup.exists:
            backup_path = _resolve_file_history_backup_path(latest_backup, snapshot, options, records)
            if backup_path is not None and backup_path.exists() and backup_path.is_file():
                current_bytes = target.read_bytes()
                if current_bytes == backup_path.read_bytes():
                    return _file_history_backup_payload_from_ref(latest_backup)
        return self._backup_current_file_payload(target, next_version)

    def _backup_current_file_payload(self, target: Path, version: int) -> dict[str, Any]:
        backup = self._backup_payload_base(version)
        backup_name = _file_history_backup_name(target, version)
        self.backup_root.mkdir(parents=True, exist_ok=True)
        backup_path = self.backup_root / backup_name
        shutil.copy2(target, backup_path)
        os.chmod(backup_path, target.stat().st_mode)
        backup["backupFileName"] = backup_name
        return backup

    def _backup_payload_base(self, version: int) -> dict[str, Any]:
        return {
            "backupFileName": None,
            "version": max(1, int(version or 1)),
            "backupTime": datetime.now(timezone.utc).isoformat(),
        }

    def _snapshot_event(self, *, is_update: bool) -> RuntimeEvent:
        timestamp = datetime.now(timezone.utc).isoformat()
        payload = {
            "type": "file-history-snapshot",
            "messageId": self.message_id,
            "sessionId": self.session_id,
            "backupRoot": str(self.backup_root),
            "snapshot": {
                "messageId": self.message_id,
                "trackedFileBackups": dict(self.backups),
                "timestamp": timestamp,
            },
            "isSnapshotUpdate": is_update,
        }
        return RuntimeEvent(type="file-history-snapshot", name="file-history", payload=payload)


def _sdk_file_history_recorder(
    options: SDKOptions,
    *,
    root: Path,
    session_id: str,
    message_id: str,
    records: list[RunRecord] | None = None,
) -> _SDKFileHistoryRecorder | None:
    if not _sdk_file_history_enabled(options) or not message_id:
        return None
    config_dir = _sdk_claude_config_dir(options)
    if config_dir is None:
        return None
    recorder = _SDKFileHistoryRecorder(
        root=root,
        config_dir=config_dir,
        session_id=session_id,
        message_id=message_id,
    )
    recorder.seed_from_previous(list(records or []), options)
    return recorder


def _sdk_file_history_enabled(options: SDKOptions) -> bool:
    metadata = dict(options.metadata or {})
    for key in ("file_history_enabled", "fileHistoryEnabled", "fileCheckpointingEnabled"):
        if key in metadata:
            return _truthy_metadata_value(metadata[key])
    return True


def _sdk_claude_config_dir(options: SDKOptions) -> Path | None:
    metadata = dict(options.metadata or {})
    value = str(
        metadata.get("claude_config_dir")
        or metadata.get("claudeConfigDir")
        or os.environ.get("CLAUDE_CONFIG_DIR", "")
        or ""
    )
    if not value:
        value = str(Path.home() / ".claude")
    return Path(value).expanduser().resolve()


def _truthy_metadata_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() not in {"", "0", "false", "no", "off"}
