from __future__ import annotations

from dataclasses import dataclass, replace

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
    metadata = _profile_metadata(profile)
    return SrcOriginAgentDefinitionOptions(
        background=_truthy(metadata.get("background")),
        isolation=_isolation(metadata.get("isolation")),
        max_turns=_positive_int(metadata.get("maxTurns") or metadata.get("max_turns")),
        required_mcp_servers=_string_list(
            metadata.get("requiredMcpServers") or metadata.get("required_mcp_servers")
        ),
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


def _profile_metadata(profile: AgentProfile) -> dict[str, object]:
    metadata = dict(profile.to_agent_spec().metadata)
    metadata.update(profile.metadata)
    return metadata


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


def _string_list(value: object) -> tuple[str, ...]:
    items = value if isinstance(value, (list, tuple, set)) else str(value or "").replace("\n", ",").split(",")
    return tuple(item for item in (str(item).strip() for item in items) if item)
