from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any, Literal

from agents.kernel.mcp.config import MCPServerRecord
from agents.kernel.state.runs import RunRecord
from agents.kernel.tasks import TaskEngine, TaskRecord
from agents.sdk.async_messages import (
    _SDKAsyncMessageQueueItem,
    _async_message_priority,
    _async_message_priority_value,
    _sorted_async_message_items,
)
from agents.sdk.control import (
    SDKControlApplyFlagSettingsRequest,
    SDKControlCancelAsyncMessageRequest,
    SDKControlElicitationRequest,
    SDKControlErrorResponse,
    SDKControlGetContextUsageRequest,
    SDKControlGetSettingsRequest,
    SDKControlInitializeRequest,
    SDKControlInterruptRequest,
    SDKControlMcpMessageRequest,
    SDKControlMcpReconnectRequest,
    SDKControlMcpSetServersRequest,
    SDKControlMcpStatusRequest,
    SDKControlMcpToggleRequest,
    SDKControlPermissionRequest,
    SDKControlReloadPluginsRequest,
    SDKControlRequest,
    SDKControlRequestInner,
    SDKControlResponse,
    SDKControlResponseInner,
    SDKControlRewindFilesRequest,
    SDKControlSeedReadStateRequest,
    SDKControlSetMaxThinkingTokensRequest,
    SDKControlSetModelRequest,
    SDKControlSetPermissionModeRequest,
    SDKControlStopTaskRequest,
    SDKControlSuccessResponse,
    SDKHookCallbackRequest,
    validate_sdk_control_request,
)
from agents.sdk.control_payloads import (
    _empty_context_usage_payload,
    _initialize_control_response_payload,
    _mcp_record_from_control_config,
    _mcp_server_status_from_record,
    _merge_mcp_server_statuses,
    _metadata_string_list,
    _permission_control_response_payload,
    _sdk_system_message,
    _sdk_task_payload,
    _settings_control_response_payload,
    _settings_mcp_server_statuses,
    _slash_command_infos,
    _task_id_matches,
    _task_in_sdk_scope,
)
from agents.sdk.event_fields import _first_non_empty, _text_field
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
from agents.sdk.mcp.control import active_session_for_options, reconnect_mcp_server
from agents.sdk.options import _apply_control_settings, _coerce_options
from agents.sdk.session_records import _runtime_fields_from_run
from agents.sdk.types import SDKOptions, SDKSystemMessage, SDKUserMessage


