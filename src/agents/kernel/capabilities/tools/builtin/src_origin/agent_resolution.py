from __future__ import annotations

from dataclasses import dataclass, replace

from agents.kernel.capabilities.tools.builtin.agent_child_specs import runtime_agent_spec
from agents.kernel.capabilities.tools.builtin.src_origin.agent_definition_options import (
    src_origin_agent_definition_options,
)
from agents.kernel.capabilities.tools.builtin.src_origin.agent_profile_lookup import (
    lookup_src_origin_agent_profile,
)
from agents.kernel.capabilities.tools.context import ToolRuntimeContext
from agents.kernel.specs import AgentModelSpec, AgentSpec
from agents.kernel.state import AgentProfile


@dataclass(frozen=True)
class SrcOriginAgentSelection:
    agent_id: str
    base_spec: AgentSpec
    background: bool = False
    isolation: str = ""


async def resolve_src_origin_agent_selection(
    context: ToolRuntimeContext,
    *,
    name: str = "",
    subagent_type: str = "",
    model: str = "",
    parent_spec: AgentSpec | None = None,
) -> SrcOriginAgentSelection:
    base = parent_spec or runtime_agent_spec(context)
    lookup = await lookup_src_origin_agent_profile(context, base, subagent_type)
    profile = lookup.profile
    if profile is not None:
        base = _apply_profile_spec(base, profile)
    base = _apply_model_override(base, model)
    options = src_origin_agent_definition_options(profile)
    return SrcOriginAgentSelection(
        agent_id=_selected_agent_id(name=name, subagent_type=lookup.requested_type, profile=profile),
        base_spec=base,
        background=options.background,
        isolation=options.isolation,
    )


def _apply_profile_spec(base: AgentSpec, profile: AgentProfile) -> AgentSpec:
    profile_spec = profile.to_agent_spec()
    metadata = dict(base.metadata)
    metadata["src_origin_agent_profile"] = profile.agent_id
    return replace(
        base,
        model=_profile_model(base, profile_spec),
        system_prompt=profile_spec.system_prompt if profile_spec.system_prompt is not None else base.system_prompt,
        enabled_tools=(
            list(profile_spec.enabled_tools)
            if profile_spec.enabled_tools is not None
            else base.enabled_tools
        ),
        skills=list(profile_spec.skills) if profile_spec.skills is not None else base.skills,
        permission_profile=profile_spec.permission_profile or base.permission_profile,
        tool_permissions=profile_spec.tool_permissions,
        memory_profile=profile_spec.memory_profile or base.memory_profile,
        metadata=metadata,
    )


def _profile_model(base: AgentSpec, profile_spec: AgentSpec) -> AgentModelSpec:
    if not _has_model_override(profile_spec):
        return base.model
    profile_model = profile_spec.model
    if _text(profile_model.model).lower() == "inherit" and not any(
        _text(value)
        for value in (
            profile_model.protocol,
            profile_model.base_url,
            profile_model.api_key,
        )
    ):
        return base.model
    return profile_model


def _apply_model_override(spec: AgentSpec, model: str) -> AgentSpec:
    value = _text(model)
    if not value or value.lower() == "inherit":
        return spec
    return replace(spec, model=replace(spec.model, model=value))


def _has_model_override(spec: AgentSpec) -> bool:
    return any(
        _text(value)
        for value in (
            spec.model.protocol,
            spec.model.model,
            spec.model.base_url,
            spec.model.api_key,
        )
    )


def _selected_agent_id(
    *,
    name: str,
    subagent_type: str,
    profile: AgentProfile | None,
) -> str:
    return _text(name) or _text(subagent_type) or _text(profile.agent_id if profile is not None else "")


def _text(value: object) -> str:
    return str(value or "").strip()
