from __future__ import annotations

from pathlib import Path

from agents.kernel.capabilities.sandbox.text import (
    BINARY_SAMPLE_BYTES,
    decode_text_bytes,
    detect_text_encoding,
)
from agents.kernel.state.runs import RunRecord
from agents.sdk.file_history_paths import _resolve_file_history_backup_path
from agents.sdk.file_history_snapshots import (
    _file_history_snapshots_from_records,
    _first_file_history_backup,
    _last_file_history_snapshot_for_message,
)
from agents.sdk.file_history_types import _FileHistoryBackupRef, _FileHistorySnapshot
from agents.sdk.file_rewind import _RewindFileEntry, _safe_rewind_path, _text_change_stats
from agents.sdk.types import SDKOptions


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
