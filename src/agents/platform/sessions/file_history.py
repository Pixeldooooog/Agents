from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agents.kernel.schema import RuntimeEvent
from agents.kernel.state.runs import RunRecord
from agents.platform.sessions.file_history_payloads import (
    FileHistoryEntry,
    entries_from_tool_result,
    path_value,
)


@dataclass(frozen=True)
class FileHistoryBackup:
    backup: dict[str, Any]


@dataclass
class FileHistorySnapshotState:
    message_id: str
    session_id: str
    backup_root: Path
    backups: dict[str, dict[str, Any]] = field(default_factory=dict)


def file_history_events_before_record(record: RunRecord | None, event: RuntimeEvent) -> list[RuntimeEvent]:
    if record is None or not _should_track_run(record):
        return []
    if not _is_file_history_trigger(event) or _latest_snapshot(record) is not None:
        return []
    state = _initial_state(record)
    if state is None:
        return []
    return [_snapshot_event(state, is_update=False)]


def file_history_events_after_record(record: RunRecord | None, event: RuntimeEvent) -> list[RuntimeEvent]:
    if record is None or not _should_track_run(record) or event.type != "tool_result":
        return []
    state = _latest_snapshot(record)
    if state is None:
        state = _initial_state(record)
    if state is None:
        return []
    changed = False
    for entry in entries_from_tool_result(event):
        if entry.path in state.backups:
            continue
        try:
            backup = _backup_entry(record, state, entry)
        except (OSError, UnicodeError, ValueError, LookupError):
            continue
        if backup is None:
            continue
        state.backups[entry.path] = backup.backup
        changed = True
    return [_snapshot_event(state, is_update=True)] if changed else []


def is_persisted_file_history_event(event: RuntimeEvent) -> bool:
    return event.type == "file-history-snapshot"


def _should_track_run(record: RunRecord) -> bool:
    metadata = dict(record.metadata or {})
    if metadata.get("sdk_session_id") or metadata.get("sdk_file_history_session_id"):
        return False
    for key in ("file_history_enabled", "fileHistoryEnabled", "fileCheckpointingEnabled"):
        if key in metadata:
            return _truthy(metadata[key])
    return True


def _is_file_history_trigger(event: RuntimeEvent) -> bool:
    return event.type == "file_history_write" or bool(entries_from_tool_result(event))


def _initial_state(record: RunRecord) -> FileHistorySnapshotState | None:
    root = _workspace_root(record)
    if root is None:
        return None
    session_id = _metadata_value(record, "file_history_session_id", "fileHistorySessionId") or record.run_id
    message_id = _metadata_value(record, "file_history_message_id", "fileHistoryMessageId") or record.run_id
    return FileHistorySnapshotState(
        message_id=message_id,
        session_id=session_id,
        backup_root=_config_dir(record) / "file-history" / session_id,
    )


def _latest_snapshot(record: RunRecord) -> FileHistorySnapshotState | None:
    latest: FileHistorySnapshotState | None = None
    for event in record.events:
        payload = _snapshot_payload(event)
        if payload is None:
            continue
        state = _snapshot_state_from_payload(record, payload)
        if state is not None:
            latest = state
    return latest


def _snapshot_state_from_payload(record: RunRecord, payload: dict[str, Any]) -> FileHistorySnapshotState | None:
    snapshot = payload.get("snapshot") if isinstance(payload.get("snapshot"), dict) else {}
    message_id = str(snapshot.get("messageId") or payload.get("messageId") or "")
    if not message_id:
        return None
    backup_root = str(payload.get("backupRoot") or snapshot.get("backupRoot") or "")
    if not backup_root:
        initial = _initial_state(record)
        backup_root = str(initial.backup_root) if initial is not None else ""
    tracked = snapshot.get("trackedFileBackups")
    backups = dict(tracked) if isinstance(tracked, dict) else {}
    return FileHistorySnapshotState(
        message_id=message_id,
        session_id=str(payload.get("sessionId") or snapshot.get("sessionId") or record.run_id),
        backup_root=Path(backup_root).expanduser().resolve(),
        backups={path_value(path): dict(backup) for path, backup in backups.items() if isinstance(backup, dict)},
    )


def _snapshot_payload(event: RuntimeEvent) -> dict[str, Any] | None:
    if event.type != "file-history-snapshot":
        return None
    payload = event.payload if isinstance(event.payload, dict) else {}
    snapshot = payload.get("snapshot")
    return dict(payload) if isinstance(snapshot, dict) else None


def _snapshot_event(state: FileHistorySnapshotState, *, is_update: bool) -> RuntimeEvent:
    timestamp = datetime.now(timezone.utc).isoformat()
    payload = {
        "type": "file-history-snapshot",
        "messageId": state.message_id,
        "sessionId": state.session_id,
        "backupRoot": str(state.backup_root),
        "snapshot": {
            "messageId": state.message_id,
            "sessionId": state.session_id,
            "backupRoot": str(state.backup_root),
            "trackedFileBackups": dict(state.backups),
            "timestamp": timestamp,
        },
        "isSnapshotUpdate": is_update,
    }
    return RuntimeEvent(type="file-history-snapshot", name="file-history", payload=payload)


def _backup_entry(record: RunRecord, state: FileHistorySnapshotState, entry: FileHistoryEntry) -> FileHistoryBackup | None:
    root = _workspace_root(record)
    if root is None:
        return None
    try:
        target = _safe_workspace_path(root, entry.path)
    except ValueError:
        return None
    version = _next_backup_version(state.backup_root, target)
    payload: dict[str, Any] = {
        "backupFileName": None,
        "version": version,
        "backupTime": datetime.now(timezone.utc).isoformat(),
    }
    if not entry.existed:
        return FileHistoryBackup(payload)
    backup_name = _backup_name(target, version)
    state.backup_root.mkdir(parents=True, exist_ok=True)
    (state.backup_root / backup_name).write_bytes(entry.before.encode(entry.encoding or "utf-8"))
    payload["backupFileName"] = backup_name
    return FileHistoryBackup(payload)


def _workspace_root(record: RunRecord) -> Path | None:
    workspace = record.spec.get("workspace") if isinstance(record.spec.get("workspace"), dict) else {}
    root = str(workspace.get("path") or workspace.get("root") or "")
    return Path(root).expanduser().resolve() if root else None


def _config_dir(record: RunRecord) -> Path:
    value = _metadata_value(record, "claude_config_dir", "claudeConfigDir") or os.environ.get("CLAUDE_CONFIG_DIR", "")
    return Path(value or Path.home() / ".claude").expanduser().resolve()


def _metadata_value(record: RunRecord, *keys: str) -> str:
    metadata = record.metadata or {}
    for key in keys:
        value = str(metadata.get(key) or "")
        if value:
            return value
    return ""


def _backup_name(path: Path, version: int) -> str:
    digest = hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:16]
    return "%s@v%d" % (digest, max(1, int(version or 1)))


def _next_backup_version(backup_root: Path, path: Path) -> int:
    digest = hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:16]
    highest = 0
    if backup_root.exists():
        for candidate in backup_root.glob("%s@v*" % digest):
            try:
                highest = max(highest, int(candidate.name.rsplit("@v", 1)[-1]))
            except ValueError:
                continue
    return highest + 1


def _safe_workspace_path(root: Path, path: str) -> Path:
    target = Path(path)
    resolved = target.resolve() if target.is_absolute() else (root / target).resolve()
    resolved.relative_to(root)
    return resolved


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() not in {"", "0", "false", "no", "off"}
