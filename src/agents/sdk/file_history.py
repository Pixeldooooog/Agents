from __future__ import annotations

import hashlib
import os
import shutil
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agents.kernel.capabilities.sandbox.text import (
    BINARY_SAMPLE_BYTES,
    decode_text_bytes,
    detect_text_encoding,
)
from agents.kernel.schema import RuntimeEvent
from agents.kernel.state.runs import RunRecord
from agents.sdk.file_rewind import (
    _RewindFileEntry,
    _event_matches_message_id,
    _read_content_from_tool_result,
    _rewind_entries_from_tool_result,
    _rewind_path_value,
    _rewind_tool_result_payload_data,
    _safe_rewind_path,
    _text_change_stats,
)
from agents.sdk.types import SDKOptions


@dataclass
class _FileHistoryBackupRef:
    exists: bool
    backup_file_name: str = ""
    backup_path: str = ""
    version: int = 0
    backup_time: Any = None


@dataclass
class _FileHistorySnapshot:
    message_id: str
    backups: dict[str, _FileHistoryBackupRef] = field(default_factory=dict)
    backup_root: str = ""
    history_session_id: str = ""


@dataclass
class _SDKReadStateSeed:
    path: str
    content: str
    timestamp: float
    encoding: str = "utf-8"


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


def _file_history_backup_name(path: Path, version: int) -> str:
    digest = hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:16]
    return "%s@v%d" % (digest, max(1, int(version or 1)))


def _next_file_history_backup_version(backup_root: Path, path: Path) -> int:
    digest = hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:16]
    highest = 0
    if backup_root.exists():
        for candidate in backup_root.glob("%s@v*" % digest):
            suffix = candidate.name.rsplit("@v", 1)[-1]
            try:
                highest = max(highest, int(suffix))
            except ValueError:
                continue
    return highest + 1



def _events_for_fork(events: list[RuntimeEvent], up_to_message_id: str = "") -> tuple[list[RuntimeEvent], bool]:
    if not up_to_message_id:
        return list(events), False
    copied: list[RuntimeEvent] = []
    for event in events:
        copied.append(event)
        if _event_matches_message_id(event, up_to_message_id):
            return copied, True
    return copied, False


def _migrate_file_history_events_for_session(
    events: list[RuntimeEvent],
    *,
    records: list[RunRecord],
    source_session_id: str,
    target_session_id: str,
) -> list[RuntimeEvent]:
    migrated: list[RuntimeEvent] = []
    if source_session_id == target_session_id:
        return list(events)
    snapshot_record = records[-1] if records else RunRecord(run_id=source_session_id)
    source_options = SDKOptions(session_id=source_session_id)
    for event in events:
        payload = _file_history_snapshot_payload(event)
        snapshot = _file_history_snapshot_from_payload(payload, snapshot_record) if payload else None
        if payload is None or snapshot is None:
            migrated.append(event)
            continue
        target_root = _copy_file_history_snapshot_backups(
            snapshot,
            source_options=source_options,
            records=records,
            target_session_id=target_session_id,
        )
        if target_root is None:
            migrated.append(event)
            continue
        migrated.append(_with_migrated_file_history_payload(event, payload, target_session_id, target_root))
    return migrated


def _copy_file_history_snapshot_backups(
    snapshot: _FileHistorySnapshot,
    *,
    source_options: SDKOptions,
    records: list[RunRecord],
    target_session_id: str,
) -> Path | None:
    target_root = _file_history_migration_target_root(snapshot, target_session_id)
    try:
        target_root.mkdir(parents=True, exist_ok=True)
        for backup in snapshot.backups.values():
            if not backup.exists:
                continue
            source = _resolve_file_history_backup_path(backup, snapshot, source_options, records)
            if source is None or not source.exists() or not source.is_file():
                return None
            target_name = backup.backup_file_name or source.name
            target = target_root / target_name
            _link_or_copy_file_history_backup(source, target)
    except OSError:
        return None
    return target_root


def _file_history_migration_target_root(snapshot: _FileHistorySnapshot, target_session_id: str) -> Path:
    if snapshot.backup_root:
        return Path(snapshot.backup_root).expanduser().resolve().parent / target_session_id
    config_dir = Path(os.environ.get("CLAUDE_CONFIG_DIR", "") or Path.home() / ".claude").expanduser().resolve()
    return config_dir / "file-history" / target_session_id


