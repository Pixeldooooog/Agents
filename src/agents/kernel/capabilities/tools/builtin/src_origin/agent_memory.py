from __future__ import annotations

from dataclasses import replace

from agents.kernel.capabilities.tools.builtin.src_origin.agent_metadata import metadata_value
from agents.kernel.specs import AgentSpec


SRC_ORIGIN_MEMORY_SCOPES = {"user", "project", "local"}


def apply_src_origin_agent_memory(
    spec: AgentSpec,
    metadata: dict[str, object],
) -> AgentSpec:
    found, value = metadata_value(metadata, "memory")
    if not found:
        return spec
    scope = str(value or "").strip().lower()
    if scope not in SRC_ORIGIN_MEMORY_SCOPES:
        return spec
    spec_metadata = dict(spec.metadata)
    spec_metadata["src_origin_memory_scope"] = scope
    return replace(
        spec,
        memory_profile="src-origin:%s" % scope,
        metadata=spec_metadata,
    )
