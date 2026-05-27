"""Compatibility facade for SDK file-history behavior.

The implementation is split by responsibility:
- recorder lifecycle and snapshot emission live in `file_history_recorder`.
- snapshot parsing and backup refs live in `file_history_snapshots`.
- backup path resolution lives in `file_history_paths`.
- fork-session backup migration lives in `file_history_migration`.
- snapshot-chain rewind entry reconstruction lives in `file_history_rewind`.
"""

from __future__ import annotations

from agents.sdk.file_history_migration import _events_for_fork, _migrate_file_history_events_for_session
from agents.sdk.file_history_recorder import _SDKFileHistoryRecorder, _sdk_file_history_enabled, _sdk_file_history_recorder
from agents.sdk.file_history_rewind import _rewind_entries_from_file_history_snapshots
from agents.sdk.file_history_types import _FileHistoryBackupRef, _FileHistorySnapshot, _SDKReadStateSeed


__all__ = [
    "_FileHistoryBackupRef",
    "_FileHistorySnapshot",
    "_SDKFileHistoryRecorder",
    "_SDKReadStateSeed",
    "_events_for_fork",
    "_migrate_file_history_events_for_session",
    "_rewind_entries_from_file_history_snapshots",
    "_sdk_file_history_enabled",
    "_sdk_file_history_recorder",
]
