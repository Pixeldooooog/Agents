from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from dataclasses import replace
from typing import Any

from agents.kernel.assembly import create_agent_session_async
from agents.kernel.config import runtime_settings
from agents.kernel.schema import RuntimeEvent
from agents.kernel.specs import AgentSpec
from agents.platform.persistence import PlatformPersistence, create_ephemeral_persistence
from agents.platform.sessions import RunService
from agents.sdk.types import (
    SDKAssistantMessage,
    SDKMessage,
    SDKOptions,
    SDKResultMessage,
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

    async def query(self, prompt: str, options: SDKOptions | None = None) -> AsyncIterator[SDKMessage]:
        options = _coerce_options(options)
        spec = _spec_from_options(options)
        started_at = time.monotonic()
        session = await self.create_session(options)
        run = await self.run_service.start(spec)
        run_id = run.run_id
        session_id = options.session_id or run_id
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

    async def prompt(self, prompt: str, options: SDKOptions | None = None) -> SDKResultMessage:
        result: SDKResultMessage | None = None
        async for message in self.query(prompt, options):
            if isinstance(message, SDKResultMessage):
                result = message
        if result is None:
            raise RuntimeError("SDK query completed without a result message")
        return result


async def query(prompt: str, options: SDKOptions | None = None) -> AsyncIterator[SDKMessage]:
    client = AgentSDKClient()
    async for message in client.query(prompt, options):
        yield message


async def prompt(prompt: str, options: SDKOptions | None = None) -> SDKResultMessage:
    return await AgentSDKClient().prompt(prompt, options)


def _coerce_options(options: SDKOptions | None) -> SDKOptions:
    if options is None:
        return SDKOptions()
    if isinstance(options, SDKOptions):
        return options
    return SDKOptions.model_validate(options)


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
