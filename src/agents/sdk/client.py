from __future__ import annotations

import asyncio
import difflib
import inspect
import json
import os
import time
import uuid
from collections.abc import AsyncIterable, AsyncIterator, Callable, Iterable
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Literal

from agents.kernel.assembly import create_agent_session_async
from agents.kernel.config import runtime_settings
from agents.kernel.capabilities.sandbox.text import (
    BINARY_SAMPLE_BYTES,
    decode_text_bytes,
    detect_text_encoding,
    public_encoding_name,
)
from agents.kernel.governance.factory import build_tool_permission_policy
from agents.kernel.mcp_config import MCPServerRecord
from agents.kernel.schema import RuntimeEvent, ToolCall
from agents.kernel.specs import AgentSpec
from agents.kernel.tasks import TaskEngine, TaskRecord
from agents.platform.commands import COMMANDS, command_names
from agents.kernel.state.runs import RunRecord
from agents.platform.persistence import PlatformPersistence, create_ephemeral_persistence
from agents.platform.sessions import RunService
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
    SDKKeepAliveMessage,
    SDKStdinMessage,
    SDKStdoutMessage,
    SDKUpdateEnvironmentVariablesMessage,
    validate_sdk_control_request,
    validate_sdk_stdin_message,
)
from agents.sdk.structured_io import SDKStructuredIO
from agents.sdk.types import (
    SDKAPIRetryMessage,
    SDKAssistantMessage,
    SDKAuthStatusMessage,
    SDKCompactBoundaryMessage,
    SDKFilesPersistedMessage,
    SDKForkSessionOptions,
    SDKForkSessionResult,
    SDKGetSessionMessagesOptions,
    SDKListSessionsOptions,
    SDKMessage,
    SDKOptions,
    SDKResultMessage,
    SDKHookProgressMessage,
    SDKHookResponseMessage,
    SDKHookStartedMessage,
    SDKLocalCommandOutputMessage,
    SDKElicitationCompleteMessage,
    SDKPostTurnSummaryMessage,
    SDKPromptSuggestionMessage,
    SDKRateLimitEventMessage,
    SDKSessionStateChangedMessage,
    SDKSessionInfo,
    SDKStatusMessage,
    SDKStreamEventMessage,
    SDKSystemMessage,
    SDKTaskNotificationMessage,
    SDKTaskProgressMessage,
    SDKTaskStartedMessage,
    SDKToolProgressMessage,
    SDKToolUseSummaryMessage,
    SDKUserMessage,
)


SessionFactory = Callable[[Any, AgentSpec], Any]
SDKMcpMessageHandler = Callable[[Any], Any]
SDKHookCallbackHandler = Callable[[SDKHookCallbackRequest], Any]
SDKElicitationHandler = Callable[[SDKControlElicitationRequest], Any]
MAX_SDK_SEED_READ_BYTES = 200000


@dataclass
class _RewindFileEntry:
    path: str
    before: str = ""
    existed: bool = True
    encoding: str = "utf-8"
    insertions: int = 0
    deletions: int = 0


@dataclass
class _SDKAsyncMessageQueueItem:
    sequence: int
    message: SDKUserMessage


@dataclass
class _SDKReadStateSeed:
    path: str
    content: str
    timestamp: float
    encoding: str = "utf-8"


try:
    _SDK_VERSION = version("agents")
except PackageNotFoundError:
    _SDK_VERSION = "0.1.0"


