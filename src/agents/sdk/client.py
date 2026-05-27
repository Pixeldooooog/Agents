from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import AsyncIterable, AsyncIterator, Callable, Iterable
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Literal

from agents.kernel.assembly import create_agent_session_async
from agents.kernel.config import runtime_settings
from agents.kernel.schema import RuntimeEvent
from agents.kernel.specs import AgentSpec
from agents.kernel.state.runs import RunRecord
from agents.platform.persistence import PlatformPersistence, create_ephemeral_persistence
from agents.platform.sessions import RunService
from agents.sdk.async_messages import (
    _SDKAsyncMessageQueueItem,
    _coerce_async_user_message,
    _sorted_async_message_items,
)
from agents.sdk.control import (
    SDKControlElicitationRequest,
    SDKControlRequest,
    SDKControlResponse,
    SDKHookCallbackRequest,
    SDKKeepAliveMessage,
    SDKStdinMessage,
    SDKStdoutMessage,
    SDKUpdateEnvironmentVariablesMessage,
    validate_sdk_control_request,
    validate_sdk_stdin_message,
)
from agents.sdk.control_handlers import SDKControlHandlersMixin
from agents.sdk.event_projection import (
    _duration_ms,
    _is_sdk_interrupt_cancel,
    _project_runtime_event_messages,
    _project_session_state_event,
    _session_state_event,
    _truncate,
)
from agents.sdk.file_history import (
    _SDKReadStateSeed,
    _events_for_fork,
    _migrate_file_history_events_for_session,
    _rewind_entries_from_file_history_snapshots,
    _sdk_file_history_enabled,
    _sdk_file_history_recorder,
)
from agents.sdk.file_rewind import _record_cwd
from agents.sdk.options import (
    _apply_control_settings,
    _apply_session_control_request,
    _coerce_fork_session_options,
    _coerce_get_session_messages_options,
    _coerce_list_sessions_options,
    _coerce_options,
    _merge_session_options,
    _spec_from_options,
)
from agents.sdk.runtime_io import (
    _aiter_stdin_messages,
    _anext,
    _apply_environment_variables_update,
    _close_transport,
    _iter_transport_chunks,
    _replay_user_messages_enabled,
    _sdk_elicitation_request_from_mcp_params,
)
from agents.sdk.session_records import (
    _duration_ms_from_record,
    _session_info_from_runs,
    _session_id_for_run,
    _session_infos_from_runs,
    _user_message_event,
)
from agents.sdk.structured_io import SDKStructuredIO, encode_stdout_message, iter_stdin_jsonl
from agents.sdk.transports import SDKJsonlTransport
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
IDE_AUTH_HEADER = "X-Claude-Code-Ide-Authorization"


@dataclass
class AgentSDKClient(SDKControlHandlersMixin):
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
    active_turn_sessions: dict[str, Any] = field(default_factory=dict)
    active_sleep_wake_events: dict[str, asyncio.Event] = field(default_factory=dict)
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
            mcp_auth_store=self.persistence.mcp_auth_tokens,
            mcp_elicitation_handler=self._mcp_elicitation_handler,
            sdk_mcp_handlers=self.sdk_mcp_handlers,
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

    async def _mcp_elicitation_handler(self, server_name: str, params: Any) -> dict[str, Any]:
        request = _sdk_elicitation_request_from_mcp_params(server_name, params)
        return await self._run_elicitation_handler(request)

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
        self._wake_active_sleep_for_async_message(queued.session_id)
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

    async def run_stdin_jsonl(
        self,
        chunks: AsyncIterable[str | bytes] | Iterable[str | bytes],
        options: SDKOptions | dict[str, Any] | None = None,
        structured_io: SDKStructuredIO | None = None,
    ) -> AsyncIterator[str]:
        async for message in self.run_stdin(iter_stdin_jsonl(chunks), options, structured_io=structured_io):
            yield encode_stdout_message(message)

    async def run_jsonl_transport(
        self,
        transport: SDKJsonlTransport,
        options: SDKOptions | dict[str, Any] | None = None,
        structured_io: SDKStructuredIO | None = None,
        *,
        close_transport: bool = True,
    ) -> None:
        try:
            async for line in self.run_stdin_jsonl(
                _iter_transport_chunks(transport),
                options,
                structured_io=structured_io,
            ):
                await transport.write(line)
        finally:
            if close_transport:
                await _close_transport(transport)

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
        workspace = getattr(session, "workspace", None)
        workspace_path = str(getattr(workspace, "path", "") or options.cwd or "")
        run = await self.run_service.start(spec)
        run_id = run.run_id
        session_id = options.session_id or run_id
        self._install_sleep_wake_for_turn(session, session_id=session_id, run_id=run_id)
        current_task = asyncio.current_task()
        self.active_turn_sessions[session_id] = session
        self.active_turn_sessions[run_id] = session
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
        user_event = _user_message_event(prompt, session_id=session_id, run_id=run_id, user_message=user_message)
        await self.run_service.record_event(run_id, user_event)
        history_records = await self._runs_for_session(session_id) if _sdk_file_history_enabled(options) else []
        file_history = _sdk_file_history_recorder(
            options,
            root=Path(workspace_path or ".").resolve(),
            session_id=session_id,
            message_id=str(user_event.payload.get("uuid") or user_event.payload.get("message_id") or ""),
            records=history_records,
        )
        if file_history is not None:
            await self.run_service.record_event(run_id, file_history.initial_event())
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
                if file_history is not None:
                    for snapshot_event in file_history.observe(event):
                        await self.run_service.record_event(run_id, snapshot_event)
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
            self._clear_active_turn(session_id, run_id, current_task, session=session)

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
                "sdk_file_history_session_id": forked_session_id,
                "sdk_forked_from_session_id": session_id,
                "sdk_forked_from_run_id": record.run_id,
            }
            title = options.title.strip()
            if title:
                metadata["sdk_title"] = title
            spec = replace(record.to_agent_spec(), metadata=metadata)
            forked = await self.run_service.store.create_run(spec)
            events, matched = _events_for_fork(record.events, options.up_to_message_id)
            events = _migrate_file_history_events_for_session(
                events,
                records=records,
                source_session_id=session_id,
                target_session_id=forked_session_id,
            )
            for event in events:
                await self.run_service.store.append_event(forked.run_id, event)
            await self.run_service.store.set_status(forked.run_id, record.status)
            forked_run_ids.append(forked.run_id)
            if options.up_to_message_id and matched:
                break
        return SDKForkSessionResult(session_id=forked_session_id, run_ids=forked_run_ids)

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


async def run_stdin_jsonl(
    chunks: AsyncIterable[str | bytes] | Iterable[str | bytes],
    options: SDKOptions | dict[str, Any] | None = None,
    structured_io: SDKStructuredIO | None = None,
) -> AsyncIterator[str]:
    async for line in AgentSDKClient().run_stdin_jsonl(chunks, options, structured_io=structured_io):
        yield line


async def run_jsonl_transport(
    transport: SDKJsonlTransport,
    options: SDKOptions | dict[str, Any] | None = None,
    structured_io: SDKStructuredIO | None = None,
    *,
    close_transport: bool = True,
) -> None:
    await AgentSDKClient().run_jsonl_transport(
        transport,
        options,
        structured_io=structured_io,
        close_transport=close_transport,
    )


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
