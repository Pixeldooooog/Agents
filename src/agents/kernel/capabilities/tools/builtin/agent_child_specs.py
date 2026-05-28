from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

from agents.kernel.capabilities.tools.context import ToolRuntimeContext
from agents.kernel.specs import AgentSpec


def child_agent_spec(
    context: ToolRuntimeContext,
    *,
    base_spec: AgentSpec | None = None,
    agent_id: str = "",
    description: str = "",
    system_prompt: str = "",
    enabled_tools: list[str] | None = None,
) -> AgentSpec:
    base = base_spec or runtime_agent_spec(context)
    child_agent_id = safe_agent_id(agent_id) or "subagent_%s" % uuid4().hex[:12]
    workspace = replace(base.workspace, agent_id=child_agent_id)
    metadata = dict(base.metadata)
    metadata.update(
        {
            "parent_agent_id": base.agent_id or base.workspace.agent_id,
            "description": str(description or ""),
        }
    )
    return replace(
        base,
        agent_id=child_agent_id,
        workspace=workspace,
        system_prompt=str(system_prompt or base.system_prompt or "") or None,
        enabled_tools=list(enabled_tools) if enabled_tools is not None else base.enabled_tools,
        skills=list(base.skills) if base.skills is not None else None,
        metadata=metadata,
    )


def runtime_agent_spec(context: ToolRuntimeContext) -> AgentSpec:
    spec = getattr(context, "agent_spec", None)
    if isinstance(spec, AgentSpec):
        return spec
    workspace = context.workspace
    return AgentSpec.from_overrides(
        tenant_id=workspace.tenant_id,
        user_id=workspace.user_id,
        agent_id=workspace.agent_id,
        workspace_id=workspace.workspace_id,
        workspace_path=str(workspace.path),
    )


def safe_agent_id(value: str) -> str:
    return "".join(
        ch for ch in str(value or "").strip() if ch.isalnum() or ch in ("_", "-", ".")
    ).strip(".-")
