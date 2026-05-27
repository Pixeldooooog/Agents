from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from agents.kernel.schema import RuntimeEvent
from agents.kernel.state.runs import RunRecord
from agents.sdk.file_history_paths import _resolve_file_history_backup_path
from agents.sdk.file_history_snapshots import _file_history_snapshot_from_payload, _file_history_snapshot_payload
from agents.sdk.file_history_types import _FileHistorySnapshot
from agents.sdk.file_rewind import _event_matches_message_id
from agents.sdk.types import SDKOptions


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