def _link_or_copy_file_history_backup(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        return
    try:
        os.link(source, target)
    except FileExistsError:
        return
    except OSError:
        shutil.copy2(source, target)


def _with_migrated_file_history_payload(
    event: RuntimeEvent,
    payload: dict[str, Any],
    target_session_id: str,
    target_root: Path,
) -> RuntimeEvent:
    migrated_payload = _migrated_file_history_payload(payload, target_session_id, target_root)
    migrated_raw = event.raw
    if isinstance(event.raw, dict):
        migrated_raw = _migrated_file_history_payload(event.raw, target_session_id, target_root)
    return RuntimeEvent(type=event.type, name=event.name, payload=migrated_payload, raw=migrated_raw)


def _migrated_file_history_payload(
    payload: dict[str, Any],
    target_session_id: str,
    target_root: Path,
) -> dict[str, Any]:
    migrated = dict(payload)
    migrated["sessionId"] = target_session_id
    migrated["backupRoot"] = str(target_root)
    snapshot_payload = migrated.get("snapshot")
    if isinstance(snapshot_payload, dict):
        snapshot_copy = dict(snapshot_payload)
        snapshot_copy["sessionId"] = target_session_id
        snapshot_copy["backupRoot"] = str(target_root)
        migrated["snapshot"] = snapshot_copy
    return migrated


def _rewind_entries_from_file_history_snapshots(
    records: list[RunRecord],
    message_id: str,
    root: Path,
    options: SDKOptions,
) -> tuple[list[_RewindFileEntry], list[str], bool]:
    snapshots = _file_history_snapshots_from_records(records)
    target_snapshot = _last_file_history_snapshot_for_message(snapshots, message_id)
    if target_snapshot is None:
        return [], [], False

    entries: list[_RewindFileEntry] = []
    unsupported_paths: set[str] = set()
    tracked_paths = sorted({path for snapshot in snapshots for path in snapshot.backups})
    for tracking_path in tracked_paths:
        backup = target_snapshot.backups.get(tracking_path) or _first_file_history_backup(tracking_path, snapshots)
        if backup is None:
            continue
        try:
            entry = _rewind_entry_from_file_history_backup(
                tracking_path,
                backup,
                target_snapshot,
                root,
                options,
                records,
            )
        except (OSError, UnicodeError, ValueError):
            unsupported_paths.add(tracking_path)
            continue
        if entry is not None:
            entries.append(entry)
    return entries, sorted(unsupported_paths), True


def _file_history_snapshots_from_records(records: list[RunRecord]) -> list[_FileHistorySnapshot]:
    snapshots: list[_FileHistorySnapshot] = []
    index_by_message_id: dict[str, int] = {}
    for record in sorted(records, key=lambda item: item.created_at):
        for event in record.events:
            payload = _file_history_snapshot_payload(event)
            if payload is None:
                continue
            snapshot = _file_history_snapshot_from_payload(payload, record)
            if snapshot is None:
                continue
            is_update = bool(payload.get("isSnapshotUpdate") or payload.get("is_snapshot_update"))
            existing_index = index_by_message_id.get(snapshot.message_id) if is_update else None
            if existing_index is None:
                index_by_message_id[snapshot.message_id] = len(snapshots)
                snapshots.append(snapshot)
            else:
                snapshots[existing_index] = snapshot
    return snapshots


def _file_history_snapshot_payload(event: RuntimeEvent) -> dict[str, Any] | None:
    candidates = [event.payload, event.raw]
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        if candidate.get("type") == "file-history-snapshot" and isinstance(candidate.get("snapshot"), dict):
            return dict(candidate)
        raw = candidate.get("raw")
        if isinstance(raw, dict) and raw.get("type") == "file-history-snapshot":
            return dict(raw)
    if event.type == "file-history-snapshot" and isinstance(event.payload.get("snapshot"), dict):
        payload = dict(event.payload)
        payload.setdefault("type", "file-history-snapshot")
        return payload
    return None


def _file_history_snapshot_from_payload(
    payload: dict[str, Any],
    record: RunRecord,
) -> _FileHistorySnapshot | None:
    snapshot_payload = payload.get("snapshot")
    if not isinstance(snapshot_payload, dict):
        return None
    message_id = str(snapshot_payload.get("messageId") or snapshot_payload.get("message_id") or payload.get("messageId") or payload.get("message_id") or "")
    if not message_id:
        return None
    backup_payload = snapshot_payload.get("trackedFileBackups")
    if not isinstance(backup_payload, dict):
        backup_payload = snapshot_payload.get("tracked_file_backups")
    if not isinstance(backup_payload, dict):
        return None
    backups: dict[str, _FileHistoryBackupRef] = {}
    for path, backup in backup_payload.items():
        ref = _file_history_backup_ref(backup)
        if ref is not None:
            backups[_rewind_path_value(path)] = ref
    return _FileHistorySnapshot(
        message_id=message_id,
        backups=backups,
        backup_root=str(
            payload.get("backupRoot")
            or payload.get("backup_root")
            or snapshot_payload.get("backupRoot")
            or snapshot_payload.get("backup_root")
            or ""
        ),
        history_session_id=str(
            payload.get("sessionId")
            or payload.get("session_id")
            or snapshot_payload.get("sessionId")
            or snapshot_payload.get("session_id")
            or record.metadata.get("sdk_file_history_session_id")
            or ""
        ),
    )


def _file_history_backup_ref(value: Any) -> _FileHistoryBackupRef | None:
    if not isinstance(value, dict):
        return None
    has_backup_name = "backupFileName" in value or "backup_file_name" in value
    backup_name = (
        value.get("backupFileName")
        if "backupFileName" in value
        else value.get("backup_file_name")
    )
    backup_path = str(value.get("backupPath") or value.get("backup_path") or "")
    backup_time = value.get("backupTime") if "backupTime" in value else value.get("backup_time")
    if backup_name is None and has_backup_name:
        return _FileHistoryBackupRef(
            exists=False,
            version=_int_value(value.get("version")),
            backup_time=backup_time,
        )
    if isinstance(backup_name, str) and backup_name:
        return _FileHistoryBackupRef(
            exists=True,
            backup_file_name=backup_name,
            backup_path=backup_path,
            version=_int_value(value.get("version")),
            backup_time=backup_time,
        )
    if backup_path:
        return _FileHistoryBackupRef(
            exists=True,
            backup_path=backup_path,
            version=_int_value(value.get("version")),
            backup_time=backup_time,
        )
    return None


def _file_history_backup_payload_from_ref(ref: _FileHistoryBackupRef) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "version": max(1, int(ref.version or 1)),
        "backupTime": str(ref.backup_time or datetime.now(timezone.utc).isoformat()),
    }
    if not ref.exists:
        payload["backupFileName"] = None
    elif ref.backup_file_name:
        payload["backupFileName"] = ref.backup_file_name
    elif ref.backup_path:
        payload["backupPath"] = ref.backup_path
    else:
        payload["backupFileName"] = None
    return payload


