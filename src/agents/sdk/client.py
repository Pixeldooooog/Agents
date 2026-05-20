from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, replace
from typing import Any

from agents.kernel.assembly import create_agent_session_async
from agents.kernel.config import runtime_settings
from agents.kernel.schema import RuntimeEvent
from agents.kernel.specs import AgentSpec
from agents.kernel.state.runs import RunRecord
from agents.platform.persistence import PlatformPersistence, create_ephemeral_persistence
from agents.platform.sessions import RunService
from agents.sdk.types import (
    SDKAssistantMessage,
    SDKGetSessionMessagesOptions,
    SDKListSessionsOptions,
    SDKMessage,
    SDKOptions,
    SDKResultMessage,
    SDKSessionInfo,
    SDKStatusMessage,
    SDKSystemMessage,
    SDKToolProgressMessage,
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
        return SDKStatusMessage(
            session_id=session_id,
            run_id=run_id,
            status="api_retry",
            data=dict(event.payload),
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