@dataclass
class AgentSDKClient:
    """Stable SDK facade over kernel assembly and platform stores."""

    settings: Any = None
    persistence: PlatformPersistence | None = None
    run_service: RunService | None = None
    session_factory: SessionFactory | None = None
    sdk_mcp_handlers: dict[str, SDKMcpMessageHandler] = field(default_factory=dict)
    hook_callback_handlers: dict[str, SDKHookCallbackHandler] = field(default_factory=dict)
    elicitation_handler: SDKElicitationHandler | None = None
    active_turn_tasks: dict[str, asyncio.Task[Any]] = field(default_factory=dict)
    active_turn_run_ids: dict[str, str] = field(default_factory=dict)
    async_message_queue: list[_SDKAsyncMessageQueueItem] = field(default_factory=list)
    async_message_sequence: int = 0
    read_state_seeds: dict[str, dict[str, _SDKReadStateSeed]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.settings is None:
            self.settings = runtime_settings
        if self.persistence is None:
            self.persistence = create_ephemeral_persistence(self.settings)
        if self.run_service is None:
            self.run_service = RunService(
                self.persistence.runs,
                sandbox_store=self.persistence.sandboxes,
            )

    async def create_session(self, options: SDKOptions | None = None):
        options = _coerce_options(options)
        spec = _spec_from_options(options)
        if self.session_factory is not None:
            session = await self.session_factory(self.settings, spec)
            self._apply_read_state_seeds_to_session(session, options)
            return session
        assert self.persistence is not None
        session = await create_agent_session_async(
            self.settings,
            spec,
            checkpoint_store=self.persistence.checkpoints,
            memory_store=self.persistence.memories,
            schedule_store=self.persistence.schedules,
            team_store=self.persistence.teams,
            hook_store=self.persistence.hooks,
            mcp_config_store=self.persistence.mcp_configs,
            session_state_store=self.persistence.session_states,
            sandbox_store=self.persistence.sandboxes,
            artifact_store=self.persistence.artifacts,
            artifact_blob_store=self.persistence.artifact_blobs,
            task_store=self.persistence.tasks,
            run_service=self.run_service,
            agent_profile_store=self.persistence.agent_profiles,
        )
        self._apply_read_state_seeds_to_session(session, options)
        return session

    def create_sdk_session(self, options: SDKOptions | dict[str, Any] | None = None) -> "SDKSession":
        options = _coerce_options(options)
        session_id = options.session_id or "session_%s" % uuid.uuid4().hex
        return SDKSession(
            client=self,
            session_id=session_id,
            options=options.model_copy(update={"session_id": session_id}),
        )

    def register_sdk_mcp_server(self, name: str, handler: SDKMcpMessageHandler) -> None:
        server_name = str(name or "").strip()
        if not server_name:
            raise ValueError("SDK MCP server name is required")
        self.sdk_mcp_handlers[server_name] = handler

    def unregister_sdk_mcp_server(self, name: str) -> None:
        self.sdk_mcp_handlers.pop(str(name or "").strip(), None)

    def register_hook_callback(self, callback_id: str, handler: SDKHookCallbackHandler) -> None:
        resolved = str(callback_id or "").strip()
        if not resolved:
            raise ValueError("hook callback id is required")
        self.hook_callback_handlers[resolved] = handler

    def unregister_hook_callback(self, callback_id: str) -> None:
        self.hook_callback_handlers.pop(str(callback_id or "").strip(), None)

    def set_elicitation_handler(self, handler: SDKElicitationHandler | None) -> None:
        self.elicitation_handler = handler

    def enqueue_async_message(
        self,
        message: SDKUserMessage | dict[str, Any] | str,
        *,
        session_id: str = "",
        priority: Literal["now", "next", "later"] | None = None,
    ) -> SDKUserMessage:
        queued = _coerce_async_user_message(message, session_id=session_id, priority=priority)
        self.async_message_queue.append(_SDKAsyncMessageQueueItem(sequence=self.async_message_sequence, message=queued))
        self.async_message_sequence += 1
        if queued.priority == "now":
            self._interrupt_active_turn_for_async_message(queued.session_id)
        return queued

    def list_async_messages(self, *, session_id: str = "") -> list[SDKUserMessage]:
        return [
            item.message
            for item in _sorted_async_message_items(self.async_message_queue)
            if not session_id or item.message.session_id == session_id
        ]

    def dequeue_async_message(self, *, session_id: str = "") -> SDKUserMessage | None:
        candidates = [
            item
            for item in _sorted_async_message_items(self.async_message_queue)
            if not session_id or item.message.session_id == session_id
        ]
        if not candidates:
            return None
        target = candidates[0]
        self.async_message_queue.remove(target)
        return target.message

    async def resume_session(self, session_id: str, options: SDKOptions | dict[str, Any] | None = None) -> "SDKSession":
        info = await self.get_session_info(session_id)
        if info is None:
            raise KeyError("session not found: %s" % session_id)
        options = _coerce_options(options).model_copy(update={"session_id": session_id})
        return SDKSession(client=self, session_id=session_id, options=options)

    async def query(self, prompt: str, options: SDKOptions | dict[str, Any] | None = None) -> AsyncIterator[SDKMessage]:
        options = _coerce_options(options)
        async for message in self._query_turn(str(prompt or ""), options):
            yield message

    async def query_user_message(
        self,
        message: SDKUserMessage | dict[str, Any],
        options: SDKOptions | dict[str, Any] | None = None,
    ) -> AsyncIterator[SDKMessage]:
        options = _coerce_options(options)
        user_message = _coerce_async_user_message(message, session_id=options.session_id or "")
        if user_message.session_id and user_message.session_id != options.session_id:
            options = options.model_copy(update={"session_id": user_message.session_id})
        async for item in self._query_turn(user_message.content, options, user_message=user_message):
            yield item

    async def run_stdin(
        self,
        messages: AsyncIterable[SDKStdinMessage | dict[str, Any]] | Iterable[SDKStdinMessage | dict[str, Any]],
        options: SDKOptions | dict[str, Any] | None = None,
        structured_io: SDKStructuredIO | None = None,
    ) -> AsyncIterator[SDKStdoutMessage]:
        session = self.create_sdk_session(_coerce_options(options))
        replay_user_messages = _replay_user_messages_enabled(session.options)
        io = structured_io or SDKStructuredIO(replay_user_messages=replay_user_messages)
        io.replay_user_messages = replay_user_messages
        received_user_uuids: set[str] = set()
        inbound = _aiter_stdin_messages(messages)
        inbound_task: asyncio.Task[SDKStdinMessage | dict[str, Any]] | None = asyncio.create_task(_anext(inbound))
        outbound_task: asyncio.Task[SDKStdoutMessage | None] | None = asyncio.create_task(io.next_stdout_message())
        try:
            while inbound_task is not None or outbound_task is not None:
                tasks = {task for task in (inbound_task, outbound_task) if task is not None}
                done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                if outbound_task in done:
                    outbound = outbound_task.result()
                    if outbound is None:
                        outbound_task = None
                    else:
                        yield outbound
                        outbound_task = asyncio.create_task(io.next_stdout_message())
                if inbound_task in done:
                    try:
                        raw_message = inbound_task.result()
                    except StopAsyncIteration:
                        inbound_task = None
                        io.close()
                        continue
                    async for output in self._process_stdin_message(
                        raw_message,
                        session=session,
                        structured_io=io,
                        replay_user_messages=replay_user_messages,
                        received_user_uuids=received_user_uuids,
                    ):
                        yield output
                    inbound_task = asyncio.create_task(_anext(inbound))
        finally:
            for task in (inbound_task, outbound_task):
                if task is not None and not task.done():
                    task.cancel()

    async def _process_stdin_message(
        self,
        raw_message: SDKStdinMessage | dict[str, Any],
        *,
        session: "SDKSession",
        structured_io: SDKStructuredIO,
        replay_user_messages: bool,
        received_user_uuids: set[str],
    ) -> AsyncIterator[SDKStdoutMessage]:
        message = await structured_io.receive(validate_sdk_stdin_message(raw_message))
        if message is None:
            return
        if isinstance(message, SDKUserMessage):
            user_message = _coerce_async_user_message(message, session_id=session.session_id)
            if replay_user_messages:
                yield user_message.model_copy(update={"isReplay": True})
            if user_message.uuid in received_user_uuids:
                return
            received_user_uuids.add(user_message.uuid)
            session.enqueue_async_message(user_message)
            async for output in session._drain_async_messages(session.options):
                yield output
        elif isinstance(message, SDKControlRequest):
            yield await session.handle_control_request(message)
        elif isinstance(message, SDKUpdateEnvironmentVariablesMessage):
            _apply_environment_variables_update(session.options, message)
        elif isinstance(message, SDKKeepAliveMessage):
            return
        elif isinstance(message, SDKControlResponse):
            yield message

    async def _query_turn(
        self,
        prompt: str,
        options: SDKOptions,
        *,
        user_message: SDKUserMessage | None = None,
    ) -> AsyncIterator[SDKMessage]:
        spec = _spec_from_options(options)
        started_at = time.monotonic()
        session = await self.create_session(options)
        run = await self.run_service.start(spec)
        run_id = run.run_id
        session_id = options.session_id or run_id
        current_task = asyncio.current_task()
        if current_task is not None:
            self.active_turn_tasks[session_id] = current_task
            self.active_turn_tasks[run_id] = current_task
            self.active_turn_run_ids[session_id] = run_id
            self.active_turn_run_ids[run_id] = run_id
        await self._record_session_metadata(
            run_id,
            session_id=session_id,
            prompt=prompt,
            options=options,
            session=session,
        )
        await self.run_service.record_event(
            run_id,
            _user_message_event(prompt, session_id=session_id, run_id=run_id, user_message=user_message),
        )
        running_event = _session_state_event("running")
        await self.run_service.record_event(run_id, running_event)
        final_status = "finished"
        yielded_result = False
        event_count = 0
        requires_action_emitted = False

        yield await self._system_message_from_session(
            session,
            options,
            session_id=session_id,
            run_id=run_id,
        )
        yield _project_session_state_event(running_event, session_id=session_id, run_id=run_id)

        try:
            async for event in session.stream(prompt, run_id=run_id):
                event_count += 1
                await self.run_service.record_event(run_id, event)
                messages = _project_runtime_event_messages(
                    event,
                    session_id=session_id,
                    run_id=run_id,
                    duration_ms=_duration_ms(started_at),
                    num_turns=1,
                )
                for message in messages:
                    if isinstance(message, SDKResultMessage):
                        yielded_result = True
                        final_status = message.status
                    elif isinstance(message, SDKToolProgressMessage) and message.status == "awaiting_approval":
                        final_status = "awaiting_approval"
                        await self.run_service.pause_for_approval(run_id)
                        if not requires_action_emitted:
                            requires_action = _session_state_event("requires_action")
                            await self.run_service.record_event(run_id, requires_action)
                            yield _project_session_state_event(requires_action, session_id=session_id, run_id=run_id)
                            requires_action_emitted = True
                    yield message
        except asyncio.CancelledError as exc:
            if not _is_sdk_interrupt_cancel(exc):
                raise
            final_status = "canceled"
            yielded_result = True
            canceled_event = RuntimeEvent(
                type="done",
                name="assistant",
                payload={"content": "run canceled", "status": "canceled"},
            )
            await self.run_service.record_event(run_id, canceled_event)
            for message in _project_runtime_event_messages(
                canceled_event,
                session_id=session_id,
                run_id=run_id,
                duration_ms=_duration_ms(started_at),
                num_turns=1,
            ):
                yield message
        except Exception as exc:
            final_status = "error"
            yielded_result = True
            error_message = SDKResultMessage(
                session_id=session_id,
                run_id=run_id,
                subtype="error_during_execution",
                is_error=True,
                result="",
                stop_reason="error",
                errors=[str(exc)],
                duration_ms=_duration_ms(started_at),
                num_turns=1,
            )
            yield error_message
        finally:
            if not yielded_result:
                is_error = final_status == "error"
                yield SDKResultMessage(
                    session_id=session_id,
                    run_id=run_id,
                    subtype="error_during_execution" if is_error else "success",
                    is_error=is_error,
                    stop_reason=final_status,
                    errors=[final_status] if is_error else [],
                    duration_ms=_duration_ms(started_at),
                    num_turns=1,
                )
            if final_status != "awaiting_approval":
                await self.run_service.finish(run_id, error="" if final_status == "finished" else final_status)
                idle_event = _session_state_event("idle")
                await self.run_service.record_event(run_id, idle_event)
                yield _project_session_state_event(idle_event, session_id=session_id, run_id=run_id)
            close = getattr(session, "aclose", None)
            if close is not None:
                await close()
            self._clear_active_turn(session_id, run_id, current_task)

    async def prompt(self, prompt: str, options: SDKOptions | dict[str, Any] | None = None) -> SDKResultMessage:
        result: SDKResultMessage | None = None
        async for message in self.query(prompt, options):
            if isinstance(message, SDKResultMessage):
                result = message
        if result is None:
            raise RuntimeError("SDK query completed without a result message")
        return result

    async def list_sessions(self, options: SDKListSessionsOptions | dict[str, Any] | None = None) -> list[SDKSessionInfo]:
        """List SDK sessions reconstructed from the configured run store."""

        options = _coerce_list_sessions_options(options)
        fetch_limit = 200 if options.limit == 0 else max(1, min(200, options.limit + options.offset))
        records = await self.run_service.list_runs(
            limit=fetch_limit,
            tenant_id=options.tenant_id,
            user_id=options.user_id,
            agent_id=options.agent_id,
        )
        if options.cwd:
            records = [record for record in records if _record_cwd(record) == options.cwd]
        infos = _session_infos_from_runs(records)
        start = options.offset
        if options.limit == 0:
            return infos[start:]
        return infos[start : start + options.limit]

    async def get_session_info(self, session_id: str) -> SDKSessionInfo | None:
        records = await self._runs_for_session(session_id)
        if not records:
            return None
        return _session_info_from_runs(records)

    async def get_session_messages(
        self,
        session_id: str,
        options: SDKGetSessionMessagesOptions | dict[str, Any] | None = None,
    ) -> list[SDKMessage]:
        options = _coerce_get_session_messages_options(options)
        records = await self._runs_for_session(session_id)
        messages: list[SDKMessage] = []
        for record in sorted(records, key=lambda item: item.created_at):
            resolved_session_id = _session_id_for_run(record)
            if options.include_system_messages:
                messages.append(await self._system_message_from_run(record, session_id=resolved_session_id))
            duration_ms = _duration_ms_from_record(record)
            for event in record.events:
                if event.type == "run_created":
                    continue
                projected = _project_runtime_event_messages(
                    event,
                    session_id=resolved_session_id,
                    run_id=record.run_id,
                    duration_ms=duration_ms,
                    num_turns=1,
                )
                messages.extend(projected)
        if options.offset:
            messages = messages[options.offset :]
        if options.limit:
            messages = messages[: options.limit]
        return messages

    async def rename_session(self, session_id: str, title: str) -> None:
        title = title.strip()
        if not title:
            raise ValueError("session title cannot be empty")
        await self._update_session_metadata(session_id, {"sdk_title": title})

    async def tag_session(self, session_id: str, tag: str | None) -> None:
        await self._update_session_metadata(session_id, {"sdk_tag": (tag or "").strip()})

    async def fork_session(
        self,
        session_id: str,
        options: SDKForkSessionOptions | dict[str, Any] | None = None,
    ) -> SDKForkSessionResult:
        options = _coerce_fork_session_options(options)
        records = await self._runs_for_session(session_id)
        if not records:
            raise KeyError("session not found: %s" % session_id)
        forked_session_id = "session_%s" % uuid.uuid4().hex
        forked_run_ids: list[str] = []
        for record in sorted(records, key=lambda item: item.created_at):
            metadata = {
                **record.metadata,
                "sdk_session_id": forked_session_id,
                "sdk_forked_from_session_id": session_id,
                "sdk_forked_from_run_id": record.run_id,
            }
            title = options.title.strip()
            if title:
                metadata["sdk_title"] = title
            spec = replace(record.to_agent_spec(), metadata=metadata)
            forked = await self.run_service.store.create_run(spec)
            events, matched = _events_for_fork(record.events, options.up_to_message_id)
            for event in events:
                await self.run_service.store.append_event(forked.run_id, event)
            await self.run_service.store.set_status(forked.run_id, record.status)
            forked_run_ids.append(forked.run_id)
            if options.up_to_message_id and matched:
                break
        return SDKForkSessionResult(session_id=forked_session_id, run_ids=forked_run_ids)

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
            return {"serverName": request.serverName, "status": "pending"}
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

        root = _rewind_workspace_root(options, records)
        try:
            targets = [(entry, _safe_rewind_path(root, entry.path)) for entry in entries]
        except ValueError as exc:
            return {"canRewind": False, "error": str(exc)}
        for entry, target in targets:
            _apply_rewind_entry(entry, target)
        return payload

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
    ) -> None:
        for key in (session_id, run_id):
            if task is None or self.active_turn_tasks.get(key) is task:
                self.active_turn_tasks.pop(key, None)
                self.active_turn_run_ids.pop(key, None)

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

    async def _record_session_metadata(
        self,
        run_id: str,
        *,
        session_id: str,
        prompt: str,
        options: SDKOptions,
        session: Any,
    ) -> None:
        workspace = getattr(session, "workspace", None)
        workspace_path = str(getattr(workspace, "path", "") or options.cwd or "")
        runtime = getattr(session, "runtime", None)
        enabled_tools = [str(tool) for tool in list(getattr(runtime, "enabled_tools", []) or [])]
        metadata = {
            "sdk_session_id": session_id,
            "sdk_first_prompt": _truncate(prompt),
            "sdk_cwd": workspace_path,
            "sdk_tenant_id": str(getattr(workspace, "tenant_id", "") or options.tenant_id or ""),
            "sdk_user_id": str(getattr(workspace, "user_id", "") or options.user_id or ""),
            "sdk_agent_id": str(getattr(workspace, "agent_id", "") or options.agent_id or ""),
            "sdk_workspace_id": str(getattr(workspace, "workspace_id", "") or ""),
            "sdk_init_tools_json": json.dumps(enabled_tools, ensure_ascii=False),
            "sdk_init_model": str(getattr(runtime, "model", "") or options.model or ""),
        }
        await self.run_service.update_metadata(run_id, metadata)

    async def _runs_for_session(self, session_id: str) -> list[RunRecord]:
        records_by_id: dict[str, RunRecord] = {}
        direct = await self.run_service.load_run(session_id)
        if direct is not None:
            records_by_id[direct.run_id] = direct
        for record in await self.run_service.list_runs(limit=200):
            if record.run_id == session_id or _session_id_for_run(record) == session_id:
                records_by_id[record.run_id] = record
        return sorted(records_by_id.values(), key=lambda item: item.created_at)

    async def _update_session_metadata(self, session_id: str, metadata: dict[str, str]) -> None:
        records = await self._runs_for_session(session_id)
        if not records:
            raise KeyError("session not found: %s" % session_id)
        for record in records:
            await self.run_service.update_metadata(record.run_id, metadata)


