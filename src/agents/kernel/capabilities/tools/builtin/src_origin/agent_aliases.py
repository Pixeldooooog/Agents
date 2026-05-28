"""Registration wiring for src-origin agent and team aliases."""

from __future__ import annotations

import json
from typing import Any

from agents.kernel.capabilities.tools.builtin.agent_child_specs import child_agent_spec
from agents.kernel.capabilities.tools.builtin.agents import agent_run
from agents.kernel.capabilities.tools.builtin.registration_helpers import register_builtin_tool as _register_builtin_tool
from agents.kernel.capabilities.tools.builtin.src_origin.agent_resolution import resolve_src_origin_agent_selection
from agents.kernel.capabilities.tools.builtin.tasks import task_background
from agents.kernel.capabilities.tools.builtin.teams import team_create, team_delete, team_send
from agents.kernel.capabilities.tools.context import ToolRuntimeContext
from agents.kernel.capabilities.tools.registry import ToolRegistry


SRC_ORIGIN_EMPTY_SCHEMA = {"type": "object", "properties": {}}

SRC_ORIGIN_AGENT_SCHEMA = {
    "type": "object",
    "properties": {
        "description": {"type": "string", "description": "A short description of the task."},
        "prompt": {"type": "string", "description": "The task for the agent to perform."},
        "subagent_type": {"type": "string"},
        "model": {"type": "string", "enum": ["sonnet", "opus", "haiku"]},
        "run_in_background": {"type": "boolean"},
        "name": {"type": "string"},
        "team_name": {"type": "string"},
        "mode": {"type": "string"},
        "isolation": {"type": "string", "enum": ["worktree", "remote"]},
        "cwd": {"type": "string"},
    },
    "required": ["description", "prompt"],
}

SRC_ORIGIN_SEND_MESSAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "to": {"type": "string", "description": "Recipient teammate name or *."},
        "summary": {"type": "string", "description": "Short message summary."},
        "message": {
            "description": "Plain text or structured message content.",
            "anyOf": [{"type": "string"}, {"type": "object"}],
        },
        "team_name": {"type": "string", "description": "Optional team id/name override."},
    },
    "required": ["to", "message"],
}

SRC_ORIGIN_TEAM_CREATE_SCHEMA = {
    "type": "object",
    "properties": {
        "team_name": {"type": "string", "description": "Name for the new team to create."},
        "description": {"type": "string", "description": "Team description or purpose."},
        "agent_type": {"type": "string", "description": "Role of the team lead."},
    },
    "required": ["team_name"],
}


