from __future__ import annotations

from dataclasses import dataclass, replace

from agents.kernel.capabilities.tools.builtin.src_origin.agent_metadata import (
    metadata_string_list,
    src_origin_profile_metadata,
)
from agents.kernel.specs import AgentSpec
from agents.kernel.state import AgentProfile


@dataclass(frozen=True)
class SrcOriginAgentDefinitionOptions:
    background: bool = False
    isolation: str = ""
    max_turns: int = 0
    required_mcp_servers: tuple[str, ...] = ()


def src_origin_agent_definition_options(profile: AgentProfile | None) -> SrcOriginAgentDefinitionOptions:
    if profile is None:
        return SrcOriginAgentDefinitionOptions()
    metadata = src_origin_profile_metadata(profile)
    return SrcOriginAgentDefinitionOptions(
        background=_truthy(metadata.get("background")),
        isolation=_isolation(metadata.get("isolation")),
        max_turns=_positive_int(metadata.get("maxTurns") or metadata.get("max_turns")),
        required_mcp_servers=metadata_string_list(metadata, "requiredMcpServers", "required_mcp_servers"),
    )


def apply_src_origin_agent_definition_options(
    spec: AgentSpec,
    options: SrcOriginAgentDefinitionOptions,
) -> AgentSpec:
    if not options.max_turns:
        return spec
    metadata = dict(spec.metadata)
    metadata["max_tool_iterations"] = str(options.max_turns)
    metadata["src_origin_max_turns"] = str(options.max_turns)
    return replace(spec, metadata=metadata)


def _truthy(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _isolation(value: object) -> str:
    isolation = str(value or "").strip().lower()
    return isolation if isolation == "worktree" else ""


def _positive_int(value: object) -> int:
    try:
        parsed = int(str(value or "").strip())
    except ValueError:
        return 0
    return parsed if parsed > 0 else 0