@dataclass
class SDKSession:
    """High-level persistent SDK session handle.

    The handle keeps a stable SDK session id while each prompt still executes as
    a stored run, which keeps the wrapper decoupled from the kernel runtime.
    """

    client: AgentSDKClient
    session_id: str
    options: SDKOptions

    async def query(
        self,
        prompt: str,
        options: SDKOptions | dict[str, Any] | None = None,
    ) -> AsyncIterator[SDKMessage]:
        merged = _merge_session_options(self.options, options, session_id=self.session_id)
        last_result: SDKResultMessage | None = None
        async for message in self.client.query(prompt, merged):
            if isinstance(message, SDKResultMessage):
                last_result = message
            yield message
        if last_result is not None and last_result.stop_reason == "awaiting_approval":
            return
        async for message in self._drain_async_messages(merged):
            yield message

    async def _drain_async_messages(self, options: SDKOptions) -> AsyncIterator[SDKMessage]:
        while True:
            queued = self.client.dequeue_async_message(session_id=self.session_id)
            if queued is None:
                return
            async for message in self.client.query_user_message(queued, options):
                yield message

    async def prompt(
        self,
        prompt: str,
        options: SDKOptions | dict[str, Any] | None = None,
    ) -> SDKResultMessage:
        result: SDKResultMessage | None = None
        async for message in self.query(prompt, options):
            if isinstance(message, SDKResultMessage):
                result = message
        if result is None:
            raise RuntimeError("SDK session prompt completed without a result message")
        return result

    def enqueue_async_message(
        self,
        message: SDKUserMessage | dict[str, Any] | str,
        *,
        priority: Literal["now", "next", "later"] | None = None,
    ) -> SDKUserMessage:
        return self.client.enqueue_async_message(message, session_id=self.session_id, priority=priority)

    def list_async_messages(self) -> list[SDKUserMessage]:
        return self.client.list_async_messages(session_id=self.session_id)

    def dequeue_async_message(self) -> SDKUserMessage | None:
        return self.client.dequeue_async_message(session_id=self.session_id)

    async def messages(
        self,
        options: SDKGetSessionMessagesOptions | dict[str, Any] | None = None,
    ) -> list[SDKMessage]:
        return await self.client.get_session_messages(self.session_id, options)

    async def info(self) -> SDKSessionInfo | None:
        return await self.client.get_session_info(self.session_id)

    async def rename(self, title: str) -> None:
        await self.client.rename_session(self.session_id, title)

    async def tag(self, tag: str | None) -> None:
        await self.client.tag_session(self.session_id, tag)

    async def fork(self, options: SDKForkSessionOptions | dict[str, Any] | None = None) -> "SDKSession":
        result = await self.client.fork_session(self.session_id, options)
        return await self.client.resume_session(result.session_id)

    async def handle_control_request(
        self,
        message: SDKControlRequest | dict[str, Any],
    ) -> SDKControlResponse:
        control = validate_sdk_control_request(message)
        self.options = _apply_session_control_request(self.options, control.request)
        return await self.client.handle_control_request(control, self.options)


async def query(prompt: str, options: SDKOptions | dict[str, Any] | None = None) -> AsyncIterator[SDKMessage]:
    client = AgentSDKClient()
    async for message in client.query(prompt, options):
        yield message


async def prompt(prompt: str, options: SDKOptions | dict[str, Any] | None = None) -> SDKResultMessage:
    return await AgentSDKClient().prompt(prompt, options)


async def list_sessions(options: SDKListSessionsOptions | dict[str, Any] | None = None) -> list[SDKSessionInfo]:
    return await AgentSDKClient().list_sessions(options)


async def get_session_info(session_id: str) -> SDKSessionInfo | None:
    return await AgentSDKClient().get_session_info(session_id)


async def get_session_messages(
    session_id: str,
    options: SDKGetSessionMessagesOptions | dict[str, Any] | None = None,
) -> list[SDKMessage]:
    return await AgentSDKClient().get_session_messages(session_id, options)


async def rename_session(session_id: str, title: str) -> None:
    await AgentSDKClient().rename_session(session_id, title)


async def tag_session(session_id: str, tag: str | None) -> None:
    await AgentSDKClient().tag_session(session_id, tag)


async def fork_session(
    session_id: str,
    options: SDKForkSessionOptions | dict[str, Any] | None = None,
) -> SDKForkSessionResult:
    return await AgentSDKClient().fork_session(session_id, options)


async def handle_control_request(
    message: SDKControlRequest | dict[str, Any],
    options: SDKOptions | dict[str, Any] | None = None,
) -> SDKControlResponse:
    return await AgentSDKClient().handle_control_request(message, options)


async def run_stdin(
    messages: AsyncIterable[SDKStdinMessage | dict[str, Any]] | Iterable[SDKStdinMessage | dict[str, Any]],
    options: SDKOptions | dict[str, Any] | None = None,
    structured_io: SDKStructuredIO | None = None,
) -> AsyncIterator[SDKStdoutMessage]:
    async for message in AgentSDKClient().run_stdin(messages, options, structured_io=structured_io):
        yield message


def unstable_v2_create_session(options: SDKOptions | dict[str, Any] | None = None) -> SDKSession:
    return AgentSDKClient().create_sdk_session(options)


async def unstable_v2_resume_session(
    session_id: str,
    options: SDKOptions | dict[str, Any] | None = None,
) -> SDKSession:
    return await AgentSDKClient().resume_session(session_id, options)


async def unstable_v2_prompt(
    prompt: str,
    options: SDKOptions | dict[str, Any] | None = None,
) -> SDKResultMessage:
    return await AgentSDKClient().prompt(prompt, _coerce_options(options))


def _coerce_options(options: SDKOptions | dict[str, Any] | None) -> SDKOptions:
    if options is None:
        return SDKOptions()
    if isinstance(options, SDKOptions):
        return options
    return SDKOptions.model_validate(options)


async def _aiter_stdin_messages(
    messages: AsyncIterable[SDKStdinMessage | dict[str, Any]] | Iterable[SDKStdinMessage | dict[str, Any]],
) -> AsyncIterator[SDKStdinMessage | dict[str, Any]]:
    if hasattr(messages, "__aiter__"):
        async for message in messages:  # type: ignore[union-attr]
            yield message
        return
    for message in messages:  # type: ignore[union-attr]
        yield message


async def _anext(iterator: AsyncIterator[SDKStdinMessage | dict[str, Any]]) -> SDKStdinMessage | dict[str, Any]:
    return await iterator.__anext__()


def _apply_environment_variables_update(options: SDKOptions, message: SDKUpdateEnvironmentVariablesMessage) -> None:
    current = options.metadata.get("environment_variables")
    variables = dict(current) if isinstance(current, dict) else {}
    variables.update(message.variables)
    options.metadata["environment_variables"] = variables
    os.environ.update(message.variables)


def _replay_user_messages_enabled(options: SDKOptions) -> bool:
    return bool(
        options.replay_user_messages
        or options.metadata.get("replay_user_messages")
        or options.metadata.get("replayUserMessages")
    )


def _coerce_async_user_message(
    message: SDKUserMessage | dict[str, Any] | str,
    *,
    session_id: str = "",
    priority: Literal["now", "next", "later"] | None = None,
) -> SDKUserMessage:
    if isinstance(message, SDKUserMessage):
        values = message.model_dump()
    elif isinstance(message, dict):
        values = dict(message)
    else:
        values = {
            "type": "user",
            "session_id": session_id,
            "uuid": "msg_%s" % uuid.uuid4().hex,
            "message": {"role": "user", "content": [{"type": "text", "text": str(message)}]},
            "priority": priority,
            "isReplay": False,
        }
    if session_id:
        values["session_id"] = session_id
    values.setdefault("type", "user")
    values.setdefault("session_id", session_id)
    values["uuid"] = str(values.get("uuid") or "msg_%s" % uuid.uuid4().hex)
    if priority is not None:
        values["priority"] = priority
    elif not values.get("priority"):
        values["priority"] = "next"
    if "message" not in values:
        values["message"] = {"role": "user", "content": []}
    values.setdefault("isReplay", False)
    return SDKUserMessage.model_validate(values)


def _sorted_async_message_items(items: list[_SDKAsyncMessageQueueItem]) -> list[_SDKAsyncMessageQueueItem]:
    return sorted(items, key=lambda item: (_async_message_priority(item.message.priority), item.sequence))


def _async_message_priority(value: str | None) -> int:
    if value == "now":
        return 0
    if value == "later":
        return 2
    return 1


def _merge_session_options(
    base: SDKOptions,
    override: SDKOptions | dict[str, Any] | None,
    *,
    session_id: str,
) -> SDKOptions:
    values = base.model_dump()
    if override is not None:
        override_options = _coerce_options(override)
        for key in override_options.model_fields_set:
            if key == "metadata":
                values["metadata"] = {
                    **values.get("metadata", {}),
                    **override_options.metadata,
                }
            else:
                values[key] = getattr(override_options, key)
    values["session_id"] = session_id
    return SDKOptions.model_validate(values)


def _apply_session_control_request(options: SDKOptions, request: SDKControlRequestInner) -> SDKOptions:
    if isinstance(request, SDKControlSetModelRequest):
        return options.model_copy(update={"model": request.model})
    if isinstance(request, SDKControlSetPermissionModeRequest):
        return options.model_copy(update={"permission_mode": request.mode})
    if isinstance(request, SDKControlApplyFlagSettingsRequest):
        return _apply_control_settings(options, request.settings)
    return options


def _apply_control_settings(options: SDKOptions, settings: dict[str, Any]) -> SDKOptions:
    values = options.model_dump()
    if "model" in settings:
        values["model"] = str(settings.get("model") or "") or None
    if "permissionMode" in settings:
        values["permission_mode"] = str(settings.get("permissionMode") or "") or None
    if "permission_mode" in settings:
        values["permission_mode"] = str(settings.get("permission_mode") or "") or None
    if "systemPrompt" in settings:
        values["system_prompt"] = str(settings.get("systemPrompt") or "") or None
    if "system_prompt" in settings:
        values["system_prompt"] = str(settings.get("system_prompt") or "") or None
    metadata = dict(values.get("metadata") or {})
    metadata["flagSettings"] = dict(settings)
    values["metadata"] = metadata
    return SDKOptions.model_validate(values)


def _coerce_list_sessions_options(options: SDKListSessionsOptions | dict[str, Any] | None) -> SDKListSessionsOptions:
    if options is None:
        return SDKListSessionsOptions()
    if isinstance(options, SDKListSessionsOptions):
        return options
    return SDKListSessionsOptions.model_validate(options)


def _coerce_get_session_messages_options(
    options: SDKGetSessionMessagesOptions | dict[str, Any] | None,
) -> SDKGetSessionMessagesOptions:
    if options is None:
        return SDKGetSessionMessagesOptions()
    if isinstance(options, SDKGetSessionMessagesOptions):
        return options
    return SDKGetSessionMessagesOptions.model_validate(options)


