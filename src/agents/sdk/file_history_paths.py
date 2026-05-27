from __future__ import annotations

import hashlib
import os
from collections.abc import Iterable
from pathlib import Path

from agents.kernel.state.runs import RunRecord
from agents.sdk.file_history_types import _FileHistoryBackupRef, _FileHistorySnapshot
from agents.sdk.types import SDKOptions


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
