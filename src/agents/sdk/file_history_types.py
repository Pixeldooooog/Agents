from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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
