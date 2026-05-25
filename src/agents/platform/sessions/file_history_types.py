from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class FileHistoryBackup:
    backup: dict[str, Any]


@dataclass(frozen=True)
class FileHistoryBackupRef:
    payload: dict[str, Any]
    exists: bool
    backup_file_name: str = ""
    backup_path: str = ""
    version: int = 0


@dataclass
class FileHistorySnapshotState:
    message_id: str
    session_id: str
    backup_root: Path
    backups: dict[str, dict[str, Any]] = field(default_factory=dict)
