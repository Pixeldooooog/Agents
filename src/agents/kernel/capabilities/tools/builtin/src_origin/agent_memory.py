from __future__ import annotations

from dataclasses import replace

from agents.kernel.capabilities.tools.builtin.src_origin.agent_metadata import metadata_value
from agents.kernel.specs import AgentSpec


SRC_ORIGIN_MEMORY_SCOPES = {"user", "project", "local"}
SRC_ORIGIN_MEMORY_TOOLS = ("filesystem.write", "patch.apply", "filesystem.read")


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
    return _with_memory_tools(_with_memory_profile(spec, scope))


def _with_memory_profile(spec: AgentSpec, scope: str) -> AgentSpec:
    spec_metadata = dict(spec.metadata)
    spec_metadata["src_origin_memory_scope"] = scope
    return replace(
        spec,
        memory_profile="src-origin:%s" % scope,
        metadata=spec_metadata,
    )


def _with_memory_tools(spec: AgentSpec) -> AgentSpec:
    if spec.enabled_tools is None:
        return spec
    enabled_tools = _merge_unique(spec.enabled_tools, SRC_ORIGIN_MEMORY_TOOLS)
    if enabled_tools == spec.enabled_tools:
        return spec
    return replace(spec, enabled_tools=enabled_tools)


def _merge_unique(existing: list[str], additions: tuple[str, ...]) -> list[str]:
    merged = list(existing)
    seen = set(merged)
    for item in additions:
        if item in seen:
            continue
        seen.add(item)
        merged.append(item)
    return merged