def _coerce_fork_session_options(options: SDKForkSessionOptions | dict[str, Any] | None) -> SDKForkSessionOptions:
    if options is None:
        return SDKForkSessionOptions()
    if isinstance(options, SDKForkSessionOptions):
        return options
    return SDKForkSessionOptions.model_validate(options)


def _spec_from_options(options: SDKOptions) -> AgentSpec:
    spec = AgentSpec.from_overrides(
        model=options.model,
        protocol=options.protocol,
        workspace_path=options.cwd,
        enabled_tools=options.allowed_tools,
        skills=options.skills,
        system_prompt=options.system_prompt,
        permission_profile=options.permission_mode,
        agent_id=options.agent_id,
        tenant_id=options.tenant_id,
        user_id=options.user_id,
    )
    metadata = dict(options.metadata or {})
    structured_schema = _structured_output_schema_from_options(options)
    if structured_schema is not None:
        metadata["structured_output_schema"] = structured_schema
    if metadata:
        spec = replace(spec, metadata=metadata)
    return spec


def _structured_output_schema_from_options(options: SDKOptions) -> dict[str, Any] | None:
    output_format = options.output_format
    if not isinstance(output_format, dict):
        return None
    if output_format.get("type") != "json_schema":
        return None
    schema = output_format.get("schema")
    return dict(schema) if isinstance(schema, dict) else None


def _user_message_event(
    prompt: str,
    *,
    session_id: str,
    run_id: str,
    user_message: SDKUserMessage | None = None,
) -> RuntimeEvent:
    message_id = str(getattr(user_message, "uuid", "") or "msg_%s" % uuid.uuid4().hex)
    message = (
        dict(user_message.message)
        if user_message is not None
        else {
            "role": "user",
            "content": [{"type": "text", "text": prompt}],
        }
    )
    timestamp = getattr(user_message, "timestamp", None) if user_message is not None else None
    return RuntimeEvent(
        type="user_message",
        name="user",
        payload={
            "uuid": message_id,
            "message_id": message_id,
            "session_id": session_id,
            "run_id": run_id,
            "message": message,
            "content": prompt,
            "parent_tool_use_id": getattr(user_message, "parent_tool_use_id", None) if user_message is not None else None,
            "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
            "isSynthetic": bool(getattr(user_message, "isSynthetic", False)) if user_message is not None else False,
            "tool_use_result": getattr(user_message, "tool_use_result", None) if user_message is not None else None,
            "priority": getattr(user_message, "priority", None) if user_message is not None else None,
            "isReplay": bool(getattr(user_message, "isReplay", True)) if user_message is not None else True,
        },
    )


def _session_state_event(state: str) -> RuntimeEvent:
    return RuntimeEvent(type="session_state_changed", name="session", payload={"state": state})


def _project_session_state_event(
    event: RuntimeEvent,
    *,
    session_id: str,
    run_id: str,
) -> SDKSessionStateChangedMessage:
    state = _session_state(event.payload.get("state"))
    return SDKSessionStateChangedMessage(session_id=session_id, run_id=run_id, state=state)


def _session_infos_from_runs(records: list[RunRecord]) -> list[SDKSessionInfo]:
    grouped: dict[str, list[RunRecord]] = {}
    for record in records:
        grouped.setdefault(_session_id_for_run(record), []).append(record)
    infos = [_session_info_from_runs(items) for items in grouped.values()]
    return sorted(infos, key=lambda item: item.last_modified, reverse=True)


def _session_info_from_runs(records: list[RunRecord]) -> SDKSessionInfo:
    ordered = sorted(records, key=lambda item: item.created_at)
    latest = sorted(records, key=lambda item: item.updated_at, reverse=True)[0]
    metadata = dict(latest.metadata)
    custom_title = str(metadata.get("sdk_title") or metadata.get("custom_title") or metadata.get("title") or "")
    first_prompt = _first_non_empty(record.metadata.get("sdk_first_prompt", "") for record in ordered)
    summary = custom_title or first_prompt or latest.run_id
    info = SDKSessionInfo(
        sessionId=_session_id_for_run(latest),
        summary=summary,
        lastModified=_millis(latest.updated_at),
        createdAt=_millis(ordered[0].created_at),
        customTitle=custom_title or None,
        firstPrompt=first_prompt or None,
        cwd=_first_non_empty(_record_cwd(record) for record in reversed(ordered)),
        tag=str(metadata.get("sdk_tag") or metadata.get("tag") or ""),
    )
    info._status = latest.status.value
    info._latest_run_id = latest.run_id
    info._run_ids = [record.run_id for record in ordered]
    info._metadata = {**metadata, "run_count": len(records)}
    return info


def _session_id_for_run(record: RunRecord) -> str:
    return str(record.metadata.get("sdk_session_id") or record.run_id)


def _runtime_fields_from_run(record: RunRecord) -> tuple[str, str, list[str]]:
    spec = record.spec
    model_spec = spec.get("model") if isinstance(spec.get("model"), dict) else {}
    tools = spec.get("tools") if isinstance(spec.get("tools"), dict) else {}
    enabled_tools = spec.get("enabled_tools")
    if enabled_tools is None:
        enabled_tools = tools.get("enabled_tools") if isinstance(tools, dict) else []
    if not isinstance(enabled_tools, list):
        enabled_tools = []
    return (
        str(model_spec.get("model") or "") if isinstance(model_spec, dict) else "",
        str(model_spec.get("protocol") or "") if isinstance(model_spec, dict) else "",
        [str(item) for item in enabled_tools],
    )


def _initialize_control_response_payload(
    settings: Any,
    options: SDKOptions,
    request: SDKControlInitializeRequest,
) -> dict[str, Any]:
    model = options.model or _default_model_from_settings(settings)
    return {
        "commands": _slash_command_infos(),
        "agents": _agent_infos_from_request(request),
        "output_style": str(options.metadata.get("output_style") or options.metadata.get("outputStyle") or "default"),
        "available_output_styles": ["default"],
        "models": _model_infos(model),
        "account": _account_info_from_options(options),
        "fast_mode_state": options.metadata.get("fast_mode_state", options.metadata.get("fastModeState")),
    }


async def _permission_control_response_payload(
    request: SDKControlPermissionRequest,
    options: SDKOptions,
) -> dict[str, Any]:
    policy = build_tool_permission_policy(_spec_from_options(options))
    decision = await policy.authorize(
        ToolCall(
            id=request.tool_use_id,
            name=request.tool_name,
            arguments=dict(request.input or {}),
        )
    )
    if decision.requires_approval:
        behavior = "ask"
    elif decision.allowed:
        behavior = "allow"
    else:
        behavior = "deny"
    return {
        "behavior": behavior,
        "allowed": decision.allowed,
        "requires_approval": decision.requires_approval,
        "reason": decision.reason,
        "metadata": decision.metadata,
    }


def _settings_control_response_payload(options: SDKOptions) -> dict[str, Any]:
    effective = {
        "model": options.model,
        "permissionMode": options.permission_mode,
        "systemPrompt": options.system_prompt,
        "cwd": options.cwd,
        "allowedTools": list(options.allowed_tools or []),
        "skills": list(options.skills or []),
    }
    return {
        "effective": {key: value for key, value in effective.items() if value not in (None, "", [])},
        "sources": [{"source": "flagSettings", "settings": dict(options.metadata.get("flagSettings") or {})}],
        "applied": {"model": options.model or "", "effort": None},
    }


def _empty_context_usage_payload(options: SDKOptions) -> dict[str, Any]:
    return {
        "categories": [],
        "totalTokens": 0,
        "maxTokens": 0,
        "rawMaxTokens": 0,
        "percentage": 0,
        "gridRows": [],
        "model": options.model or "",
        "memoryFiles": [],
        "mcpTools": [],
        "isAutoCompactEnabled": False,
        "agents": [],
        "apiUsage": None,
    }


def _slash_command_infos() -> list[dict[str, str]]:
    return [
        {
            "name": command.name.lstrip("/"),
            "description": command.action,
            "argumentHint": command.argument_hint,
        }
        for command in COMMANDS
    ]


def _agent_infos_from_request(request: SDKControlInitializeRequest) -> list[dict[str, str]]:
    agents = request.agents or {}
    infos: list[dict[str, str]] = []
    for name, definition in agents.items():
        payload = definition if isinstance(definition, dict) else {}
        info = {
            "name": str(name),
            "description": str(payload.get("description") or payload.get("prompt") or ""),
        }
        model = str(payload.get("model") or "")
        if model:
            info["model"] = model
        infos.append(info)
    return infos


def _model_infos(model: str) -> list[dict[str, Any]]:
    value = model or "default"
    return [{"value": value, "displayName": value, "description": "Configured SDK model"}]


def _account_info_from_options(options: SDKOptions) -> dict[str, str]:
    source = _api_key_source(options.metadata.get("apiKeySource", options.metadata.get("api_key_source")))
    return {"apiKeySource": source}


def _default_model_from_settings(settings: Any) -> str:
    agent_model = str(getattr(getattr(settings, "agent", None), "CLAUDE_MODEL", "") or "")
    if agent_model:
        return agent_model
    models = getattr(settings, "models", None)
    for name in ("anthropic", "openai", "openai_responses", "gemini"):
        value = str(getattr(getattr(models, name, None), "MODEL", "") or "")
        if value:
            return value
    return ""


def _mcp_record_from_control_config(
    name: str,
    config: dict[str, Any],
    *,
    tenant_id: str,
    user_id: str,
    agent_id: str,
    workspace_id: str,
) -> MCPServerRecord:
    transport = str(config.get("type") or "stdio")
    args = config.get("args") if isinstance(config.get("args"), list) else []
    command_parts = [str(config.get("command") or ""), *[str(arg) for arg in args]]
    command = " ".join(part for part in command_parts if part).strip()
    headers = config.get("headers") if isinstance(config.get("headers"), dict) else {}
    return MCPServerRecord(
        name=name,
        command=command,
        transport=transport,
        url=str(config.get("url") or ""),
        headers={str(key): str(value) for key, value in headers.items()},
        enabled=True,
        tenant_id=tenant_id,
        user_id=user_id,
        agent_id=agent_id,
        workspace_id=workspace_id,
    )


def _task_in_sdk_scope(task: TaskRecord, options: SDKOptions) -> bool:
    return (
        task.tenant_id == (options.tenant_id or "")
        and task.user_id in ("", options.user_id or "")
        and task.agent_id in ("", options.agent_id or "")
    )


def _task_id_matches(task_id: str, target: str) -> bool:
    return task_id == target or task_id.replace("task_", "", 1).startswith(target)


def _sdk_task_payload(task: TaskRecord) -> dict[str, Any]:
    return {
        "task_id": task.task_id,
        "short_id": task.task_id.replace("task_", "", 1)[:12],
        "title": task.title,
        "input": task.input,
        "status": task.status.value,
        "agent_id": task.agent_id,
        "workspace_id": task.workspace_id,
        "metadata": dict(task.metadata),
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }


