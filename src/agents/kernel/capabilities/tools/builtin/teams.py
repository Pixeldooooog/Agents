from __future__ import annotations

import time
from typing import Any

from agents.kernel.capabilities.tools.builtin.agents import agent_run
from agents.kernel.capabilities.tools.context import ToolRuntimeContext
from agents.kernel.specs import AgentSpec
from agents.kernel.teams import TeamMessageRecord, TeamRecord, safe_agent_id, safe_team_id


TEAM_CREATE_SCHEMA = {
    "type": "object",
    "properties": {
        "team_id": {"type": "string", "description": "Optional stable team id. Defaults to default."},
        "name": {"type": "string"},
        "description": {"type": "string"},
        "members": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "agent_id": {"type": "string"},
                    "name": {"type": "string"},
                    "role": {"type": "string"},
                    "system_prompt": {"type": "string"},
                    "enabled_tools": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["agent_id"],
            },
        },
    },
}

TEAM_MEMBERS_SCHEMA = {
    "type": "object",
    "properties": {
        "team_id": {"type": "string"},
    },
}

TEAM_SEND_SCHEMA = {
    "type": "object",
    "properties": {
        "to": {"type": "string", "description": "Recipient agent id, or * for every team member."},
        "message": {"type": "string"},
        "team_id": {"type": "string"},
        "from_agent": {"type": "string"},
        "message_type": {"type": "string"},
    },
    "required": ["to", "message"],
}

TEAM_INBOX_SCHEMA = {
    "type": "object",
    "properties": {
        "agent_id": {"type": "string", "description": "Agent id to read inbox for. Defaults to current agent."},
        "team_id": {"type": "string"},
        "unread_only": {"type": "boolean"},
        "mark_read": {"type": "boolean"},
        "limit": {"type": "integer", "minimum": 1, "maximum": 100},
    },
}

TEAM_RUN_MEMBER_SCHEMA = {
    "type": "object",
    "properties": {
        "agent_id": {"type": "string"},
        "prompt": {"type": "string"},
        "team_id": {"type": "string"},
        "reply_to": {"type": "string", "description": "Agent id that receives the result message. Defaults to current agent."},
    },
    "required": ["agent_id", "prompt"],
}