def _last_file_history_snapshot_for_message(
    snapshots: list[_FileHistorySnapshot],
    message_id: str,
) -> _FileHistorySnapshot | None:
    for snapshot in reversed(snapshots):
        if snapshot.message_id == message_id:
            return snapshot
    return None


def _first_file_history_backup(
    tracking_path: str,
    snapshots: list[_FileHistorySnapshot],
) -> _FileHistoryBackupRef | None:
    fallback: _FileHistoryBackupRef | None = None
    for snapshot in snapshots:
        backup = snapshot.backups.get(tracking_path)
        if backup is None:
            continue
        if fallback is None:
            fallback = backup
        if backup.version == 1:
            return backup
    return fallback


def _latest_file_history_backup(
    tracking_path: str,
    snapshots: list[_FileHistorySnapshot],
) -> tuple[_FileHistorySnapshot, _FileHistoryBackupRef] | None:
    for snapshot in reversed(snapshots):
        backup = snapshot.backups.get(tracking_path)
        if backup is not None:
            return snapshot, backup
    return None


def _rewind_entry_from_file_history_backup(
    tracking_path: str,
    backup: _FileHistoryBackupRef,
    snapshot: _FileHistorySnapshot,
    root: Path,
    options: SDKOptions,
    records: list[RunRecord],
) -> _RewindFileEntry | None:
    target = _safe_rewind_path(root, tracking_path)
    current_bytes = _read_rewind_target_bytes(target)
    if not backup.exists:
        if current_bytes is None:
            return None
        insertions, deletions = _rewind_bytes_change_stats(target, current_bytes, None, b"")
        return _RewindFileEntry(
            path=tracking_path,
            before="",
            before_bytes=None,
            existed=False,
            insertions=insertions,
            deletions=deletions,
        )

    backup_path = _resolve_file_history_backup_path(backup, snapshot, options, records)
    if backup_path is None or not backup_path.exists() or not backup_path.is_file():
        raise FileNotFoundError("file history backup not found: %s" % tracking_path)
    backup_bytes = backup_path.read_bytes()
    if current_bytes == backup_bytes:
        return None
    insertions, deletions = _rewind_bytes_change_stats(target, current_bytes, backup_path, backup_bytes)
    backup_text = _decode_rewind_bytes(backup_path, backup_bytes)
    return _RewindFileEntry(
        path=tracking_path,
        before=backup_text,
        before_bytes=backup_bytes,
        existed=True,
        encoding="utf-8",
        insertions=insertions,
        deletions=deletions,
        mode=backup_path.stat().st_mode,
    )


