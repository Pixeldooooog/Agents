from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

from agents.kernel.assembly.session import create_agent_session_async
from agents.kernel.specs import AgentSpec
from agents.platform.sessions import RunService

BridgeWriter = Callable[[dict[str, Any]], None]


def tool_context(state: Any) -> Any | None:
    return getattr(getattr(state, "session", None), "tool_context", None)


def error_message(exc: Exception) -> str:
    return str(exc).strip("'") or exc.__class__.__name__


def split_once(value: str) -> tuple[str, str]:
    parts = str(value or "").strip().split(maxsplit=1)
    if not parts:
        return "", ""
    return parts[0].lower(), parts[1] if len(parts) > 1 else ""


def split_once_preserve(value: str) -> tuple[str, str]:
    parts = str(value or "").strip().split(maxsplit=1)
    if not parts:
        return "", ""
    return parts[0], parts[1] if len(parts) > 1 else ""


def merge_unique(*groups: list[str]) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for item in group:
            if item and item not in seen:
                seen.add(item)
                values.append(item)
    return values


def short_task_id(task_id: str) -> str:
    return str(task_id).replace("task_", "", 1)[:12]


def safe_file_stem(value: str) -> str:
    text = str(value or "").strip()
    return "".join(ch for ch in text if ch.isalnum() or ch in {"-", "_"}).strip("-_")


def task_run_service(state: Any) -> RunService:
    service = getattr(state, "task_run_service", None)
    if service is not None:
        return service
    persistence = getattr(state, "persistence", None)
    service = RunService(
        getattr(persistence, "runs", None),
        sandbox_store=getattr(persistence, "sandboxes", None),
    )
    setattr(state, "task_run_service", service)
    return service


async def create_session_from_agent_profile(state: Any, spec: AgentSpec) -> Any:
    persistence = getattr(state, "persistence", None)
    return await create_agent_session_async(
        state.settings,
        spec=spec,
        checkpoint_store=getattr(persistence, "checkpoints", None),
        memory_store=getattr(persistence, "memories", None),
        schedule_store=getattr(persistence, "schedules", None),
        team_store=getattr(persistence, "teams", None),
        hook_store=getattr(persistence, "hooks", None),
        mcp_config_store=getattr(persistence, "mcp_configs", None),
        session_state_store=getattr(persistence, "session_states", None),
        sandbox_store=getattr(persistence, "sandboxes", None),
        artifact_store=getattr(persistence, "artifacts", None),
        artifact_blob_store=getattr(persistence, "artifact_blobs", None),
        task_store=getattr(persistence, "tasks", None),
        run_service=task_run_service(state),
        agent_profile_store=getattr(persistence, "agent_profiles", None),
    )


def agent_spec_for_state(state: Any, *, agent_id: str = "") -> AgentSpec:
    workspace = getattr(state.session, "workspace", None)
    runtime = getattr(state.session, "runtime", None)
    resolved_agent_id = agent_id or str(getattr(workspace, "agent_id", "") or "")
    context = tool_context(state)
    denied_tools = (
        [str(tool) for tool in list(getattr(context, "permission_denied_tools_override", []) or [])]
        if context is not None
        else []
    )
    approval_tools = [str(tool) for tool in list(getattr(state, "approval_tools", []) or [])]
    if not approval_tools and context is not None:
        approval_tools = [str(tool) for tool in list(getattr(context, "approval_required_tools_override", []) or [])]
    permission_profile = str(getattr(state, "permission", "") or getattr(state, "permission_mode", "") or "auto")
    permission_mode = str(getattr(state, "permission_mode", "") or permission_profile or "auto")
    spec = AgentSpec.from_overrides(
        protocol=str(getattr(runtime, "protocol", "") or ""),
        model=str(getattr(runtime, "model", "") or ""),
        enabled_tools=list(getattr(state, "active_tools", []) or []),
        tenant_id=str(getattr(workspace, "tenant_id", "") or ""),
        user_id=str(getattr(workspace, "user_id", "") or ""),
        agent_id=resolved_agent_id,
        workspace_id=str(getattr(workspace, "workspace_id", "") or ""),
        workspace_path=str(getattr(workspace, "path", "") or getattr(state, "active_workspace", "") or ""),
        permission_profile=permission_profile,
        approval_required_tools=approval_tools,
        denied_tools=denied_tools,
    )
    if spec.tool_permissions.mode != permission_mode:
        spec = replace(spec, tool_permissions=replace(spec.tool_permissions, mode=permission_mode))
    if context is None or not bool(getattr(context, "permission_restrict_allowed_tools", False)):
        return spec
    return replace(
        spec,
        tool_permissions=replace(
            spec.tool_permissions,
            allowed_tools=[str(tool) for tool in list(getattr(context, "permission_allowed_tools_override", []) or [])],
        ),
    )
