from __future__ import annotations

from dataclasses import replace

from agents.kernel.capabilities.tools.builtin.src_origin.agent_metadata import metadata_value
from agents.kernel.specs import AgentSpec


def apply_src_origin_agent_system_reminder(
    spec: AgentSpec,
    metadata: dict[str, object],
) -> AgentSpec:
    found, value = metadata_value(
        metadata,
        "criticalSystemReminder_EXPERIMENTAL",
        "criticalSystemReminder",
        "critical_system_reminder",
    )
    if not found:
        return spec
    reminder = str(value or "").strip()
    if not reminder:
        return spec
    spec_metadata = dict(spec.metadata)
    spec_metadata["critical_system_reminder"] = reminder
    spec_metadata["src_origin_critical_system_reminder"] = "true"
    return replace(spec, metadata=spec_metadata)
