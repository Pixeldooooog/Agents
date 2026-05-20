from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any

from agents.kernel.assembly import create_agent_session_async
from agents.kernel.config import runtime_settings
from agents.kernel.schema import RuntimeEvent
from agents.kernel.specs import AgentSpec
from agents.kernel.state.runs import RunRecord
from agents.platform.persistence import PlatformPersistence, create_ephemeral_persistence
from agents.platform.sessions import RunService
from agents.sdk.types import (
    SDKAPIRetryMessage,
    SDKAssistantMessage,
    SDKCompactBoundaryMessage,
    SDKForkSessionOptions,
    SDKForkSessionResult,
    SDKGetSessionMessagesOptions,
    SDKListSessionsOptions,
    SDKMessage,
    SDKOptions,
    SDKResultMessage,
    SDKSessionInfo,
    SDKStatusMessage,
    SDKSystemMessage,
    SDKToolProgressMessage,
    SDKUserMessage,
)


SessionFactory = Callable[[Any, AgentSpec], Any]


@dataclass
class AgentSDKClient:
    """Stable SDK facade over kernel assembly and platform stores."""

    settings: Any = None
    persistence: PlatformPersistence | None = None
    run_service: RunService | None = None
    session_factory: SessionFactory | None = None

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
            return await self.session_factory(self.settings, spec)
        assert self.persistence is not None
        return await create_agent_session_async(
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

    def create_sdk_session(self, options: SDKOptions | dict[str, Any] | None = None) -> "SDKSession":
        options = _coerce_options(options)
        session_id = options.session_id or "session_%s" % uuid.uuid4().hex
        return SDKSession(
            client=self,
            session_id=session_id,
            options=options.model_copy(update={"session_id": session_id}),
        )

    async def resume_session(self, session_id: str, options: SDKOptions | dict[str, Any] | None = None) -> "SDKSession":
        info = await self.get_session_info(session_id)
        if info is None:
            raise KeyError("session not found: %s" % session_id)
        options = _coerce_options(options).model_copy(update={"session_id": session_id})
        return SDKSession(client=self, session_id=session_id, options=options)

    async def query(self, prompt: str, options: SDKOptions | dict[str, Any] | None = None) -> AsyncIterator[SDKMessage]:
        options = _coerce_options(options)
        spec = _spec_from_options(options)
        started_at = time.monotonic()
        session = await self.create_session(options)
        run = await self.run_service.start(spec)
        run_id = run.run_id
        session_id = options.session_id or run_id
        await self._record_session_metadata(
            run_id,
            session_id=session_id,
            prompt=prompt,
            options=options,
            session=session,
        )
        await self.run_service.record_event(
            run_id,
            _user_message_event(prompt, session_id=session_id, run_id=run_id),
        )
        final_status = "finished"
        yielded_result = False
        event_count = 0

        yield SDKSystemMessage(
            session_id=session_id,
            run_id=run_id,
            cwd=str(getattr(session.workspace, "path", "") or ""),
            model=str(getattr(session.runtime, "model", "") or ""),
            protocol=str(getattr(session.runtime, "protocol", "") or ""),
            tools=list(getattr(session.runtime, "enabled_tools", []) or []),
            metadata=options.metadata,
        )

        try:
            async for event in session.stream(prompt, run_id=run_id):
                event_count += 1
                await self.run_service.record_event(run_id, event)
                message = _project_runtime_event(
                    event,
                    session_id=session_id,
                    run_id=run_id,
                    duration_ms=_duration_ms(started_at),
                    num_turns=1,
                )
                if message is None:
                    continue
                if isinstance(message, SDKResultMessage):
                    yielded_result = True
                    final_status = message.status
                elif isinstance(message, SDKToolProgressMessage) and message.status == "awaiting_approval":
                    final_status = "awaiting_approval"
                    await self.run_service.pause_for_approval(run_id)
                yield message
        except Exception as exc:
            final_status = "error"
            yielded_result = True
            error_message = SDKResultMessage(
                session_id=session_id,
                run_id=run_id,
                subtype="error",
                status="error",
                error=str(exc),
                duration_ms=_duration_ms(started_at),
                num_turns=1,
                metadata={"event_count": event_count},
            )
            yield error_message
        finally:
            if not yielded_result:
                yield SDKResultMessage(
                    session_id=session_id,
                    run_id=run_id,
                    subtype="success" if final_status != "error" else "error",
                    status=final_status,
                    duration_ms=_duration_ms(started_at),
                    num_turns=1,
                    metadata={"event_count": event_count},
                )
            if final_status != "awaiting_approval":
                await self.run_service.finish(run_id, error="" if final_status == "finished" else final_status)
            close = getattr(session, "aclose", None)
            if close is not None:
                await close()

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
                messages.append(_system_message_from_run(record, session_id=resolved_session_id))
            duration_ms = _duration_ms_from_record(record)
            for event in record.events:
                if event.type == "run_created":
                    continue
                message = _project_runtime_event(
                    event,
                    session_id=resolved_session_id,
                    run_id=record.run_id,
                    duration_ms=duration_ms,
                    num_turns=1,
                )
                if message is not None:
                    messages.append(message)
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

    async def _record_session_metadata(
        self,
        run_id: str,
        *,
        session_id: str,
        prompt: str,
        options: SDKOptions,
        session: Any,
    ) -> None:
        workspace_path = str(getattr(getattr(session, "workspace", None), "path", "") or options.cwd or "")
        metadata = {
            "sdk_session_id": session_id,
            "sdk_first_prompt": _truncate(prompt),
            "sdk_cwd": workspace_path,
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
        async for message in self.client.query(prompt, merged):
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


def _user_message_event(prompt: str, *, session_id: str, run_id: str) -> RuntimeEvent:
    message_id = "msg_%s" % uuid.uuid4().hex
    message = {
        "role": "user",
        "content": [{"type": "text", "text": prompt}],
    }
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
            "parent_tool_use_id": None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


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
    return SDKSessionInfo(
        session_id=_session_id_for_run(latest),
        summary=summary,
        last_modified=_millis(latest.updated_at),
        created_at=_millis(ordered[0].created_at),
        custom_title=custom_title,
        first_prompt=first_prompt,
        cwd=_first_non_empty(_record_cwd(record) for record in reversed(ordered)),
        tag=str(metadata.get("sdk_tag") or metadata.get("tag") or ""),
        status=latest.status.value,
        latest_run_id=latest.run_id,
        run_ids=[record.run_id for record in ordered],
        metadata={**metadata, "run_count": len(records)},
    )


def _session_id_for_run(record: RunRecord) -> str:
    return str(record.metadata.get("sdk_session_id") or record.run_id)


def _system_message_from_run(record: RunRecord, *, session_id: str) -> SDKSystemMessage:
    model, protocol, tools = _runtime_fields_from_run(record)
    return SDKSystemMessage(
        session_id=session_id,
        run_id=record.run_id,
        cwd=_record_cwd(record),
        model=model,
        protocol=protocol,
        tools=tools,
        metadata=dict(record.metadata),
    )


def _runtime_fields_from_run(record: RunRecord) -> tuple[str, str, list[str]]:
    spec = record.spec
    model_spec = spec.get("model") if isinstance(spec.get("model"), dict) else {}
    tools = spec.get("tools") if isinstance(spec.get("tools"), dict) else {}
    enabled_tools = tools.get("enabled_tools") if isinstance(tools, dict) else []
    if not isinstance(enabled_tools, list):
        enabled_tools = []
    return (
        str(model_spec.get("model") or "") if isinstance(model_spec, dict) else "",
        str(model_spec.get("protocol") or "") if isinstance(model_spec, dict) else "",
        [str(item) for item in enabled_tools],
    )


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


def _content_from_user_message(message: dict[str, Any]) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text") or ""))
        return "".join(parts)
    return ""


def _user_message_priority(value: Any) -> str | None:
    text = str(value or "")
    return text if text in {"now", "next", "later"} else None


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
            content=str(event.payload.get("content") or _content_from_user_message(message)),
            parent_tool_use_id=event.payload.get("parent_tool_use_id"),
            is_synthetic=bool(event.payload.get("isSynthetic") or event.payload.get("is_synthetic") or False),
            tool_use_result=event.payload.get("tool_use_result"),
            priority=_user_message_priority(event.payload.get("priority")),
            timestamp=str(event.payload.get("timestamp") or ""),
            is_replay=bool(event.payload.get("isReplay", event.payload.get("is_replay", True))),
        )
    if event.type == "model_message":
        return SDKAssistantMessage(
            session_id=session_id,
            run_id=run_id,
            content=str(event.payload.get("content", "") or ""),
            raw=dict(event.payload),
        )
    if event.type == "text_delta":
        return SDKAssistantMessage(
            session_id=session_id,
            run_id=run_id,
            content=str(event.payload.get("delta", "") or ""),
            raw=dict(event.payload),
        )
    if event.type == "reasoning_delta":
        return SDKStatusMessage(
            session_id=session_id,
            run_id=run_id,
            status="reasoning_delta",
            message=str(event.payload.get("delta", "") or ""),
            data=dict(event.payload),
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
            status="error",
            message=str(event.payload.get("message", "") or ""),
            data=dict(event.payload),
        )
    if event.type == "done":
        status = str(event.payload.get("status", "") or "finished")
        error = str(event.payload.get("error", "") or "")
        return SDKResultMessage(
            session_id=session_id,
            run_id=run_id,
            subtype="error" if error or status == "error" else "success",
            content=str(event.payload.get("content", "") or ""),
            stop_reason=status,
            duration_ms=duration_ms,
            num_turns=num_turns,
            status=status,
            error=error,
            metadata={"event_count": event.payload.get("event_count")},
        )
    return SDKStatusMessage(
        session_id=session_id,
        run_id=run_id,
        status=event.type,
        message=event.name,
        data=dict(event.payload),
    )


def _tool_call_id(payload: dict[str, Any]) -> str:
    return str(payload.get("id") or payload.get("tool_call_id") or uuid.uuid4())


def _tool_contract(payload: dict[str, Any]) -> dict[str, Any]:
    contract = payload.get("contract")
    return dict(contract) if isinstance(contract, dict) else {}


def _duration_ms(started_at: float) -> int:
    return int((time.monotonic() - started_at) * 1000)