def _sdk_system_message(
    *,
    session_id: str,
    run_id: str,
    cwd: str,
    model: str,
    tools: list[str],
    skills: list[str],
    permission_mode: str | None,
    metadata: dict[str, Any],
    mcp_servers: list[dict[str, str]],
) -> SDKSystemMessage:
    return SDKSystemMessage(
        session_id=session_id,
        run_id=run_id,
        agents=_metadata_string_list(metadata, "agents", "sdk_agents"),
        apiKeySource=_api_key_source(metadata.get("apiKeySource", metadata.get("api_key_source"))),
        betas=_metadata_string_list(metadata, "betas", "sdk_betas"),
        claude_code_version=_text_field(metadata, "claude_code_version", "sdk_version") or _SDK_VERSION,
        cwd=cwd,
        tools=tools,
        mcp_servers=mcp_servers,
        model=model,
        permissionMode=_permission_mode(metadata.get("permissionMode", permission_mode)),
        slash_commands=_metadata_string_list(metadata, "slash_commands", "slashCommands") or command_names(),
        output_style=_text_field(metadata, "output_style", "outputStyle") or "default",
        skills=_metadata_string_list(metadata, "skills", "sdk_skills") or skills,
        plugins=_plugin_list_field(metadata.get("plugins", metadata.get("sdk_plugins"))),
        fast_mode_state=_fast_mode_state(metadata.get("fast_mode_state", metadata.get("fastModeState"))),
        uuid=_text_field(metadata, "uuid", "message_id", "messageId") or str(uuid.uuid4()),
    )


def _api_key_source(value: Any) -> Literal["user", "project", "org", "temporary", "oauth"]:
    text = str(value or "")
    if text in {"user", "project", "org", "temporary", "oauth"}:
        return text
    return "project"


def _permission_mode(value: Any) -> Literal["default", "acceptEdits", "bypassPermissions", "plan", "dontAsk"]:
    text = str(value or "")
    if text in {"default", "acceptEdits", "bypassPermissions", "plan", "dontAsk"}:
        return text
    normalized = text.strip().lower().replace("_", "-")
    if normalized in {"accept-edits", "acceptedits"}:
        return "acceptEdits"
    if normalized in {"bypass", "bypass-permissions", "bypasspermissions"}:
        return "bypassPermissions"
    if normalized in {"deny", "dont-ask", "dontask"}:
        return "dontAsk"
    if normalized == "plan":
        return "plan"
    return "default"


def _fast_mode_state(value: Any) -> Literal["off", "cooldown", "on"] | None:
    text = str(value or "")
    if text in {"off", "cooldown", "on"}:
        return text
    return None


def _metadata_string_list(metadata: dict[str, Any], *keys: str) -> list[str]:
    for key in keys:
        value = metadata.get(key)
        if isinstance(value, list):
            return [str(item) for item in value if str(item or "")]
        if isinstance(value, str) and value:
            parsed = _json_list(value)
            if parsed:
                return [str(item) for item in parsed if str(item or "")]
    return []


def _plugin_list_field(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    plugins: list[dict[str, str]] = []
    for item in value:
        if isinstance(item, str):
            if item:
                plugins.append({"name": item, "path": ""})
            continue
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "")
        if not name:
            continue
        plugin = {"name": name, "path": str(item.get("path") or "")}
        source = str(item.get("source") or "")
        if source:
            plugin["source"] = source
        plugins.append(plugin)
    return plugins


def _settings_mcp_server_statuses(settings: Any) -> list[dict[str, str]]:
    mcp = getattr(settings, "mcp", None)
    if mcp is None:
        return []
    name = str(getattr(mcp, "SERVER_NAME", "") or "default")
    transport = str(getattr(mcp, "SERVER_TRANSPORT", "stdio") or "stdio")
    command = str(getattr(mcp, "SERVER_COMMAND", "") or "").strip()
    url = str(getattr(mcp, "SERVER_URL", "") or "").strip()
    auth_required = bool(getattr(mcp, "AUTH_REQUIRED", False))
    if transport == "stdio" and not command and not auth_required:
        return []
    if transport != "stdio" and not url and not auth_required:
        return []
    return [{"name": name, "status": _mcp_status(enabled=True, auth_required=auth_required, auth_status=getattr(mcp, "AUTH_STATUS", ""))}]


def _mcp_server_status_from_record(record: MCPServerRecord) -> dict[str, str]:
    return {
        "name": record.name,
        "status": _mcp_status(
            enabled=record.enabled,
            auth_required=record.auth_required,
            auth_status=record.auth_status,
        ),
    }


def _mcp_status(*, enabled: bool, auth_required: bool, auth_status: Any) -> str:
    if not enabled:
        return "disabled"
    status = str(auth_status or "").strip().lower()
    if auth_required and status not in {"authenticated", "connected", "ok", "ready"}:
        return "needs-auth"
    if status in {"failed", "error"}:
        return "failed"
    if status == "pending":
        return "pending"
    return "connected"


def _merge_mcp_server_statuses(
    base: list[dict[str, str]],
    extra: list[dict[str, str]],
) -> list[dict[str, str]]:
    merged: dict[str, dict[str, str]] = {}
    for item in [*base, *extra]:
        name = str(item.get("name") or "")
        if name:
            merged[name] = {"name": name, "status": str(item.get("status") or "connected")}
    return sorted(merged.values(), key=lambda item: item["name"])


def _record_cwd(record: RunRecord) -> str:
    if record.metadata.get("sdk_cwd"):
        return str(record.metadata["sdk_cwd"])
    workspace = record.spec.get("workspace") if isinstance(record.spec.get("workspace"), dict) else {}
    if isinstance(workspace, dict):
        return str(workspace.get("path") or workspace.get("root") or "")
    return ""


def _duration_ms_from_record(record: RunRecord) -> int:
    return int(max(0, record.updated_at - record.created_at) * 1000)


def _events_for_fork(events: list[RuntimeEvent], up_to_message_id: str = "") -> tuple[list[RuntimeEvent], bool]:
    if not up_to_message_id:
        return list(events), False
    copied: list[RuntimeEvent] = []
    for event in events:
        copied.append(event)
        if _event_matches_message_id(event, up_to_message_id):
            return copied, True
    return copied, False


def _event_matches_message_id(event: RuntimeEvent, message_id: str) -> bool:
    candidates = {
        str(event.payload.get("uuid") or ""),
        str(event.payload.get("message_id") or ""),
        str(event.payload.get("id") or ""),
        str(event.payload.get("tool_call_id") or ""),
        str(event.payload.get("approval_id") or ""),
    }
    raw = event.raw if isinstance(event.raw, dict) else {}
    candidates.update(
        {
            str(raw.get("uuid") or ""),
            str(raw.get("message_id") or ""),
            str(raw.get("id") or ""),
        }
    )
    return message_id in candidates


def _rewind_entries_after_message(
    records: list[RunRecord],
    message_id: str,
) -> tuple[list[_RewindFileEntry], list[str], bool]:
    found_message = False
    entries_by_path: dict[str, _RewindFileEntry] = {}
    unsupported_paths: set[str] = set()
    read_cache: dict[str, str] = {}
    for record in sorted(records, key=lambda item: item.created_at):
        for event in record.events:
            if not found_message:
                if _event_matches_message_id(event, message_id):
                    found_message = True
                continue
            if event.type != "tool_result":
                continue
            payload = _tool_result_payload_data(event.payload)
            read_path, read_content = _read_content_from_tool_result(event, payload)
            if read_path:
                read_cache[read_path] = read_content
                continue
            entries, unsupported = _rewind_entries_from_tool_result(event, payload, read_cache)
            unsupported_paths.update(path for path in unsupported if path not in entries_by_path)
            for entry in entries:
                if entry.path in unsupported_paths:
                    continue
                existing = entries_by_path.get(entry.path)
                if existing is None:
                    entries_by_path[entry.path] = entry
                    continue
                existing.insertions += entry.insertions
                existing.deletions += entry.deletions
    entries = [entries_by_path[path] for path in sorted(entries_by_path)]
    return entries, sorted(unsupported_paths), found_message


def _read_content_from_tool_result(event: RuntimeEvent, payload: dict[str, Any]) -> tuple[str, str]:
    if str(event.name or "") not in {"filesystem.read", "Read"}:
        return "", ""
    file_payload = payload.get("file") if isinstance(payload.get("file"), dict) else {}
    path = _rewind_path_value(file_payload.get("filePath") or payload.get("path"))
    content = file_payload.get("content") if "content" in file_payload else payload.get("content")
    if not path or not isinstance(content, str):
        return "", ""
    if payload.get("truncated") or payload.get("isPartialView"):
        return "", ""
    return path, content


def _rewind_entries_from_tool_result(
    event: RuntimeEvent,
    payload: dict[str, Any],
    read_cache: dict[str, str],
) -> tuple[list[_RewindFileEntry], list[str]]:
    name = str(event.name or "")
    if payload.get("dry_run") is True or payload.get("changed") is False:
        return [], []
    if name in {"patch.apply", "Edit"}:
        return _rewind_entries_from_patch_payload(payload)
    if name in {"notebook.edit", "NotebookEdit"}:
        entry = _rewind_entry_from_notebook_payload(payload)
        return ([entry], []) if entry is not None else ([], [])
    if name in {"filesystem.write", "Write"}:
        entry, unsupported = _rewind_entry_from_write_payload(payload, read_cache)
        return ([entry], []) if entry is not None else ([], unsupported)
    return [], []


def _rewind_entries_from_patch_payload(payload: dict[str, Any]) -> tuple[list[_RewindFileEntry], list[str]]:
    entries: list[_RewindFileEntry] = []
    unsupported_paths: set[str] = set()
    supported_paths: set[str] = set()
    path = _rewind_path_value(payload.get("filePath") or payload.get("path"))
    before = payload.get("originalFile")
    if path and isinstance(before, str):
        after = _patch_after_content(payload, before)
        insertions, deletions = _change_stats(payload.get("structuredPatch"), before, after)
        entries.append(
            _RewindFileEntry(
                path=path,
                before=before,
                existed=True,
                encoding=str(payload.get("encoding") or "utf-8"),
                insertions=insertions,
                deletions=deletions,
            )
        )
        supported_paths.add(path)

    files = payload.get("files") if isinstance(payload.get("files"), list) else []
    for item in files:
        if not isinstance(item, dict):
            continue
        item_path = _rewind_path_value(item.get("path") or item.get("filePath"))
        if not item_path or item_path in supported_paths:
            continue
        action = str(item.get("action") or "")
        if action == "create":
            insertions, deletions = _change_stats(_structured_patch_for_path(payload, item_path), "", None)
            entries.append(
                _RewindFileEntry(
                    path=item_path,
                    before="",
                    existed=False,
                    encoding=str(payload.get("encoding") or "utf-8"),
                    insertions=insertions,
                    deletions=deletions,
                )
            )
            supported_paths.add(item_path)
        elif action == "edit":
            unsupported_paths.add(item_path)

    if not files and payload.get("structuredPatches") and not supported_paths:
        for item in payload.get("structuredPatches") or []:
            if isinstance(item, dict):
                item_path = _rewind_path_value(item.get("filePath") or item.get("path"))
                if item_path:
                    unsupported_paths.add(item_path)
    return entries, sorted(unsupported_paths)