def _read_rewind_target_bytes(target: Path) -> bytes | None:
    if not target.exists():
        return None
    if not target.is_file():
        raise ValueError("rewind path is not a file: %s" % target)
    return target.read_bytes()


def _resolve_file_history_backup_path(
    backup: _FileHistoryBackupRef,
    snapshot: _FileHistorySnapshot,
    options: SDKOptions,
    records: list[RunRecord],
) -> Path | None:
    if backup.backup_path:
        path = Path(backup.backup_path).expanduser()
        return path if path.is_absolute() else path.resolve()
    name = str(backup.backup_file_name or "")
    if not name or Path(name).is_absolute() or "/" in name or "\\" in name or name.startswith(".."):
        return None
    for root in _file_history_backup_roots(snapshot, options, records):
        candidate = root / name
        if candidate.exists():
            return candidate
    roots = _file_history_backup_roots(snapshot, options, records)
    return (roots[0] / name) if roots else None


def _file_history_backup_roots(
    snapshot: _FileHistorySnapshot,
    options: SDKOptions,
    records: list[RunRecord],
) -> list[Path]:
    metadata = dict(options.metadata or {})
    direct_roots = [
        snapshot.backup_root,
        str(metadata.get("file_history_root") or metadata.get("fileHistoryRoot") or ""),
    ]
    roots: list[Path] = []
    for value in direct_roots:
        if value:
            roots.append(Path(value).expanduser().resolve())

    config_values = [
        str(metadata.get("claude_config_dir") or metadata.get("claudeConfigDir") or ""),
        os.environ.get("CLAUDE_CONFIG_DIR", ""),
        str(Path.home() / ".claude"),
    ]
    session_ids = _file_history_session_ids(snapshot, options, records)
    for config_value in config_values:
        if not config_value:
            continue
        config_dir = Path(config_value).expanduser().resolve()
        for session_id in session_ids:
            roots.append(config_dir / "file-history" / session_id)
    return _unique_paths(roots)


def _file_history_session_ids(
    snapshot: _FileHistorySnapshot,
    options: SDKOptions,
    records: list[RunRecord],
) -> list[str]:
    metadata = dict(options.metadata or {})
    values = [
        snapshot.history_session_id,
        str(metadata.get("file_history_session_id") or metadata.get("fileHistorySessionId") or ""),
        str(options.session_id or ""),
    ]
    values.extend(str(record.metadata.get("sdk_session_id") or record.run_id or "") for record in records)
    return _unique_strings(values)


def _unique_paths(paths: Iterable[Path]) -> list[Path]:
    seen: set[str] = set()
    unique: list[Path] = []
    for path in paths:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def _unique_strings(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        item = str(value or "").strip()
        if not item or item in seen:
            continue
        seen.add(item)
        unique.append(item)
    return unique


def _rewind_bytes_change_stats(
    current_path: Path,
    current_bytes: bytes | None,
    backup_path: Path | None,
    backup_bytes: bytes,
) -> tuple[int, int]:
    try:
        current_text = _decode_rewind_bytes(current_path, current_bytes or b"")
        backup_text = _decode_rewind_bytes(backup_path or current_path, backup_bytes)
    except UnicodeError:
        return 0, 0
    return _text_change_stats(current_text, backup_text)


def _decode_rewind_bytes(path: Path, data: bytes) -> str:
    encoding = detect_text_encoding(path, data[:BINARY_SAMPLE_BYTES])
    return decode_text_bytes(data, encoding)


def _int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
