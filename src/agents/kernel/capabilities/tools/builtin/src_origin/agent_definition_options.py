from __future__ import annotations

from dataclasses import dataclass

from agents.kernel.state import AgentProfile


@dataclass(frozen=True)
class SrcOriginAgentDefinitionOptions:
    background: bool = False
    isolation: str = ""


def src_origin_agent_definition_options(profile: AgentProfile | None) -> SrcOriginAgentDefinitionOptions:
    if profile is None:
        return SrcOriginAgentDefinitionOptions()
    metadata = _profile_metadata(profile)
    return SrcOriginAgentDefinitionOptions(
        background=_truthy(metadata.get("background")),
        isolation=_isolation(metadata.get("isolation")),
    )


def _profile_metadata(profile: AgentProfile) -> dict[str, object]:
    metadata = dict(profile.to_agent_spec().metadata)
    metadata.update(profile.metadata)
    return metadata


def _truthy(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _isolation(value: object) -> str:
    isolation = str(value or "").strip().lower()
    return isolation if isolation == "worktree" else ""