def _rewind_entry_from_notebook_payload(payload: dict[str, Any]) -> _RewindFileEntry | None:
    path = _rewind_path_value(payload.get("notebook_path") or payload.get("path") or payload.get("filePath"))
    before = payload.get("original_file") if "original_file" in payload else payload.get("originalFile")
    after = payload.get("updated_file") if "updated_file" in payload else payload.get("updatedFile")
    if not path or not isinstance(before, str):
        return None
    insertions, deletions = _change_stats(None, before, after if isinstance(after, str) else None)
    return _RewindFileEntry(
        path=path,
        before=before,
        existed=True,
        encoding=str(payload.get("encoding") or "utf-8"),
        insertions=insertions,
        deletions=deletions,
    )


def _rewind_entry_from_write_payload(
    payload: dict[str, Any],
    read_cache: dict[str, str],
) -> tuple[_RewindFileEntry | None, list[str]]:
    path = _rewind_path_value(payload.get("path") or payload.get("filePath"))
    if not path:
        return None, []
    safety = payload.get("safety") if isinstance(payload.get("safety"), dict) else {}
    existed = bool(safety.get("required_prior_read"))
    encoding = str(payload.get("encoding") or safety.get("encoding") or "utf-8")
    if not existed:
        return _RewindFileEntry(path=path, before="", existed=False, encoding=encoding), []
    before = read_cache.get(path)
    if before is None:
        return None, [path]
    return _RewindFileEntry(path=path, before=before, existed=True, encoding=encoding), []


def _rewind_response_payload(entries: list[_RewindFileEntry]) -> dict[str, Any]:
    ordered = sorted(entries, key=lambda item: item.path)
    return {
        "canRewind": True,
        "filesChanged": [entry.path for entry in ordered],
        "insertions": sum(max(0, entry.insertions) for entry in ordered),
        "deletions": sum(max(0, entry.deletions) for entry in ordered),
    }


def _rewind_workspace_root(options: SDKOptions, records: list[RunRecord]) -> Path:
    root = str(options.cwd or "")
    if not root:
        root = _first_non_empty(_record_cwd(record) for record in reversed(records))
    return Path(root or ".").resolve()


def _safe_workspace_path(root: Path, path: str) -> Path:
    target = Path(path)
    resolved = target.resolve() if target.is_absolute() else (root / target).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError("path escapes workspace: %s" % path) from exc
    return resolved


def _safe_rewind_path(root: Path, path: str) -> Path:
    try:
        return _safe_workspace_path(root, path)
    except ValueError as exc:
        raise ValueError("rewind path escapes workspace: %s" % path) from exc


def _apply_rewind_entry(entry: _RewindFileEntry, target: Path) -> None:
    if not entry.existed:
        if target.exists():
            if target.is_dir():
                raise ValueError("cannot rewind file path because it is a directory: %s" % entry.path)
            target.unlink()
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(entry.before, encoding=entry.encoding or "utf-8")


def _rewind_path_value(value: Any) -> str:
    path = str(value or "").strip()
    if path.startswith("./"):
        path = path[2:]
    return path


def _read_state_seed_key(options: SDKOptions) -> str:
    return str(options.session_id or "")


def _is_seed_observation_stale(disk_mtime: float, observed_mtime: float) -> bool:
    observed = float(observed_mtime or 0.0)
    if observed > 10_000_000_000:
        return int(disk_mtime * 1000) > int(observed)
    return disk_mtime > observed


def _read_seed_text(path: Path) -> tuple[str, str]:
    with path.open("rb") as handle:
        data = handle.read(MAX_SDK_SEED_READ_BYTES + 1)
    if len(data) > MAX_SDK_SEED_READ_BYTES:
        raise ValueError("file is too large to seed read state: %s" % path)
    encoding = detect_text_encoding(path, data[:BINARY_SAMPLE_BYTES])
    return decode_text_bytes(data, encoding), public_encoding_name(encoding)


def _patch_after_content(payload: dict[str, Any], before: str) -> str | None:
    old = payload.get("oldString")
    new = payload.get("newString")
    if isinstance(old, str) and isinstance(new, str) and old in before:
        return before.replace(old, new, 1)
    return None


def _structured_patch_for_path(payload: dict[str, Any], path: str) -> list[dict[str, Any]] | None:
    patches = payload.get("structuredPatches")
    if not isinstance(patches, list):
        return None
    for item in patches:
        if not isinstance(item, dict):
            continue
        item_path = _rewind_path_value(item.get("filePath") or item.get("path"))
        if item_path == path and isinstance(item.get("hunks"), list):
            return list(item["hunks"])
    return None


def _change_stats(patch: Any, before: str, after: str | None) -> tuple[int, int]:
    insertions, deletions = _structured_patch_stats(patch)
    if insertions or deletions or after is None:
        return insertions, deletions
    return _text_change_stats(before, after)


def _structured_patch_stats(patch: Any) -> tuple[int, int]:
    if not isinstance(patch, list):
        return 0, 0
    insertions = 0
    deletions = 0
    for hunk in patch:
        if not isinstance(hunk, dict):
            continue
        for line in hunk.get("lines") or []:
            text = str(line)
            if text.startswith("+"):
                insertions += 1
            elif text.startswith("-"):
                deletions += 1
    return insertions, deletions


def _text_change_stats(before: str, after: str) -> tuple[int, int]:
    insertions = 0
    deletions = 0
    matcher = difflib.SequenceMatcher(a=before.splitlines(), b=after.splitlines(), autojunk=False)
    for tag, old_start, old_end, new_start, new_end in matcher.get_opcodes():
        if tag in {"replace", "delete"}:
            deletions += old_end - old_start
        if tag in {"replace", "insert"}:
            insertions += new_end - new_start
    return insertions, deletions


def _assistant_api_message(payload: dict[str, Any]) -> dict[str, Any]:
    message = payload.get("message")
    if isinstance(message, dict):
        return dict(message)
    raw = payload.get("raw")
    if isinstance(raw, dict) and isinstance(raw.get("message"), dict):
        return dict(raw["message"])
    content = str(payload.get("content") or "")
    return {
        "id": str(payload.get("message_id") or payload.get("id") or "msg_%s" % uuid.uuid4().hex),
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": content}] if content else [],
        "model": str(payload.get("model") or ""),
        "stop_reason": payload.get("stop_reason"),
        "stop_sequence": payload.get("stop_sequence"),
        "usage": payload.get("usage") if isinstance(payload.get("usage"), dict) else {},
    }


def _assistant_error(value: Any) -> Literal[
    "authentication_failed",
    "billing_error",
    "rate_limit",
    "invalid_request",
    "server_error",
    "unknown",
    "max_output_tokens",
] | None:
    text = str(value or "")
    if text in {
        "authentication_failed",
        "billing_error",
        "rate_limit",
        "invalid_request",
        "server_error",
        "unknown",
        "max_output_tokens",
    }:
        return text
    return None


def _user_message_priority(value: Any) -> str | None:
    text = str(value or "")
    return text if text in {"now", "next", "later"} else None


def _session_state(value: Any) -> str:
    text = str(value or "")
    return text if text in {"idle", "running", "requires_action"} else "idle"


def _result_message_from_done(
    payload: dict[str, Any],
    *,
    session_id: str,
    run_id: str,
    duration_ms: int,
    num_turns: int,
) -> SDKResultMessage:
    status = str(payload.get("status") or payload.get("stop_reason") or payload.get("stopReason") or "finished")
    errors = _string_list_field(payload.get("errors"))
    error = _text_field(payload, "error")
    if error and not errors:
        errors = [error]
    is_error = bool(payload.get("is_error", payload.get("isError", False))) or bool(errors) or status == "error"
    result = payload["result"] if "result" in payload else payload.get("content", "")
    return SDKResultMessage(
        session_id=session_id,
        run_id=run_id,
        subtype=_result_subtype(payload.get("subtype"), is_error=is_error),
        duration_ms=_int(payload.get("duration_ms", payload.get("durationMs", duration_ms))),
        duration_api_ms=_int(payload.get("duration_api_ms", payload.get("durationApiMs", 0))),
        is_error=is_error,
        num_turns=_int(payload.get("num_turns", payload.get("numTurns", num_turns))),
        result=str(result or ""),
        stop_reason=_nullable_text_field(payload, "stop_reason", "stopReason") or status,
        total_cost_usd=_float(payload.get("total_cost_usd", payload.get("totalCostUsd", 0))),
        usage=_dict_field(payload.get("usage")),
        modelUsage=_dict_field(payload.get("modelUsage", payload.get("model_usage"))),
        permission_denials=_dict_list_field(payload.get("permission_denials", payload.get("permissionDenials"))),
        structured_output=payload.get("structured_output", payload.get("structuredOutput")),
        fast_mode_state=_optional_dict_field(payload.get("fast_mode_state", payload.get("fastModeState"))),
        errors=errors,
        uuid=_text_field(payload, "uuid", "message_id", "messageId") or str(uuid.uuid4()),
    )


def _result_subtype(
    value: Any,
    *,
    is_error: bool,
) -> Literal[
    "success",
    "error_during_execution",
    "error_max_turns",
    "error_max_budget_usd",
    "error_max_structured_output_retries",
]:
    text = str(value or "")
    if text in {
        "error_during_execution",
        "error_max_turns",
        "error_max_budget_usd",
        "error_max_structured_output_retries",
    }:
        return text
    return "error_during_execution" if is_error else "success"


def _auth_status_from_tool_result(
    event: RuntimeEvent,
    *,
    session_id: str,
    run_id: str,
) -> SDKAuthStatusMessage | None:
    if not _is_auth_tool_result(event):
        return None
    payload = _tool_result_payload_data(event.payload)
    status = str(payload.get("status") or "")
    auth_url = str(payload.get("authUrl") or payload.get("auth_url") or "")
    message = str(payload.get("message") or "")
    output = [item for item in [message, auth_url] if item]
    if not output and status:
        output = [status]
    error = message if status in {"error", "unsupported"} else ""
    return SDKAuthStatusMessage(
        session_id=session_id,
        run_id=run_id,
        is_authenticating=status == "auth_url",
        output=output,
        error=error,
        metadata={key: value for key, value in payload.items() if key != "_meta"},
    )


def _is_auth_tool_result(event: RuntimeEvent) -> bool:
    if event.type != "tool_result":
        return False
    if str(event.name).endswith("__authenticate"):
        return True
    contract = event.payload.get("contract")
    metadata = contract.get("metadata") if isinstance(contract, dict) else {}
    return bool(isinstance(metadata, dict) and metadata.get("auth_tool"))


def _tool_result_payload_data(payload: dict[str, Any]) -> dict[str, Any]:
    raw = payload.get("raw")
    if isinstance(raw, dict):
        if isinstance(raw.get("result"), str):
            parsed = _json_object(raw["result"])
            if parsed:
                return {**parsed, "_meta": dict(raw.get("_meta") or {})}
        return dict(raw)
    if isinstance(raw, str):
        parsed = _json_object(raw)
        if parsed:
            return parsed
    content = payload.get("content")
    if isinstance(content, str):
        parsed = _json_object(content)
        if parsed:
            return parsed
    return {}


