from __future__ import annotations

from pathlib import Path
from typing import Any

from agents.sdk.control import SDKControlRewindFilesRequest, SDKControlSeedReadStateRequest
from agents.sdk.event_fields import _first_non_empty
from agents.sdk.file_history import _SDKReadStateSeed, _rewind_entries_from_file_history_snapshots
from agents.sdk.file_rewind import (
    _apply_rewind_entry,
    _is_seed_observation_stale,
    _read_seed_text,
    _read_state_seed_key,
    _record_cwd,
    _rewind_entries_after_message,
    _rewind_response_payload,
    _rewind_workspace_root,
    _safe_rewind_path,
    _safe_workspace_path,
)
from agents.sdk.types import SDKOptions


class SDKControlFilesMixin:
    async def _seed_read_state_control_response(
        self,
        request: SDKControlSeedReadStateRequest,
        options: SDKOptions,
    ) -> dict[str, Any]:
        root = await self._control_workspace_root(options)
        try:
            target = _safe_workspace_path(root, request.path)
            relative_path = target.relative_to(root).as_posix()
            disk_mtime = target.stat().st_mtime
            if _is_seed_observation_stale(disk_mtime, request.mtime):
                return {"seeded": False, "path": relative_path, "mtime": disk_mtime}
            content, encoding = _read_seed_text(target)
        except (OSError, UnicodeError, ValueError):
            return {"seeded": False, "path": request.path, "mtime": request.mtime}
        seed_key = _read_state_seed_key(options)
        self.read_state_seeds.setdefault(seed_key, {})[relative_path] = _SDKReadStateSeed(
            path=relative_path,
            content=content,
            timestamp=disk_mtime,
            encoding=encoding,
        )
        return {"seeded": True, "path": relative_path, "mtime": disk_mtime}

    async def _rewind_files_control_response(
        self,
        request: SDKControlRewindFilesRequest,
        options: SDKOptions,
    ) -> dict[str, Any]:
        session_id = str(options.session_id or "").strip()
        if not session_id:
            return {"canRewind": False, "error": "session_id is required for rewind_files"}
        records = await self._runs_for_session(session_id)
        if not records:
            return {"canRewind": False, "error": "session not found: %s" % session_id}
        root = _rewind_workspace_root(options, records)
        entries, unsupported_paths, found_snapshot = _rewind_entries_from_file_history_snapshots(
            records,
            request.user_message_id,
            root,
            options,
        )
        if found_snapshot:
            if unsupported_paths:
                return {
                    "canRewind": False,
                    "error": "File history backup is incomplete for: %s" % ", ".join(unsupported_paths),
                }
            payload = _rewind_response_payload(entries)
            if request.dry_run:
                return payload
            try:
                for entry, target in [(entry, _safe_rewind_path(root, entry.path)) for entry in entries]:
                    _apply_rewind_entry(entry, target)
            except (OSError, ValueError) as exc:
                return {"canRewind": False, "error": "Failed to rewind: %s" % exc}
            return {"canRewind": True}

        entries, unsupported_paths, found_message = _rewind_entries_after_message(records, request.user_message_id)
        if not found_message:
            return {"canRewind": False, "error": "No user message found for id: %s" % request.user_message_id}
        if unsupported_paths:
            return {
                "canRewind": False,
                "error": "File history is incomplete for: %s" % ", ".join(unsupported_paths),
            }
        if not entries:
            return {"canRewind": False, "error": "No file checkpoint found for this message."}

        payload = _rewind_response_payload(entries)
        if request.dry_run:
            return payload

        try:
            targets = [(entry, _safe_rewind_path(root, entry.path)) for entry in entries]
        except ValueError as exc:
            return {"canRewind": False, "error": str(exc)}
        try:
            for entry, target in targets:
                _apply_rewind_entry(entry, target)
        except (OSError, ValueError) as exc:
            return {"canRewind": False, "error": "Failed to rewind: %s" % exc}
        return {"canRewind": True}

    async def _control_workspace_root(self, options: SDKOptions) -> Path:
        if options.cwd:
            return Path(options.cwd).resolve()
        if options.session_id:
            records = await self._runs_for_session(options.session_id)
            cwd = _first_non_empty(_record_cwd(record) for record in reversed(records))
            if cwd:
                return Path(cwd).resolve()
        return Path(".").resolve()

    def _apply_read_state_seeds_to_session(self, session: Any, options: SDKOptions) -> None:
        context = getattr(session, "tool_context", None)
        file_read_state = getattr(context, "file_read_state", None)
        if not isinstance(file_read_state, dict):
            return
        seed_key = _read_state_seed_key(options)
        seeds: dict[str, _SDKReadStateSeed] = {}
        default_seeds = self.read_state_seeds.pop("", {})
        session_seeds = self.read_state_seeds.pop(seed_key, {}) if seed_key else {}
        seeds.update(default_seeds)
        seeds.update(session_seeds)
        for path, seed in seeds.items():
            file_read_state.setdefault(
                path,
                {
                    "path": seed.path,
                    "content": seed.content,
                    "encoding": seed.encoding,
                    "timestamp": seed.timestamp,
                    "full_read": True,
                    "source": "read",
                    "offset": 1,
                    "limit": None,
                    "is_partial_view": False,
                },
            )
