from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from agents.kernel.schema import RuntimeEvent
from agents.kernel.state.runs import RunRecord
from agents.sdk.file_history_types import _FileHistoryBackupRef, _FileHistorySnapshot
from agents.sdk.file_rewind import _rewind_path_value


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
    backup_name = value.get("backupFileName") if "backupFileName" in value else value.get("backup_file_name")
    backup_path = str(value.get("backupPath") or value.get("backup_path") or "")
    backup_time = value.get("backupTime") if "backupTime" in value else value.get("backup_time")
    if backup_name is None and has_backup_name:
        return _FileHistoryBackupRef(exists=False, version=_int_value(value.get("version")), backup_time=backup_time)
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


def _int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