def _json_object(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return dict(parsed) if isinstance(parsed, dict) else {}


def _json_list(value: str) -> list[Any]:
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return []
    return list(parsed) if isinstance(parsed, list) else []


def _task_messages_from_tool_result(
    event: RuntimeEvent,
    *,
    session_id: str,
    run_id: str,
) -> list[SDKMessage]:
    if event.type != "tool_result":
        return []
    payload = _tool_result_payload_data(event.payload)
    task = payload.get("task") if isinstance(payload.get("task"), dict) else {}
    name = str(event.name or "")
    tool_use_id = str(event.payload.get("tool_call_id") or "")
    messages: list[SDKMessage] = []
    if task and _is_task_start_tool(name):
        messages.append(_task_started_message(task, session_id=session_id, run_id=run_id, tool_use_id=tool_use_id))
    if task and _is_task_progress_tool(name):
        messages.append(_task_progress_message(task, payload, session_id=session_id, run_id=run_id, tool_use_id=tool_use_id))
    if task and _is_task_run_tool(name):
        notification = _task_notification_message(task, payload, session_id=session_id, run_id=run_id, tool_use_id=tool_use_id)
        if notification is not None:
            messages.append(notification)
    if name in {"task.backgrounds", "TaskBackgrounds"}:
        for item in payload.get("background_tasks") or []:
            if isinstance(item, dict):
                notification = _background_task_notification(item, session_id=session_id, run_id=run_id)
                if notification is not None:
                    messages.append(notification)
    return messages


def _task_started_message(
    task: dict[str, Any],
    *,
    session_id: str,
    run_id: str,
    tool_use_id: str,
) -> SDKTaskStartedMessage:
    metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
    return SDKTaskStartedMessage(
        session_id=session_id,
        run_id=run_id,
        task_id=str(task.get("task_id") or ""),
        tool_use_id=tool_use_id,
        description=str(task.get("title") or task.get("input") or ""),
        task_type=str(metadata.get("task_type") or metadata.get("type") or ""),
        workflow_name=str(metadata.get("workflow_name") or metadata.get("workflow") or ""),
        prompt=str(task.get("input") or ""),
    )


def _task_progress_message(
    task: dict[str, Any],
    payload: dict[str, Any],
    *,
    session_id: str,
    run_id: str,
    tool_use_id: str,
) -> SDKTaskProgressMessage:
    step = payload.get("step") if isinstance(payload.get("step"), dict) else {}
    return SDKTaskProgressMessage(
        session_id=session_id,
        run_id=run_id,
        task_id=str(task.get("task_id") or ""),
        tool_use_id=tool_use_id,
        description=str(task.get("title") or task.get("input") or ""),
        usage=_task_usage(payload),
        last_tool_name=str(step.get("name") or ""),
        summary=_task_summary(payload, task),
    )


def _task_notification_message(
    task: dict[str, Any],
    payload: dict[str, Any],
    *,
    session_id: str,
    run_id: str,
    tool_use_id: str,
) -> SDKTaskNotificationMessage | None:
    status = _task_notification_status(str(task.get("status") or payload.get("status") or ""))
    if status is None:
        return None
    return SDKTaskNotificationMessage(
        session_id=session_id,
        run_id=run_id,
        task_id=str(task.get("task_id") or ""),
        tool_use_id=tool_use_id,
        status=status,
        output_file=str(payload.get("output_file") or payload.get("outputFile") or ""),
        summary=_task_summary(payload, task),
        usage=_task_usage(payload),
    )


def _background_task_notification(
    item: dict[str, Any],
    *,
    session_id: str,
    run_id: str,
) -> SDKTaskNotificationMessage | None:
    result = item.get("result") if isinstance(item.get("result"), dict) else {}
    task = result.get("task") if isinstance(result.get("task"), dict) else {}
    task_id = str(task.get("task_id") or item.get("task_id") or "")
    status = _task_notification_status(str(result.get("status") or task.get("status") or ""))
    if not task_id or status is None:
        return None
    return SDKTaskNotificationMessage(
        session_id=session_id,
        run_id=run_id,
        task_id=task_id,
        status=status,
        summary=_task_summary(result, task),
        usage=_task_usage(result),
    )


def _is_task_start_tool(name: str) -> bool:
    return name in {"task.create", "TaskCreate", "task.background", "task.run", "Agent", "Task"}


def _is_task_progress_tool(name: str) -> bool:
    return name in {"task.update", "TaskUpdate"}


def _is_task_run_tool(name: str) -> bool:
    return name in {"task.run", "Agent", "Task"}


def _task_notification_status(status: str) -> str | None:
    if status == "finished":
        return "completed"
    if status == "error":
        return "failed"
    if status == "canceled":
        return "stopped"
    return None


def _task_summary(payload: dict[str, Any], task: dict[str, Any]) -> str:
    result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    step = payload.get("step") if isinstance(payload.get("step"), dict) else {}
    return str(
        result.get("content")
        or step.get("output")
        or step.get("error")
        or payload.get("status")
        or task.get("title")
        or ""
    )


def _task_usage(payload: dict[str, Any]) -> dict[str, int]:
    result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
    return {
        "total_tokens": _int(usage.get("total_tokens")),
        "tool_uses": _int(usage.get("tool_uses", result.get("tool_results"))),
        "duration_ms": _int(usage.get("duration_ms")),
    }


def _files_persisted_from_tool_result(
    event: RuntimeEvent,
    *,
    session_id: str,
    run_id: str,
) -> SDKFilesPersistedMessage | None:
    if event.type != "tool_result":
        return None
    payload = _tool_result_payload_data(event.payload)
    artifacts = _artifact_payloads(payload)
    failed = _artifact_failures(payload)
    if not artifacts and not failed:
        return None
    processed_at = _first_non_empty(_artifact_processed_at(artifact) for artifact in artifacts)
    return SDKFilesPersistedMessage(
        session_id=session_id,
        run_id=run_id,
        files=[
            {
                "filename": _artifact_filename(artifact),
                "file_id": str(artifact.get("artifact_id") or artifact.get("file_id") or artifact.get("id") or ""),
            }
            for artifact in artifacts
        ],
        failed=failed,
        processed_at=processed_at or datetime.now(timezone.utc).isoformat(),
    )


def _artifact_payloads(payload: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    artifact = payload.get("artifact")
    if isinstance(artifact, dict):
        result.append(dict(artifact))
    for key in ("artifacts", "files"):
        values = payload.get(key)
        if isinstance(values, list):
            result.extend(dict(item) for item in values if isinstance(item, dict))
    return [item for item in result if item.get("artifact_id") or item.get("file_id") or item.get("id")]


def _artifact_failures(payload: dict[str, Any]) -> list[dict[str, str]]:
    values = payload.get("failed") or payload.get("failed_files") or []
    if not isinstance(values, list):
        return []
    failed: list[dict[str, str]] = []
    for item in values:
        if isinstance(item, dict):
            failed.append(
                {
                    "filename": str(item.get("filename") or item.get("path") or item.get("uri") or ""),
                    "error": str(item.get("error") or item.get("message") or ""),
                }
            )
    return failed


def _artifact_filename(artifact: dict[str, Any]) -> str:
    for key in ("filename", "workspace_path", "path", "uri"):
        value = str(artifact.get(key) or "")
        if value:
            return value.rsplit("/", 1)[-1] if key == "uri" else value
    return str(artifact.get("artifact_id") or artifact.get("file_id") or "artifact")


def _artifact_processed_at(artifact: dict[str, Any]) -> str:
    value = artifact.get("processed_at") or artifact.get("created_at")
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)) and value:
        return datetime.fromtimestamp(float(value), timezone.utc).isoformat()
    return ""


def _retry_attempt(payload: dict[str, Any]) -> int:
    if payload.get("next_attempt") is not None:
        return _int(payload.get("next_attempt"))
    if payload.get("attempt") is not None:
        return _int(payload.get("attempt"))
    return _int(payload.get("failed_attempt")) + 1 if payload.get("failed_attempt") is not None else 0


def _retry_max_attempts(payload: dict[str, Any]) -> int:
    return _int(payload.get("max_attempts") or payload.get("max_retries"))


def _retry_delay_ms(payload: dict[str, Any]) -> int:
    if payload.get("retry_delay_ms") is not None:
        return _int(payload.get("retry_delay_ms"))
    return int(float(payload.get("delay_seconds") or 0) * 1000)


def _retry_error_status(payload: dict[str, Any]) -> int | None:
    value = payload.get("error_status", payload.get("status_code", payload.get("status")))
    if value is None or value == "":
        return None
    return _int(value)


