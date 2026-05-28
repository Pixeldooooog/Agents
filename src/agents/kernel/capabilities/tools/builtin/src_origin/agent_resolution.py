from __future__ import annotations

from dataclasses import dataclass, replace

from agents.kernel.capabilities.tools.builtin.agent_child_specs import runtime_agent_spec
from agents.kernel.capabilities.tools.builtin.src_origin.agent_definition_options import (
    apply_src_origin_agent_definition_options,
    src_origin_agent_definition_options,
)
from agents.kernel.capabilities.tools.builtin.src_origin.agent_mcp_requirements import (
    validate_src_origin_required_mcp_servers,
)
from agents.kernel.capabilities.tools.builtin.src_origin.agent_profile_spec import (
    apply_src_origin_agent_profile_spec,
)
from agents.kernel.capabilities.tools.builtin.src_origin.agent_profile_lookup import (
    lookup_src_origin_agent_profile,
)
from agents.kernel.capabilities.tools.context import ToolRuntimeContext
from agents.kernel.specs import AgentSpec
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
        base = apply_src_origin_agent_profile_spec(base, profile)
    options = src_origin_agent_definition_options(profile)
    base = apply_src_origin_agent_definition_options(_apply_model_override(base, model), options)
    agent_id = _selected_agent_id(name=name, subagent_type=lookup.requested_type, profile=profile)
    validate_src_origin_required_mcp_servers(
        context,
        agent_id=agent_id,
        required_servers=options.required_mcp_servers,
    )
    return SrcOriginAgentSelection(
        agent_id=agent_id,
        base_spec=base,
        background=options.background,
        isolation=options.isolation,
    )


def _apply_model_override(spec: AgentSpec, model: str) -> AgentSpec:
    value = _text(model)
    if not value or value.lower() == "inherit":
        return spec
    return replace(spec, model=replace(spec.model, model=value))


def _selected_agent_id(*, name: str, subagent_type: str, profile: AgentProfile | None) -> str:
    return _text(name) or _text(subagent_type) or _text(profile.agent_id if profile is not None else "")


def _text(value: object) -> str:
    return str(value or "").strip()
