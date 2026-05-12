from __future__ import annotations

from dataclasses import replace
from typing import Any
from uuid import uuid4

from agents.kernel.capabilities.tools.context import ToolRuntimeContext
from agents.kernel.schema import Message
from agents.kernel.specs import AgentSpec


AGENT_RUN_SCHEMA = {
    "type": "object",
    "properties": {
        "prompt": {"type": "string", "description": "Bounded prompt for the child agent."},
        "description": {"type": "string", "description": "Short description of the delegated work."},
        "agent_id": {"type": "string", "description": "Optional child agent id. Defaults to a generated id."},
        "system_prompt": {"type": "string", "description": "Optional child system prompt override."},
        "enabled_tools": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Optional child enabled tool list. Defaults to the parent active tool set.",
        },
    },
    "required": ["prompt"],
}


async def agent_run(
    context: ToolRuntimeContext,
    prompt: str,
    description: str = "",
    agent_id: str = "",
    system_prompt: str = "",
    enabled_tools: list[str] | None = None,
) -> dict[str, Any]:
    if context.agent_session_factory is None:
        raise RuntimeError("agent session factory is not available")
    if int(context.subagent_depth or 0) >= int(context.max_subagent_depth or 1):
        raise RuntimeError("subagent depth limit reached")
    child_spec = _child_spec(
        context,
        agent_id=agent_id,
        description=description,
        system_prompt=system_prompt,
        enabled_tools=enabled_tools,
    )
    child = await context.agent_session_factory(child_spec, task_id="")
    run_id = "subagent_%s" % uuid4().hex
    try:
        result = await child.send(_required_text(prompt, "prompt"), run_id=run_id)
    finally:
        close = getattr(child, "aclose", None)
        if close is not None:
            await close()
    return {
        "agent_id": child_spec.agent_id,
        "run_id": run_id,
        "description": str(description or ""),
        "status": result.status,
        "content": result.content,
        "messages": _message_count(result.messages),
        "tool_results": len(result.tool_results),
    }


def _child_spec(
    context: ToolRuntimeContext,
    *,
    agent_id: str = "",
    description: str = "",
    system_prompt: str = "",
    enabled_tools: list[str] | None = None,
) -> AgentSpec:
    base = _agent_spec(context)
    child_agent_id = _safe_agent_id(agent_id) or "subagent_%s" % uuid4().hex[:12]
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
        metadata=metadata,
    )


def _agent_spec(context: ToolRuntimeContext) -> AgentSpec:
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


def _message_count(messages: list[Message]) -> int:
    return len([message for message in messages if message.role != "system"])


def _safe_agent_id(value: str) -> str:
    return "".join(ch for ch in str(value or "").strip() if ch.isalnum() or ch in ("_", "-", ".")).strip(".-")


def _required_text(value: str, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError("%s is required" % name)
    return text
