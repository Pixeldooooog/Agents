from __future__ import annotations

from dataclasses import replace

from agents.kernel.capabilities.tools.builtin.src_origin.agent_metadata import metadata_value
from agents.kernel.specs import AgentSpec


def apply_src_origin_agent_context_options(
    spec: AgentSpec,
    metadata: dict[str, object],
) -> AgentSpec:
    found, value = metadata_value(metadata, "omitClaudeMd", "omit_claude_md")
    if not found or not _truthy(value):
        return spec
    spec_metadata = dict(spec.metadata)
    spec_metadata["omit_workspace_instructions"] = "true"
    spec_metadata["src_origin_omit_claude_md"] = "true"
    return replace(spec, metadata=spec_metadata)


def _truthy(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}
