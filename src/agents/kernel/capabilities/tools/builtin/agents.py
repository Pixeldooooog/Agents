from __future__ import annotations

from typing import Any
from uuid import uuid4

from agents.kernel.capabilities.tools.builtin.agent_isolation import (
    prepare_agent_isolation_scope,
    with_agent_workspace_path,
)
from agents.kernel.capabilities.tools.builtin.agent_child_specs import child_agent_spec
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
        "isolation": {
            "type": "string",
            "enum": ["worktree", "remote"],
            "description": "Optional child workspace isolation mode.",
        },
        "cwd": {"type": "string", "description": "Optional child working directory inside the current workspace."},
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
    isolation: str = "",
    cwd: str = "",
    base_spec: AgentSpec | None = None,
) -> dict[str, Any]:
    if context.agent_session_factory is None:
        raise RuntimeError("agent session factory is not available")
    if int(context.subagent_depth or 0) >= int(context.max_subagent_depth or 1):
        raise RuntimeError("subagent depth limit reached")
    child_spec = child_agent_spec(
        context,
        base_spec=base_spec,
        agent_id=agent_id,
        description=description,
        system_prompt=system_prompt,
        enabled_tools=enabled_tools,
    )
    run_id = "subagent_%s" % uuid4().hex
    scope = await prepare_agent_isolation_scope(
        context,
        child_agent_id=child_spec.agent_id,
        isolation=isolation,
        cwd=cwd,
    )
    if scope.workspace_path is not None:
        child_spec = with_agent_workspace_path(child_spec, scope.workspace_path)
    child = None
    try:
        child = await context.agent_session_factory(child_spec, task_id="")
        result = await child.send(_required_text(prompt, "prompt"), run_id=run_id)
    finally:
        try:
            close = getattr(child, "aclose", None) if child is not None else None
            if close is not None:
                await close()
        finally:
            scope.close()
    payload = {
        "agent_id": child_spec.agent_id,
        "run_id": run_id,
        "description": str(description or ""),
        "status": result.status,
        "content": result.content,
        "messages": _message_count(result.messages),
        "tool_results": len(result.tool_results),
    }
    payload.update(scope.result_fields())
    return payload


def _message_count(messages: list[Message]) -> int:
    return len([message for message in messages if message.role != "system"])


def _required_text(value: str, name: str) -> str:
    text = str(value or "").strip()
    if text:
        return text
    raise ValueError("%s is required" % name)
