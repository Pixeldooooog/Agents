from __future__ import annotations

import hashlib
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agents.platform.sessions.file_history_types import FileHistoryBackupRef, FileHistorySnapshotState


def seed_file_history_state(
    state: FileHistorySnapshotState,
    *,
    root: Path,
    snapshots: list[FileHistorySnapshotState],
) -> None:
    latest = _latest_backups(snapshots)
    for tracking_path, (snapshot, backup) in sorted(latest.items()):
        if tracking_path in state.backups:
            continue
        try:
            state.backups[tracking_path] = _seed_backup_payload(root, state, tracking_path, backup, snapshot)
        except (OSError, UnicodeError, ValueError):
            continue


def _latest_backups(
    snapshots: list[FileHistorySnapshotState],
) -> dict[str, tuple[FileHistorySnapshotState, FileHistoryBackupRef]]:
    latest: dict[str, tuple[FileHistorySnapshotState, FileHistoryBackupRef]] = {}
    for snapshot in snapshots:
        for tracking_path, payload in snapshot.backups.items():
            backup = _backup_ref(payload)
            if backup is not None:
                latest[tracking_path] = (snapshot, backup)
    return latest


def _seed_backup_payload(
    root: Path,
    state: FileHistorySnapshotState,
    tracking_path: str,
    latest_backup: FileHistoryBackupRef,
    snapshot: FileHistorySnapshotState,
) -> dict[str, Any]:
    target = _safe_workspace_path(root, tracking_path)
    next_version = max(1, int(latest_backup.version or 0) + 1)
    if not target.exists():
        return _backup_payload_base(next_version)
    if not target.is_file():
        raise ValueError("file history path is not a file: %s" % tracking_path)
    if latest_backup.exists:
        backup_path = _resolve_backup_path(latest_backup, snapshot)
        if backup_path is not None and backup_path.exists() and backup_path.is_file():
            current_bytes = target.read_bytes()
            if current_bytes == backup_path.read_bytes():
                return dict(latest_backup.payload)
    return _backup_current_file_payload(state, target, next_version)


def _backup_current_file_payload(state: FileHistorySnapshotState, target: Path, version: int) -> dict[str, Any]:
    payload = _backup_payload_base(version)
    backup_name = _backup_name(target, version)
    state.backup_root.mkdir(parents=True, exist_ok=True)
    shutil.copy2(target, state.backup_root / backup_name)
    payload["backupFileName"] = backup_name
    return payload


def _backup_payload_base(version: int) -> dict[str, Any]:
    return {
        "backupFileName": None,
        "version": max(1, int(version or 1)),
        "backupTime": datetime.now(timezone.utc).isoformat(),
    }


def _backup_ref(value: Any) -> FileHistoryBackupRef | None:
    if not isinstance(value, dict):
        return None
    payload = dict(value)
    has_backup_name = "backupFileName" in payload or "backup_file_name" in payload
    backup_name = payload.get("backupFileName") if "backupFileName" in payload else payload.get("backup_file_name")
    backup_path = str(payload.get("backupPath") or payload.get("backup_path") or "")
    version = _int_value(payload.get("version"))
    if backup_name is None and has_backup_name:
        return FileHistoryBackupRef(payload=payload, exists=False, version=version)
    if isinstance(backup_name, str) and backup_name:
        return FileHistoryBackupRef(
            payload=payload,
            exists=True,
            backup_file_name=backup_name,
            backup_path=backup_path,
            version=version,
        )
    if backup_path:
        return FileHistoryBackupRef(payload=payload, exists=True, backup_path=backup_path, version=version)
    return None


def _resolve_backup_path(backup: FileHistoryBackupRef, snapshot: FileHistorySnapshotState) -> Path | None:
    if backup.backup_path:
        path = Path(backup.backup_path).expanduser()
        return path if path.is_absolute() else path.resolve()
    name = str(backup.backup_file_name or "")
    if not name or Path(name).is_absolute() or "/" in name or "\\" in name or name.startswith(".."):
        return None
    return snapshot.backup_root / name


def _safe_workspace_path(root: Path, path: str) -> Path:
    target = Path(path)
    resolved = target.resolve() if target.is_absolute() else (root / target).resolve()
    resolved.relative_to(root)
    return resolved


def _backup_name(path: Path, version: int) -> str:
    digest = hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:16]
    return "%s@v%d" % (digest, max(1, int(version or 1)))


def _int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
