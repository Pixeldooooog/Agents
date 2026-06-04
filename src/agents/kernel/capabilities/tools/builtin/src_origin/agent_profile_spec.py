from __future__ import annotations

from dataclasses import replace

from agents.kernel.capabilities.tools.builtin.src_origin.agent_metadata import src_origin_profile_metadata
from agents.kernel.capabilities.tools.builtin.src_origin.agent_initial_prompt import apply_src_origin_agent_initial_prompt
from agents.kernel.capabilities.tools.builtin.src_origin.agent_memory import apply_src_origin_agent_memory
from agents.kernel.capabilities.tools.builtin.src_origin.agent_context_options import apply_src_origin_agent_context_options
from agents.kernel.capabilities.tools.builtin.src_origin.agent_permission_mode import (
    apply_src_origin_agent_permission_mode,
)
from agents.kernel.capabilities.tools.builtin.src_origin.agent_skills import (
    apply_src_origin_agent_skills,
)
from agents.kernel.capabilities.tools.builtin.src_origin.agent_system_reminder import (
    apply_src_origin_agent_system_reminder,
)
from agents.kernel.capabilities.tools.builtin.src_origin.agent_tool_rules import (
    apply_src_origin_agent_tool_rules,
)
from agents.kernel.specs import AgentModelSpec, AgentSpec
from agents.kernel.state import AgentProfile


def apply_src_origin_agent_profile_spec(base: AgentSpec, profile: AgentProfile) -> AgentSpec:
    profile_spec = profile.to_agent_spec()
    metadata = dict(base.metadata)
    metadata["src_origin_agent_profile"] = profile.agent_id
    spec = replace(
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
    profile_metadata = src_origin_profile_metadata(profile)
    spec = apply_src_origin_agent_skills(spec, profile_metadata)
    spec = apply_src_origin_agent_permission_mode(spec, profile_metadata)
    spec = apply_src_origin_agent_initial_prompt(spec, profile_metadata)
    spec = apply_src_origin_agent_memory(spec, profile_metadata)
    spec = apply_src_origin_agent_context_options(spec, profile_metadata)
    spec = apply_src_origin_agent_system_reminder(spec, profile_metadata)
    return apply_src_origin_agent_tool_rules(spec, profile_metadata)


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


def _text(value: object) -> str:
    return str(value or "").strip()