def _retry_error_payload(payload: dict[str, Any]) -> dict[str, Any]:
    error = payload.get("error")
    if isinstance(error, dict):
        return dict(error)
    return {
        "message": str(error or payload.get("message") or "model request failed"),
        "type": str(payload.get("error_type") or payload.get("type") or "unknown"),
    }


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _dict_field(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _optional_dict_field(value: Any) -> dict[str, Any] | None:
    return dict(value) if isinstance(value, dict) else None


def _dict_list_field(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _millis(timestamp: float) -> float:
    return timestamp * 1000


def _truncate(value: str, *, limit: int = 500) -> str:
    value = value.strip()
    return value if len(value) <= limit else value[: limit - 3] + "..."


def _first_non_empty(values) -> str:
    for value in values:
        text = str(value or "")
        if text:
            return text
    return ""


def _project_runtime_event_messages(
    event: RuntimeEvent,
    *,
    session_id: str,
    run_id: str,
    duration_ms: int,
    num_turns: int,
) -> list[SDKMessage]:
    message = _project_runtime_event(
        event,
        session_id=session_id,
        run_id=run_id,
        duration_ms=duration_ms,
        num_turns=num_turns,
    )
    messages = [] if message is None else [message]
    auth_status = _auth_status_from_tool_result(event, session_id=session_id, run_id=run_id)
    if auth_status is not None:
        messages.append(auth_status)
    messages.extend(_task_messages_from_tool_result(event, session_id=session_id, run_id=run_id))
    files_persisted = _files_persisted_from_tool_result(event, session_id=session_id, run_id=run_id)
    if files_persisted is not None:
        messages.append(files_persisted)
    return messages


def _project_runtime_event(
    event: RuntimeEvent,
    *,
    session_id: str,
    run_id: str,
    duration_ms: int,
    num_turns: int,
) -> SDKMessage | None:
    if event.type == "user_message":
        message = dict(event.payload.get("message") or {})
        return SDKUserMessage(
            session_id=session_id,
            run_id=run_id,
            uuid=str(event.payload.get("uuid") or event.payload.get("message_id") or ""),
            message=message,
            parent_tool_use_id=event.payload.get("parent_tool_use_id"),
            isSynthetic=bool(event.payload.get("isSynthetic") or event.payload.get("is_synthetic") or False),
            tool_use_result=event.payload.get("tool_use_result"),
            priority=_user_message_priority(event.payload.get("priority")),
            timestamp=str(event.payload.get("timestamp") or "") or None,
            isReplay=bool(event.payload.get("isReplay", event.payload.get("is_replay", True))),
        )
    if event.type == "model_message":
        return SDKAssistantMessage(
            session_id=session_id,
            run_id=run_id,
            message=_assistant_api_message(event.payload),
            parent_tool_use_id=_nullable_text_field(event.payload, "parent_tool_use_id", "parentToolUseId"),
            error=_assistant_error(event.payload.get("error")),
            uuid=_text_field(event.payload, "uuid", "message_id", "messageId") or str(uuid.uuid4()),
        )
    if event.type == "text_delta":
        return SDKStreamEventMessage(
            session_id=session_id,
            run_id=run_id,
            event=_stream_delta_event("text_delta", event.payload),
            parent_tool_use_id=_nullable_text_field(event.payload, "parent_tool_use_id", "parentToolUseId"),
        )
    if event.type == "reasoning_delta":
        return SDKStreamEventMessage(
            session_id=session_id,
            run_id=run_id,
            event=_stream_delta_event("reasoning_delta", event.payload),
            parent_tool_use_id=_nullable_text_field(event.payload, "parent_tool_use_id", "parentToolUseId"),
        )
    if event.type == "model_retry":
        return SDKAPIRetryMessage(
            session_id=session_id,
            run_id=run_id,
            attempt=_retry_attempt(event.payload),
            max_retries=_retry_max_attempts(event.payload),
            retry_delay_ms=_retry_delay_ms(event.payload),
            error_status=_retry_error_status(event.payload),
            error=_retry_error_payload(event.payload),
            metadata=dict(event.payload),
        )
    if event.type == "rate_limit_event":
        rate_limit_info = event.payload.get("rate_limit_info") or event.payload.get("rateLimitInfo") or {}
        return SDKRateLimitEventMessage(
            session_id=session_id,
            run_id=run_id,
            rate_limit_info=dict(rate_limit_info) if isinstance(rate_limit_info, dict) else {},
            uuid=_text_field(event.payload, "uuid", "message_id", "messageId") or str(uuid.uuid4()),
        )
    if event.type == "compact_boundary":
        return SDKCompactBoundaryMessage(
            session_id=session_id,
            run_id=run_id,
            compact_metadata={
                "trigger": str(event.payload.get("trigger") or "auto"),
                "pre_tokens": _int(event.payload.get("pre_tokens")),
                "post_tokens": _int(event.payload.get("post_tokens")),
                "before_messages": _int(event.payload.get("before_messages")),
                "after_messages": _int(event.payload.get("after_messages")),
                "dropped_messages": _int(event.payload.get("dropped_messages")),
            },
        )
    if event.type == "session_state_changed":
        return _project_session_state_event(event, session_id=session_id, run_id=run_id)
    if event.type == "local_command_output":
        return SDKLocalCommandOutputMessage(
            session_id=session_id,
            run_id=run_id,
            content=_local_command_output_content(event.payload),
            uuid=_text_field(event.payload, "uuid", "message_id", "messageId") or str(uuid.uuid4()),
        )
    if event.type == "tool_use_summary":
        return SDKToolUseSummaryMessage(
            session_id=session_id,
            run_id=run_id,
            summary=str(event.payload.get("summary") or ""),
            preceding_tool_use_ids=_string_list_field(
                event.payload.get("preceding_tool_use_ids", event.payload.get("precedingToolUseIds"))
            ),
            uuid=_text_field(event.payload, "uuid", "message_id", "messageId") or str(uuid.uuid4()),
        )
    if event.type == "elicitation_complete":
        return SDKElicitationCompleteMessage(
            session_id=session_id,
            run_id=run_id,
            mcp_server_name=_text_field(event.payload, "mcp_server_name", "mcpServerName", "server"),
            elicitation_id=_text_field(event.payload, "elicitation_id", "elicitationId", "id"),
            uuid=_text_field(event.payload, "uuid", "message_id", "messageId") or str(uuid.uuid4()),
        )
    if event.type == "prompt_suggestion":
        return SDKPromptSuggestionMessage(
            session_id=session_id,
            run_id=run_id,
            suggestion=str(event.payload.get("suggestion") or ""),
            uuid=_text_field(event.payload, "uuid", "message_id", "messageId") or str(uuid.uuid4()),
        )
    if event.type == "post_turn_summary":
        status_category = event.payload.get("status_category", event.payload.get("statusCategory"))
        return SDKPostTurnSummaryMessage(
            session_id=session_id,
            run_id=run_id,
            summarizes_uuid=_text_field(event.payload, "summarizes_uuid", "summarizesUuid"),
            status_category=_post_turn_status_category(status_category),
            status_detail=_text_field(event.payload, "status_detail", "statusDetail"),
            is_noteworthy=bool(event.payload.get("is_noteworthy", event.payload.get("isNoteworthy", False))),
            title=_text_field(event.payload, "title"),
            description=_text_field(event.payload, "description"),
            recent_action=_text_field(event.payload, "recent_action", "recentAction"),
            needs_action=_text_field(event.payload, "needs_action", "needsAction"),
            artifact_urls=_string_list_field(event.payload.get("artifact_urls", event.payload.get("artifactUrls"))),
            uuid=_text_field(event.payload, "uuid", "message_id", "messageId") or str(uuid.uuid4()),
        )
    if event.type == "hook_started":
        return SDKHookStartedMessage(
            session_id=session_id,
            run_id=run_id,
            hook_id=_text_field(event.payload, "hook_id", "hookId"),
            hook_name=_text_field(event.payload, "hook_name", "hookName"),
            hook_event=_text_field(event.payload, "hook_event", "hookEvent"),
        )
    if event.type == "hook_progress":
        return SDKHookProgressMessage(
            session_id=session_id,
            run_id=run_id,
            hook_id=_text_field(event.payload, "hook_id", "hookId"),
            hook_name=_text_field(event.payload, "hook_name", "hookName"),
            hook_event=_text_field(event.payload, "hook_event", "hookEvent"),
            stdout=_text_field(event.payload, "stdout"),
            stderr=_text_field(event.payload, "stderr"),
            output=_text_field(event.payload, "output"),
        )
    if event.type == "hook_response":
        return SDKHookResponseMessage(
            session_id=session_id,
            run_id=run_id,
            hook_id=_text_field(event.payload, "hook_id", "hookId"),
            hook_name=_text_field(event.payload, "hook_name", "hookName"),
            hook_event=_text_field(event.payload, "hook_event", "hookEvent"),
            output=_text_field(event.payload, "output"),
            stdout=_text_field(event.payload, "stdout"),
            stderr=_text_field(event.payload, "stderr"),
            exit_code=_optional_int(event.payload.get("exit_code", event.payload.get("exitCode"))),
            outcome=_hook_outcome(event.payload.get("outcome")),
        )
    if event.type == "tool_start":
        contract = _tool_contract(event.payload)
        return SDKToolProgressMessage(
            session_id=session_id,
            run_id=run_id,
            tool_call_id=_tool_call_id(event.payload),
            name=event.name,
            status="started",
            input=dict(event.payload.get("arguments") or {}),
            activity=dict(contract.get("activity") or {}),
            target=str(contract.get("target") or ""),
            paths=list(contract.get("paths") or []),
            metadata=dict(contract.get("metadata") or {}),
        )
    if event.type == "tool_result":
        status = "failed" if event.payload.get("error") else "completed"
        contract = _tool_contract(event.payload)
        return SDKToolProgressMessage(
            session_id=session_id,
            run_id=run_id,
            tool_call_id=str(event.payload.get("tool_call_id", "") or ""),
            name=event.name,
            status=status,
            result=dict(event.payload),
            activity=dict(contract.get("activity") or {}),
            target=str(contract.get("target") or ""),
            paths=list(contract.get("paths") or []),
            metadata=dict(contract.get("metadata") or {}),
            error=str(event.payload.get("error", "") or ""),
        )
    if event.type == "tool_approval_required":
        tool_call = dict(event.payload.get("tool_call") or {})
        contract = _tool_contract(event.payload)
        return SDKToolProgressMessage(
            session_id=session_id,
            run_id=run_id,
            tool_call_id=_tool_call_id(tool_call),
            name=event.name,
            status="awaiting_approval",
            input=dict(tool_call.get("arguments") or {}),
            result=dict(event.payload),
            activity=dict(contract.get("activity") or {}),
            target=str(contract.get("target") or ""),
            paths=list(contract.get("paths") or []),
            metadata=dict(contract.get("metadata") or {}),
        )
    if event.type == "tool_approval_decision":
        tool_call = dict(event.payload.get("tool_call") or {})
        contract = _tool_contract(event.payload)
        return SDKToolProgressMessage(
            session_id=session_id,
            run_id=run_id,
            tool_call_id=_tool_call_id(tool_call),
            name=event.name,
            status="completed" if event.payload.get("approved") else "denied",
            result=dict(event.payload),
            activity=dict(contract.get("activity") or {}),
            target=str(contract.get("target") or ""),
            paths=list(contract.get("paths") or []),
            metadata=dict(contract.get("metadata") or {}),
        )
    if event.type == "error":
        return SDKStatusMessage(
            session_id=session_id,
            run_id=run_id,
            status=None,
        )
    if event.type == "done":
        return _result_message_from_done(
            event.payload,
            session_id=session_id,
            run_id=run_id,
            duration_ms=duration_ms,
            num_turns=num_turns,
        )
    return SDKStatusMessage(
        session_id=session_id,
        run_id=run_id,
        status=_sdk_status(event.payload.get("status")),
        permissionMode=_nullable_text_field(event.payload, "permissionMode", "permission_mode"),
    )


def _tool_call_id(payload: dict[str, Any]) -> str:
    return str(payload.get("id") or payload.get("tool_call_id") or uuid.uuid4())


def _tool_contract(payload: dict[str, Any]) -> dict[str, Any]:
    contract = payload.get("contract")
    return dict(contract) if isinstance(contract, dict) else {}


def _local_command_output_content(payload: dict[str, Any]) -> str:
    content = str(payload.get("content") or payload.get("output") or "")
    content = content.replace("<local-command-stdout>", "").replace("</local-command-stdout>", "")
    content = content.replace("<local-command-stderr>", "").replace("</local-command-stderr>", "")
    return content.strip()


def _stream_delta_event(event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    delta = str(payload.get("delta") or "")
    raw = payload.get("event") if isinstance(payload.get("event"), dict) else {}
    if raw:
        return dict(raw)
    if event_type == "reasoning_delta":
        return {
            "type": "content_block_delta",
            "delta": {"type": "thinking_delta", "thinking": delta},
        }
    return {
        "type": "content_block_delta",
        "delta": {"type": "text_delta", "text": delta},
    }


def _text_field(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if value is not None:
            return str(value)
    return ""


def _nullable_text_field(payload: dict[str, Any], *keys: str) -> str | None:
    text = _text_field(payload, *keys)
    return text or None


def _string_list_field(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item or "")]


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return _int(value)


def _hook_outcome(value: Any) -> Literal["success", "error", "cancelled"]:
    text = str(value or "")
    if text == "error":
        return "error"
    if text == "cancelled":
        return "cancelled"
    return "success"


def _post_turn_status_category(value: Any) -> Literal["blocked", "waiting", "completed", "review_ready", "failed"]:
    text = str(value or "")
    if text == "blocked":
        return "blocked"
    if text == "waiting":
        return "waiting"
    if text == "review_ready":
        return "review_ready"
    if text == "failed":
        return "failed"
    return "completed"


def _sdk_status(value: Any) -> Literal["compacting"] | None:
    return "compacting" if str(value or "") == "compacting" else None


def _duration_ms(started_at: float) -> int:
    return int((time.monotonic() - started_at) * 1000)


def _is_sdk_interrupt_cancel(exc: asyncio.CancelledError) -> bool:
    return bool(exc.args) and str(exc.args[0]) == "interrupt"
