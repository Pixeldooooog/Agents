from __future__ import annotations

from dataclasses import replace

from agents.kernel.capabilities.tools.builtin.src_origin.agent_metadata import (
    metadata_value,
    parse_src_origin_name_list,
)
from agents.kernel.specs import AgentSpec


def apply_src_origin_agent_skills(
    spec: AgentSpec,
    metadata: dict[str, object],
) -> AgentSpec:
    found, value = metadata_value(metadata, "skills")
    if not found:
        return spec
    return replace(spec, skills=list(parse_src_origin_name_list(value)))