def register_src_origin_agent_aliases(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    for alias_name, src_origin_tool in (("Agent", "Agent"), ("Task", "Task")):
        _register_builtin_tool(
            registry,
            name=alias_name,
            description="Delegate work to a child agent. src-origin alias for agent.run.",
            parameters=SRC_ORIGIN_AGENT_SCHEMA,
            handler=lambda description,
            prompt,
            subagent_type="",
            model="",
            run_in_background=False,
            name="",
            team_name="",
            mode="",
            isolation="",
            cwd="": _src_origin_agent(
                context,
                description=description,
                prompt=prompt,
                subagent_type=subagent_type,
                model=model,
                run_in_background=run_in_background,
                name=name,
                team_name=team_name,
                mode=mode,
                isolation=isolation,
                cwd=cwd,
            ),
            metadata={"risk": "high", "spawns_agent": True, "model_call": True, "alias_of": "agent.run", "src_origin_tool": src_origin_tool},
            writes_state=True,
            concurrency_safe=False,
            activity_kind="agent",
            activity_title="Run agent",
            activity_target_argument="description",
        )
    _register_builtin_tool(
        registry,
        name="SendMessage",
        description="Send a message to a teammate. src-origin alias for team.send.",
        parameters=SRC_ORIGIN_SEND_MESSAGE_SCHEMA,
        handler=lambda to, message, summary="", team_name="": _src_origin_send_message(
            context,
            to=to,
            message=message,
            summary=summary,
            team_name=team_name,
        ),
        metadata={"risk": "low", "writes_state": True, "alias_of": "team.send", "src_origin_tool": "SendMessage"},
        writes_state=True,
        activity_kind="state",
        activity_title="Send message",
        activity_target_argument="to",
    )
    _register_builtin_tool(
        registry,
        name="TeamCreate",
        description="Create a multi-agent team. src-origin alias for team.create.",
        parameters=SRC_ORIGIN_TEAM_CREATE_SCHEMA,
        handler=lambda team_name, description="", agent_type="": _src_origin_team_create(
            context,
            team_name=team_name,
            description=description,
            agent_type=agent_type,
        ),
        metadata={"risk": "low", "writes_state": True, "alias_of": "team.create", "src_origin_tool": "TeamCreate"},
        writes_state=True,
        activity_kind="state",
        activity_title="Create team",
        activity_target_argument="team_name",
    )
    _register_builtin_tool(
        registry,
        name="TeamDelete",
        description="Delete the active team. src-origin alias for team.delete.",
        parameters=SRC_ORIGIN_EMPTY_SCHEMA,
        handler=lambda: team_delete(context),
        metadata={"risk": "medium", "writes_state": True, "alias_of": "team.delete", "src_origin_tool": "TeamDelete"},
        writes_state=True,
        concurrency_safe=False,
        activity_kind="state",
        activity_title="Delete team",
    )


async def _src_origin_agent(
    context: ToolRuntimeContext,
    *,
    description: str,
    prompt: str,
    subagent_type: str = "",
    model: str = "",
    run_in_background: bool = False,
    name: str = "",
    team_name: str = "",
    mode: str = "",
    isolation: str = "",
    cwd: str = "",
) -> dict:
    selection = await resolve_src_origin_agent_selection(
        context,
        name=name,
        subagent_type=subagent_type,
        model=model,
    )
    effective_isolation = isolation or selection.isolation
    if run_in_background or selection.background:
        child_spec = child_agent_spec(
            context,
            base_spec=selection.base_spec,
            agent_id=selection.agent_id,
            description=description,
        )
        payload = await task_background(
            context,
            title=description,
            input=prompt,
            metadata=_src_origin_metadata(
                {"source": "Agent"},
                subagent_type=subagent_type,
                model=model,
                name=name,
                team_name=team_name,
                mode=mode,
                isolation=effective_isolation,
                cwd=cwd,
                agent_id=child_spec.agent_id,
            ),
            step_name="agent",
            agent_spec=selection.base_spec,
        )
        payload["status"] = "async_launched"
        payload["agentId"] = payload["task"]["task_id"]
        payload["description"] = description
        payload["prompt"] = prompt
        return payload
    return await agent_run(
        context,
        prompt=prompt,
        description=description,
        agent_id=selection.agent_id,
        isolation=effective_isolation,
        cwd=cwd,
        base_spec=selection.base_spec,
    )


async def _src_origin_send_message(
    context: ToolRuntimeContext,
    *,
    to: str,
    message: Any,
    summary: str = "",
    team_name: str = "",
) -> dict:
    content = message if isinstance(message, str) else json.dumps(message, ensure_ascii=False, sort_keys=True)
    team_id = str(team_name or (next(iter(context.teams)) if len(context.teams) == 1 else ""))
    return await team_send(
        context,
        to=to,
        message=content,
        team_id=team_id,
        from_agent="team-lead",
        message_type="message",
    )


async def _src_origin_team_create(
    context: ToolRuntimeContext,
    *,
    team_name: str,
    description: str = "",
    agent_type: str = "",
) -> dict:
    lead_agent_id = "team-lead"
    payload = await team_create(
        context,
        team_id=team_name,
        name=team_name,
        description=description,
        members=[
            {
                "agent_id": lead_agent_id,
                "name": "team-lead",
                "role": agent_type or "team-lead",
            }
        ],
    )
    payload.update(
        {
            "team_name": payload["team"]["name"],
            "team_file_path": ".agents/teams/%s.json" % payload["team"]["team_id"],
            "lead_agent_id": lead_agent_id,
        }
    )
    return payload


def _src_origin_metadata(metadata: dict[str, Any] | None, **extra: Any) -> dict[str, Any]:
    payload = dict(metadata or {})
    for key, value in extra.items():
        if value not in (None, ""):
            payload[key] = value
    return payload