class SDKControlHandlersMixin:
    async def handle_control_request(
        self,
        message: SDKControlRequest | dict[str, Any],
        options: SDKOptions | dict[str, Any] | None = None,
    ) -> SDKControlResponse:
        control = validate_sdk_control_request(message)
        resolved_options = _coerce_options(options)
        try:
            payload = await self._control_response_payload(control.request, resolved_options)
            response: SDKControlResponseInner = SDKControlSuccessResponse(
                request_id=control.request_id,
                response=payload,
            )
        except Exception as exc:
            response = SDKControlErrorResponse(request_id=control.request_id, error=str(exc))
        return SDKControlResponse(response=response)

    async def _control_response_payload(
        self,
        request: SDKControlRequestInner,
        options: SDKOptions,
    ) -> dict[str, Any]:
        if isinstance(request, SDKControlInitializeRequest):
            return _initialize_control_response_payload(self.settings, options, request)
        if isinstance(request, SDKControlMcpStatusRequest):
            return {"mcpServers": await self._mcp_statuses_for_options(options)}
        if isinstance(request, SDKControlPermissionRequest):
            return await _permission_control_response_payload(request, options)
        if isinstance(request, SDKControlSetModelRequest):
            return {"model": request.model or ""}
        if isinstance(request, SDKControlSetPermissionModeRequest):
            return {"mode": request.mode, "ultraplan": bool(request.ultraplan or False)}
        if isinstance(request, SDKControlSetMaxThinkingTokensRequest):
            return {"max_thinking_tokens": request.max_thinking_tokens}
        if isinstance(request, SDKControlGetSettingsRequest):
            return _settings_control_response_payload(options)
        if isinstance(request, SDKControlApplyFlagSettingsRequest):
            updated = _apply_control_settings(options, request.settings)
            return _settings_control_response_payload(updated)
        if isinstance(request, SDKControlMcpSetServersRequest):
            return await self._mcp_set_servers_control_response(request, options)
        if isinstance(request, SDKControlMcpToggleRequest):
            return await self._mcp_toggle_control_response(request, options)
        if isinstance(request, SDKControlMcpReconnectRequest):
            return await self._mcp_reconnect_control_response(request, options)
        if isinstance(request, SDKControlInterruptRequest):
            return self._interrupt_control_response(options)
        if isinstance(request, SDKControlGetContextUsageRequest):
            return _empty_context_usage_payload(options)
        if isinstance(request, SDKHookCallbackRequest):
            return await self._hook_callback_control_response(request)
        if isinstance(request, SDKControlReloadPluginsRequest):
            return {"commands": _slash_command_infos(), "agents": [], "plugins": [], "mcpServers": [], "error_count": 0}
        if isinstance(request, SDKControlCancelAsyncMessageRequest):
            return self._cancel_async_message_control_response(request)
        if isinstance(request, SDKControlRewindFilesRequest):
            return await self._rewind_files_control_response(request, options)
        if isinstance(request, SDKControlSeedReadStateRequest):
            return await self._seed_read_state_control_response(request, options)
        if isinstance(request, SDKControlMcpMessageRequest):
            return await self._mcp_message_control_response(request, options)
        if isinstance(request, SDKControlStopTaskRequest):
            return await self._stop_task_control_response(request, options)
        if isinstance(request, SDKControlElicitationRequest):
            return await self._elicitation_control_response(request)
        return {}

    def _cancel_async_message_control_response(self, request: SDKControlCancelAsyncMessageRequest) -> dict[str, Any]:
        removed = self._dequeue_matching_async_messages(
            lambda item: item.message.uuid == request.message_uuid,
        )
        return {"cancelled": bool(removed)}

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

    def _dequeue_matching_async_messages(
        self,
        predicate: Callable[[_SDKAsyncMessageQueueItem], bool],
    ) -> list[SDKUserMessage]:
        matched: list[_SDKAsyncMessageQueueItem] = []
        remaining: list[_SDKAsyncMessageQueueItem] = []
        for item in self.async_message_queue:
            if predicate(item):
                matched.append(item)
            else:
                remaining.append(item)
        if not matched:
            return []
        self.async_message_queue = remaining
        return [item.message for item in _sorted_async_message_items(matched)]

    def _interrupt_active_turn_for_async_message(self, session_id: str) -> None:
        if not session_id:
            return
        task = self.active_turn_tasks.get(session_id)
        if task is None or task.done():
            return
        try:
            current = asyncio.current_task()
        except RuntimeError:
            current = None
        if task is current:
            return
        task.cancel("interrupt")

    def _wake_active_sleep_for_async_message(self, session_id: str) -> None:
        if session_id:
            event = self.active_sleep_wake_events.get(session_id)
            if event is not None:
                event.set()
            return
        for event in set(self.active_sleep_wake_events.values()):
            event.set()

    def _has_async_messages(
        self,
        *,
        session_id: str = "",
        max_priority: Literal["now", "next", "later"] = "later",
    ) -> bool:
        max_rank = _async_message_priority(max_priority)
        for item in self.async_message_queue:
            if session_id and item.message.session_id != session_id:
                continue
            if _async_message_priority(item.message.priority) <= max_rank:
                return True
        return False

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

    async def _mcp_statuses_for_options(self, options: SDKOptions) -> list[dict[str, Any]]:
        statuses = await self._sdk_mcp_server_statuses_for_scope(
            tenant_id=options.tenant_id or "",
            user_id=options.user_id or "",
            agent_id=options.agent_id or "",
            workspace_id="",
        )
        sdk_statuses = [{"name": name, "status": "connected"} for name in self.sdk_mcp_handlers]
        return [dict(item) for item in _merge_mcp_server_statuses(sdk_statuses, statuses)]

    def _interrupt_control_response(self, options: SDKOptions) -> dict[str, Any]:
        keys = [str(options.session_id or "")]
        run_id = str(options.metadata.get("run_id") or options.metadata.get("runId") or "")
        if run_id:
            keys.append(run_id)
        current = asyncio.current_task()
        for key in keys:
            if not key:
                continue
            task = self.active_turn_tasks.get(key)
            if task is None or task.done():
                continue
            if task is current:
                return {"interrupted": False, "reason": "cannot interrupt the current control handler task"}
            task.cancel("interrupt")
            return {"interrupted": True, "session_id": key, "run_id": self.active_turn_run_ids.get(key, "")}
        return {"interrupted": False, "reason": "no active SDK turn is attached to this control handler"}

    def _clear_active_turn(
        self,
        session_id: str,
        run_id: str,
        task: asyncio.Task[Any] | None,
        session: Any | None = None,
    ) -> None:
        for key in (session_id, run_id):
            if task is None or self.active_turn_tasks.get(key) is task:
                self.active_turn_tasks.pop(key, None)
                self.active_turn_run_ids.pop(key, None)
                self.active_sleep_wake_events.pop(key, None)
            if session is None or self.active_turn_sessions.get(key) is session:
                self.active_turn_sessions.pop(key, None)

    def _install_sleep_wake_for_turn(self, session: Any, *, session_id: str, run_id: str) -> None:
        context = getattr(session, "tool_context", None)
        if context is None:
            return
        event = asyncio.Event()
        context.sleep_wake_event = event
        context.sleep_wake_check = lambda: self._has_async_messages(session_id=session_id, max_priority="later")
        context.async_message_enqueue = lambda message: self.enqueue_async_message(
            message,
            session_id=session_id,
            priority=_async_message_priority_value(message),
        )
        self.active_sleep_wake_events[session_id] = event
        self.active_sleep_wake_events[run_id] = event

    async def _mcp_set_servers_control_response(
        self,
        request: SDKControlMcpSetServersRequest,
        options: SDKOptions,
    ) -> dict[str, Any]:
        assert self.persistence is not None
        tenant_id = options.tenant_id or ""
        user_id = options.user_id or ""
        agent_id = options.agent_id or ""
        workspace_id = ""
        existing = await self.persistence.mcp_configs.list_for_scope(
            tenant_id=tenant_id,
            user_id=user_id,
            agent_id=agent_id,
            workspace_id=workspace_id,
        )
        wanted = {str(name): dict(config) for name, config in request.servers.items()}
        existing_names = {record.name for record in existing}
        removed: list[str] = []
        for record in existing:
            if record.name not in wanted:
                await self.persistence.mcp_configs.delete(
                    record.name,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    agent_id=agent_id,
                    workspace_id=workspace_id,
                )
                removed.append(record.name)
        added: list[str] = []
        errors: dict[str, str] = {}
        for name, config in wanted.items():
            try:
                await self.persistence.mcp_configs.save(
                    _mcp_record_from_control_config(
                        name,
                        config,
                        tenant_id=tenant_id,
                        user_id=user_id,
                        agent_id=agent_id,
                        workspace_id=workspace_id,
                    )
                )
                if name not in existing_names:
                    added.append(name)
            except Exception as exc:
                errors[name] = str(exc)
        return {"added": sorted(added), "removed": sorted(removed), "errors": errors}

    async def _mcp_toggle_control_response(
        self,
        request: SDKControlMcpToggleRequest,
        options: SDKOptions,
    ) -> dict[str, Any]:
        assert self.persistence is not None
        tenant_id = options.tenant_id or ""
        user_id = options.user_id or ""
        agent_id = options.agent_id or ""
        workspace_id = ""
        records = await self.persistence.mcp_configs.list_for_scope(
            tenant_id=tenant_id,
            user_id=user_id,
            agent_id=agent_id,
            workspace_id=workspace_id,
        )
        for record in records:
            if record.name == request.serverName:
                await self.persistence.mcp_configs.save(replace(record, enabled=request.enabled))
                return {"serverName": request.serverName, "enabled": request.enabled}
        if request.serverName in self.sdk_mcp_handlers:
            await self.persistence.mcp_configs.save(
                MCPServerRecord(
                    name=request.serverName,
                    command="",
                    transport="sdk",
                    enabled=request.enabled,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    agent_id=agent_id,
                    workspace_id=workspace_id,
                )
            )
            return {"serverName": request.serverName, "enabled": request.enabled}
        raise KeyError("MCP server not found: %s" % request.serverName)

    async def _mcp_reconnect_control_response(
        self,
        request: SDKControlMcpReconnectRequest,
        options: SDKOptions,
    ) -> dict[str, Any]:
        server_name = str(request.serverName or "").strip()
        return await reconnect_mcp_server(
            server_name,
            active_session=active_session_for_options(self.active_turn_sessions, options),
            sdk_handler_registered=server_name in self.sdk_mcp_handlers,
            sdk_server_enabled=lambda name: self._sdk_mcp_server_enabled(name, options),
            status_for_server=lambda name: self._mcp_status_for_server(name, options),
        )

    async def _mcp_status_for_server(self, server_name: str, options: SDKOptions) -> str | None:
        for item in await self._mcp_statuses_for_options(options):
            if str(item.get("name") or "") == server_name:
                return str(item.get("status") or "")
        return None

    async def _mcp_message_control_response(
        self,
        request: SDKControlMcpMessageRequest,
        options: SDKOptions,
    ) -> dict[str, Any]:
        handler = self.sdk_mcp_handlers.get(request.server_name)
        if handler is None:
            raise KeyError("SDK MCP server not registered: %s" % request.server_name)
        if not await self._sdk_mcp_server_enabled(request.server_name, options):
            raise RuntimeError("SDK MCP server is disabled: %s" % request.server_name)
        response = handler(request.message)
        if inspect.isawaitable(response):
            response = await response
        return {"mcp_response": response}

    async def _hook_callback_control_response(self, request: SDKHookCallbackRequest) -> dict[str, Any]:
        handler = self.hook_callback_handlers.get(request.callback_id)
        if handler is None:
            return {}
        response = handler(request)
        if inspect.isawaitable(response):
            response = await response
        if response is None:
            return {}
        if not isinstance(response, dict):
            raise TypeError("hook callback handler must return a dict")
        return dict(response)

    async def _elicitation_control_response(self, request: SDKControlElicitationRequest) -> dict[str, Any]:
        return await self._run_elicitation_handler(request)

    async def _run_elicitation_handler(self, request: SDKControlElicitationRequest) -> dict[str, Any]:
        if self.elicitation_handler is None:
            return {"action": "cancel"}
        response = self.elicitation_handler(request)
        if inspect.isawaitable(response):
            response = await response
        if response is None:
            return {"action": "cancel"}
        if not isinstance(response, dict):
            raise TypeError("elicitation handler must return a dict")
        action = str(response.get("action") or "cancel")
        if action not in {"accept", "decline", "cancel"}:
            raise ValueError("elicitation action must be accept, decline, or cancel")
        payload: dict[str, Any] = {"action": action}
        content = response.get("content")
        if content is not None:
            if not isinstance(content, dict):
                raise TypeError("elicitation content must be a dict")
            payload["content"] = dict(content)
        return payload

    async def _sdk_mcp_server_enabled(self, name: str, options: SDKOptions) -> bool:
        assert self.persistence is not None
        records = await self.persistence.mcp_configs.list_for_scope(
            tenant_id=options.tenant_id or "",
            user_id=options.user_id or "",
            agent_id=options.agent_id or "",
            workspace_id="",
        )
        for record in records:
            if record.name == name:
                return bool(record.enabled)
        return True

    async def _stop_task_control_response(
        self,
        request: SDKControlStopTaskRequest,
        options: SDKOptions,
    ) -> dict[str, Any]:
        assert self.persistence is not None
        task = await self._resolve_sdk_task(request.task_id, options)
        updated = await TaskEngine(self.persistence.tasks).cancel_task(task.task_id)
        return {"stopped": True, "task": _sdk_task_payload(updated)}

    async def _resolve_sdk_task(self, task_id: str, options: SDKOptions) -> TaskRecord:
        assert self.persistence is not None
        target = str(task_id or "").strip()
        if not target:
            raise ValueError("task_id is required")
        task = await self.persistence.tasks.load_task(target)
        if task is not None and _task_in_sdk_scope(task, options):
            return task
        matches = [
            task
            for task in await self.persistence.tasks.list_tasks(
                options.tenant_id or "",
                user_id=options.user_id or "",
                agent_id=options.agent_id or "",
            )
            if _task_id_matches(task.task_id, target)
        ]
        if not matches:
            raise KeyError("task not found: %s" % target)
        if len(matches) > 1:
            raise ValueError("task id is ambiguous: %s" % target)
        return matches[0]

    async def _system_message_from_session(
        self,
        session: Any,
        options: SDKOptions,
        *,
        session_id: str,
        run_id: str,
    ) -> SDKSystemMessage:
        workspace = getattr(session, "workspace", None)
        runtime = getattr(session, "runtime", None)
        mcp_servers = await self._sdk_mcp_server_statuses_for_scope(
            tenant_id=str(getattr(workspace, "tenant_id", "") or options.tenant_id or ""),
            user_id=str(getattr(workspace, "user_id", "") or options.user_id or ""),
            agent_id=str(getattr(workspace, "agent_id", "") or options.agent_id or ""),
            workspace_id=str(getattr(workspace, "workspace_id", "") or ""),
        )
        return _sdk_system_message(
            session_id=session_id,
            run_id=run_id,
            cwd=str(getattr(workspace, "path", "") or options.cwd or ""),
            model=str(getattr(runtime, "model", "") or options.model or ""),
            tools=[str(tool) for tool in list(getattr(runtime, "enabled_tools", []) or [])],
            skills=list(options.skills or []),
            permission_mode=options.permission_mode,
            metadata=options.metadata,
            mcp_servers=mcp_servers,
        )

    async def _system_message_from_run(self, record: RunRecord, *, session_id: str) -> SDKSystemMessage:
        model, _protocol, tools = _runtime_fields_from_run(record)
        spec = record.spec
        workspace = spec.get("workspace") if isinstance(spec.get("workspace"), dict) else {}
        spec_metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
        metadata = {**dict(record.metadata), **dict(spec_metadata)}
        mcp_servers = await self._sdk_mcp_server_statuses_for_scope(
            tenant_id=_text_field(metadata, "sdk_tenant_id") or str(workspace.get("tenant_id") or ""),
            user_id=_text_field(metadata, "sdk_user_id") or str(workspace.get("user_id") or ""),
            agent_id=_text_field(metadata, "sdk_agent_id") or str(workspace.get("agent_id") or spec.get("agent_id") or ""),
            workspace_id=_text_field(metadata, "sdk_workspace_id") or str(workspace.get("workspace_id") or ""),
        )
        skills = spec.get("skills") if isinstance(spec.get("skills"), list) else []
        return _sdk_system_message(
            session_id=session_id,
            run_id=record.run_id,
            cwd=_record_cwd(record),
            model=_text_field(metadata, "sdk_init_model") or model,
            tools=_metadata_string_list(metadata, "sdk_init_tools_json") or tools,
            skills=[str(skill) for skill in skills],
            permission_mode=str(spec.get("permission_profile") or ""),
            metadata=metadata,
            mcp_servers=mcp_servers,
        )

    async def _sdk_mcp_server_statuses_for_scope(
        self,
        *,
        tenant_id: str,
        user_id: str = "",
        agent_id: str = "",
        workspace_id: str = "",
    ) -> list[dict[str, str]]:
        servers = _settings_mcp_server_statuses(self.settings)
        if self.persistence is None:
            return servers
        try:
            records = await self.persistence.mcp_configs.list_for_scope(
                tenant_id=tenant_id,
                user_id=user_id,
                agent_id=agent_id,
                workspace_id=workspace_id,
            )
        except Exception:
            return servers
        return _merge_mcp_server_statuses(servers, [_mcp_server_status_from_record(record) for record in records])
