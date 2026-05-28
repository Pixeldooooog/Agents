from __future__ import annotations

from dataclasses import dataclass

from agents.kernel.capabilities.tools.context import ToolRuntimeContext
from agents.kernel.specs import AgentSpec
from agents.kernel.state import AgentProfile


DEFAULT_AGENT_TYPE = "general-purpose"


@dataclass(frozen=True)
class SrcOriginProfileLookup:
    profile: AgentProfile | None
    requested_type: str
    defaulted: bool = False


async def lookup_src_origin_agent_profile(
    context: ToolRuntimeContext,
    base: AgentSpec,
    subagent_type: str,
) -> SrcOriginProfileLookup:
    requested_type = _text(subagent_type)
    if requested_type:
        return SrcOriginProfileLookup(
            profile=await _required_profile(context, base, requested_type),
            requested_type=requested_type,
        )
    return SrcOriginProfileLookup(
        profile=await _optional_profile(context, base, DEFAULT_AGENT_TYPE),
        requested_type="",
        defaulted=True,
    )


async def _required_profile(
    context: ToolRuntimeContext,
    base: AgentSpec,
    profile_id: str,
) -> AgentProfile | None:
    store = getattr(context, "agent_profile_store", None)
    if store is None:
        return None
    profile = await _load_profile(context, base, profile_id)
    if profile is not None:
        return profile
    available = await _available_profile_ids(context, base)
    suffix = ", ".join(available) if available else "none"
    raise ValueError("Agent type '%s' not found. Available agents: %s" % (profile_id, suffix))


async def _optional_profile(
    context: ToolRuntimeContext,
    base: AgentSpec,
    profile_id: str,
) -> AgentProfile | None:
    store = getattr(context, "agent_profile_store", None)
    if store is None:
        return None
    return await _load_profile(context, base, profile_id)


async def _load_profile(
    context: ToolRuntimeContext,
    base: AgentSpec,
    profile_id: str,
) -> AgentProfile | None:
    store = getattr(context, "agent_profile_store", None)
    if store is None:
        return None
    workspace = context.workspace
    tenant_id = base.workspace.tenant_id or workspace.tenant_id
    user_id = base.workspace.user_id or workspace.user_id
    return await store.load(tenant_id, user_id, profile_id)


async def _available_profile_ids(context: ToolRuntimeContext, base: AgentSpec) -> list[str]:
    store = getattr(context, "agent_profile_store", None)
    if store is None:
        return []
    workspace = context.workspace
    tenant_id = base.workspace.tenant_id or workspace.tenant_id
    user_id = base.workspace.user_id or workspace.user_id
    profiles = await store.list_for_user(tenant_id, user_id)
    return sorted(profile.agent_id for profile in profiles)


def _text(value: object) -> str:
    return str(value or "").strip()
