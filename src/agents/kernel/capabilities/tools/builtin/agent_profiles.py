from __future__ import annotations

from typing import Any

from agents.kernel.capabilities.tools.context import ToolRuntimeContext
from agents.kernel.specs import AgentSpec
from agents.kernel.state import AgentProfile


AGENT_PROFILES_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {"type": "string"},
        "limit": {"type": "integer", "minimum": 1, "maximum": 100},
    },
}

AGENT_SAVE_PROFILE_SCHEMA = {
    "type": "object",
    "properties": {
        "agent_id": {"type": "string", "description": "Profile agent id. Defaults to current agent id."},
        "name": {"type": "string", "description": "Display name. Defaults to agent_id."},
        "system_prompt": {"type": "string", "description": "Optional system prompt override. Defaults to current session prompt."},
        "enabled_tools": {"type": "array", "items": {"type": "string"}},
        "skills": {"type": "array", "items": {"type": "string"}},
        "permission_profile": {"type": "string", "enum": ["", "auto", "ask", "deny"]},
    },
}


async def agent_profiles(context: ToolRuntimeContext, query: str = "", limit: int = 50) -> dict[str, Any]:
    store = _profile_store(context)
    workspace = context.workspace
    profiles = await store.list_for_user(workspace.tenant_id, workspace.user_id)
    needle = str(query or "").strip().lower()
    if needle:
        profiles = [profile for profile in profiles if needle in _profile_haystack(profile)]
    max_items = max(1, min(int(limit or 50), 100))
    return {"profiles": [_profile_payload(profile) for profile in profiles[:max_items]], "count": min(len(profiles), max_items), "total": len(profiles)}


async def agent_save_profile(
    context: ToolRuntimeContext,
    agent_id: str = "",
    name: str = "",
    system_prompt: str = "",
    enabled_tools: list[str] | None = None,
    skills: list[str] | None = None,
    permission_profile: str = "",
) -> dict[str, Any]:
    store = _profile_store(context)
    spec = _profile_spec(
        context,
        agent_id=agent_id,
        system_prompt=system_prompt,
        enabled_tools=enabled_tools,
        skills=skills,
        permission_profile=permission_profile,
    )
    profile = AgentProfile.from_spec(spec, name=str(name or spec.agent_id or spec.workspace.agent_id or "agent"))
    await store.save(profile)
    return {"profile": _profile_payload(profile.with_update())}


def _profile_store(context: ToolRuntimeContext) -> Any:
    store = getattr(context, "agent_profile_store", None)
    if store is None:
        raise RuntimeError("agent profile store is not available")
    return store


def _profile_spec(
    context: ToolRuntimeContext,
    *,
    agent_id: str = "",
    system_prompt: str = "",
    enabled_tools: list[str] | None = None,
    skills: list[str] | None = None,
    permission_profile: str = "",
) -> AgentSpec:
    base = getattr(context, "agent_spec", None)
    if not isinstance(base, AgentSpec):
        workspace = context.workspace
        base = AgentSpec.from_overrides(
            tenant_id=workspace.tenant_id,
            user_id=workspace.user_id,
            agent_id=workspace.agent_id,
            workspace_id=workspace.workspace_id,
            workspace_path=str(workspace.path),
        )
    session_prompt = str(getattr(getattr(context, "session", None), "system_prompt", "") or "")
    return AgentSpec.from_overrides(
        protocol=base.model.protocol,
        model=base.model.model,
        base_url=base.model.base_url,
        api_key=base.model.api_key,
        system_prompt=str(system_prompt or session_prompt or base.system_prompt or ""),
        enabled_tools=list(enabled_tools) if enabled_tools is not None else list(getattr(context, "enabled_tools", []) or base.enabled_tools or []),
        tenant_id=base.workspace.tenant_id,
        user_id=base.workspace.user_id,
        agent_id=str(agent_id or base.agent_id or base.workspace.agent_id or "agent"),
        workspace_id=base.workspace.workspace_id,
        workspace_path=base.workspace.path,
        skills=list(skills) if skills is not None else list(base.skills or []),
        permission_profile=str(permission_profile or base.permission_profile or base.tool_permissions.mode or "auto"),
        approval_required_tools=list(base.tool_permissions.approval_required_tools),
        denied_tools=list(base.tool_permissions.denied_tools),
    )


def _profile_payload(profile: AgentProfile) -> dict[str, Any]:
    return {
        "agent_id": profile.agent_id,
        "name": profile.name,
        "tenant_id": profile.tenant_id,
        "user_id": profile.user_id,
        "spec": dict(profile.spec),
        "created_at": profile.created_at,
        "updated_at": profile.updated_at,
    }


def _profile_haystack(profile: AgentProfile) -> str:
    return ("%s %s %s" % (profile.agent_id, profile.name, profile.spec)).lower()
