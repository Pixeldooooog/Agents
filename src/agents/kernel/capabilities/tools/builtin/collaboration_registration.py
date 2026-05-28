from __future__ import annotations

from agents.kernel.capabilities.tools.builtin.agents import AGENT_RUN_SCHEMA, agent_run
from agents.kernel.capabilities.tools.builtin.agent_profiles import (
    AGENT_PROFILES_SCHEMA,
    AGENT_SAVE_PROFILE_SCHEMA,
    agent_profiles,
    agent_save_profile,
)
from agents.kernel.capabilities.tools.builtin.teams import (
    TEAM_CREATE_SCHEMA,
    TEAM_DELETE_SCHEMA,
    TEAM_INBOX_SCHEMA,
    TEAM_MEMBERS_SCHEMA,
    TEAM_RUN_MEMBER_SCHEMA,
    TEAM_SEND_SCHEMA,
    team_create,
    team_delete,
    team_inbox,
    team_members,
    team_run_member,
    team_send,
)
from agents.kernel.capabilities.tools.context import ToolRuntimeContext
from agents.kernel.capabilities.tools.registry import ToolRegistry


def register_collaboration_tools(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    _register_agent_profiles(registry, context)
    _register_teams(registry, context)
    _register_agents(registry, context)


def _register_agent_profiles(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    registry.register(
        "agent.profiles",
        "List saved agent profiles for the current user.",
        AGENT_PROFILES_SCHEMA,
        lambda query="", limit=50: agent_profiles(context, query=query, limit=limit),
        metadata={"risk": "low", "model_call": True},
    )
    registry.register(
        "agent.save_profile",
        "Save the current session as an agent profile with optional overrides.",
        AGENT_SAVE_PROFILE_SCHEMA,
        lambda agent_id="", name="", system_prompt="", enabled_tools=None, skills=None, permission_profile="": agent_save_profile(
            context,
            agent_id=agent_id,
            name=name,
            system_prompt=system_prompt,
            enabled_tools=enabled_tools,
            skills=skills,
            permission_profile=permission_profile,
        ),
        metadata={"risk": "medium", "writes_state": True, "model_call": True},
    )


def _register_teams(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    registry.register(
        "team.create",
        "Create or update an agent team with named members.",
        TEAM_CREATE_SCHEMA,
        lambda team_id="", name="", description="", members=None: team_create(
            context,
            team_id=team_id,
            name=name,
            description=description,
            members=members,
        ),
        metadata={"risk": "low", "writes_state": True, "model_call": True},
    )
    registry.register(
        "team.delete",
        "Delete an agent team and its queued messages.",
        TEAM_DELETE_SCHEMA,
        lambda team_id="": team_delete(context, team_id=team_id),
        metadata={"risk": "medium", "writes_state": True, "model_call": True},
    )
    registry.register(
        "team.members",
        "List members for an agent team.",
        TEAM_MEMBERS_SCHEMA,
        lambda team_id="": team_members(context, team_id=team_id),
        metadata={"risk": "low", "model_call": True},
    )
    registry.register(
        "team.send",
        "Send a message to a team member or broadcast to the team.",
        TEAM_SEND_SCHEMA,
        lambda to, message, team_id="", from_agent="", message_type="message": team_send(
            context,
            to=to,
            message=message,
            team_id=team_id,
            from_agent=from_agent,
            message_type=message_type,
        ),
        metadata={"risk": "low", "writes_state": True, "model_call": True},
    )
    registry.register(
        "team.inbox",
        "Read queued team messages for an agent.",
        TEAM_INBOX_SCHEMA,
        lambda agent_id="", team_id="", unread_only=True, mark_read=False, limit=50: team_inbox(
            context,
            agent_id=agent_id,
            team_id=team_id,
            unread_only=unread_only,
            mark_read=mark_read,
            limit=limit,
        ),
        metadata={"risk": "low", "writes_state": True, "model_call": True},
    )
    registry.register(
        "team.run_member",
        "Run a bounded prompt with a configured team member and deliver the result to an inbox.",
        TEAM_RUN_MEMBER_SCHEMA,
        lambda agent_id, prompt, team_id="", reply_to="": team_run_member(
            context,
            agent_id=agent_id,
            prompt=prompt,
            team_id=team_id,
            reply_to=reply_to,
        ),
        metadata={"risk": "high", "writes_state": True, "spawns_agent": True, "model_call": True},
    )


def _register_agents(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    registry.register(
        "agent.run",
        "Run a bounded prompt in an in-process child agent and return the child agent result.",
        AGENT_RUN_SCHEMA,
        lambda prompt, description="", agent_id="", system_prompt="", enabled_tools=None, isolation="", cwd="": agent_run(
            context,
            prompt=prompt,
            description=description,
            agent_id=agent_id,
            system_prompt=system_prompt,
            enabled_tools=enabled_tools,
            isolation=isolation,
            cwd=cwd,
        ),
        metadata={"risk": "high", "spawns_agent": True, "model_call": True},
    )