async def team_create(
    context: ToolRuntimeContext,
    team_id: str = "",
    name: str = "",
    description: str = "",
    members: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    resolved_team_id = safe_team_id(team_id or "default")
    existing = await _load_team_optional(context, resolved_team_id)
    member_map = dict(existing.members if existing is not None else {})
    for member in members or []:
        payload = _member_payload(context, member)
        member_map[payload["agent_id"]] = payload
    if existing is None:
        team = TeamRecord.create(
            spec=_agent_spec(context),
            team_id=resolved_team_id,
            name=str(name or resolved_team_id),
            description=str(description or ""),
            members=member_map,
        )
    else:
        team = existing.with_update(
            name=str(name or existing.name or resolved_team_id),
            description=str(description or existing.description or ""),
            members=member_map,
        )
    await _save_team(context, team)
    return {"team": _team_payload(team)}


async def team_members(context: ToolRuntimeContext, team_id: str = "") -> dict[str, Any]:
    team = await _load_team(context, team_id or "default")
    members = list(team.members.values())
    return {"team": _team_payload(team), "members": members, "count": len(members)}


async def team_send(
    context: ToolRuntimeContext,
    to: str,
    message: str,
    team_id: str = "",
    from_agent: str = "",
    message_type: str = "message",
) -> dict[str, Any]:
    team = await _load_team(context, team_id or "default")
    recipients = _recipients(team, to)
    if not recipients:
        raise KeyError("team recipient not found: %s" % to)
    messages = []
    for recipient in recipients:
        record = TeamMessageRecord.create(
            spec=_agent_spec(context),
            team_id=team.team_id,
            from_agent=safe_agent_id(from_agent) or context.workspace.agent_id or "agent",
            to_agent=recipient,
            message_type=str(message_type or "message"),
            message=_required_text(message, "message"),
        )
        await _add_message(context, record)
        messages.append(record.to_dict())
    return {"sent": messages, "count": len(messages)}


async def team_inbox(
    context: ToolRuntimeContext,
    agent_id: str = "",
    team_id: str = "",
    unread_only: bool = True,
    mark_read: bool = False,
    limit: int = 50,
) -> dict[str, Any]:
    max_items = max(1, min(int(limit or 50), 100))
    recipient = safe_agent_id(agent_id) or context.workspace.agent_id or "agent"
    wanted_team = safe_team_id(team_id) if str(team_id or "").strip() else ""
    store = getattr(context, "team_store", None)
    if store is not None:
        workspace = context.workspace
        records = await store.list_messages(
            workspace.tenant_id,
            user_id=workspace.user_id,
            agent_id=workspace.agent_id,
            workspace_id=workspace.workspace_id,
            team_id=wanted_team,
            to_agent=recipient,
            unread_only=unread_only,
            limit=max_items,
        )
        selected_payloads = [record.to_dict() for record in records]
        if mark_read:
            await store.mark_messages_read([record.message_id for record in records])
            context.team_messages = [
                {**message, "read": True} if message.get("message_id") in {record.message_id for record in records} else message
                for message in context.team_messages
            ]
        return {"agent_id": recipient, "messages": selected_payloads, "count": len(selected_payloads), "total": len(selected_payloads)}
    messages = [
        message
        for message in context.team_messages
        if message.get("to") == recipient
        and (not wanted_team or message.get("team_id") == wanted_team)
        and (not unread_only or not message.get("read"))
    ]
    selected = messages[-max_items:]
    if mark_read:
        selected_ids = {message["message_id"] for message in selected}
        for message in context.team_messages:
            if message.get("message_id") in selected_ids:
                message["read"] = True
    return {"agent_id": recipient, "messages": [dict(message) for message in selected], "count": len(selected), "total": len(messages)}


async def team_run_member(
    context: ToolRuntimeContext,
    agent_id: str,
    prompt: str,
    team_id: str = "",
    reply_to: str = "",
) -> dict[str, Any]:
    team = await _load_team(context, team_id or "default")
    member_id = safe_agent_id(agent_id)
    member = dict(team.members.get(member_id) or {})
    if not member:
        raise KeyError("team member not found: %s" % member_id)
    result = await agent_run(
        context,
        prompt=_required_text(prompt, "prompt"),
        description=member.get("role") or member.get("name") or member_id,
        agent_id=member_id,
        system_prompt=str(member.get("system_prompt") or ""),
        enabled_tools=list(member.get("enabled_tools") or []),
    )
    recipient = safe_agent_id(reply_to) or context.workspace.agent_id or "agent"
    message = TeamMessageRecord.create(
        spec=_agent_spec(context),
        team_id=team.team_id,
        from_agent=member_id,
        to_agent=recipient,
        message_type="agent_result",
        message=str(result.get("content") or ""),
        metadata={"run_id": str(result.get("run_id") or ""), "status": str(result.get("status") or "")},
    )
    await _add_message(context, message)
    return {"member": member, "result": result, "delivered": message.to_dict()}


def _member_payload(context: ToolRuntimeContext, member: dict[str, Any]) -> dict[str, Any]:
    agent_id = safe_agent_id(member.get("agent_id"))
    if not agent_id:
        raise ValueError("member agent_id is required")
    return {
        "agent_id": agent_id,
        "name": str(member.get("name") or agent_id),
        "role": str(member.get("role") or ""),
        "system_prompt": str(member.get("system_prompt") or ""),
        "enabled_tools": [str(tool) for tool in member.get("enabled_tools") or context.enabled_tools],
        "status": "idle",
    }


async def _load_team(context: ToolRuntimeContext, team_id: str) -> TeamRecord:
    resolved = safe_team_id(team_id or "default")
    team = await _load_team_optional(context, resolved)
    if team is None:
        raise KeyError("team not found: %s" % resolved)
    return team


async def _load_team_optional(context: ToolRuntimeContext, team_id: str) -> TeamRecord | None:
    resolved = safe_team_id(team_id or "default")
    store = getattr(context, "team_store", None)
    if store is not None:
        workspace = context.workspace
        record = await store.load_team(
            resolved,
            workspace.tenant_id,
            user_id=workspace.user_id,
            agent_id=workspace.agent_id,
            workspace_id=workspace.workspace_id,
        )
        if record is not None:
            context.teams[record.team_id] = record.to_dict()
            return record
    if resolved in context.teams:
        return _record_from_payload(context.teams[resolved])
    return None


async def _save_team(context: ToolRuntimeContext, team: TeamRecord) -> None:
    store = getattr(context, "team_store", None)
    if store is not None:
        await store.save_team(team)
        persisted = await store.load_team(
            team.team_id,
            team.tenant_id,
            user_id=team.user_id,
            agent_id=team.agent_id,
            workspace_id=team.workspace_id,
        )
        team = persisted or team
    context.teams[team.team_id] = team.to_dict()


async def _add_message(context: ToolRuntimeContext, message: TeamMessageRecord) -> None:
    store = getattr(context, "team_store", None)
    if store is not None:
        await store.add_message(message)
    context.team_messages.append(message.to_dict())


def _team_payload(team: TeamRecord) -> dict[str, Any]:
    return {
        "team_id": team.team_id,
        "name": team.name,
        "description": team.description,
        "member_count": len(team.members),
        "created_at": team.created_at,
        "updated_at": team.updated_at,
    }


def _recipients(team: TeamRecord, to: str) -> list[str]:
    target = str(to or "").strip()
    members = team.members
    if target == "*":
        return sorted(members)
    agent_id = safe_agent_id(target)
    return [agent_id] if agent_id in members else []


def _record_from_payload(payload: dict[str, Any]) -> TeamRecord:
    return TeamRecord(
        team_id=safe_team_id(payload.get("team_id") or "default"),
        name=str(payload.get("name") or payload.get("team_id") or "default"),
        description=str(payload.get("description") or ""),
        members={str(key): dict(value) for key, value in dict(payload.get("members") or {}).items()},
        agent_id=str(payload.get("agent_id") or ""),
        tenant_id=str(payload.get("tenant_id") or ""),
        user_id=str(payload.get("user_id") or ""),
        workspace_id=str(payload.get("workspace_id") or ""),
        metadata={str(key): str(value) for key, value in dict(payload.get("metadata") or {}).items()},
        created_at=float(payload.get("created_at") or time.time()),
        updated_at=float(payload.get("updated_at") or time.time()),
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


def _required_text(value: Any, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError("%s is required" % name)
    return text
