from __future__ import annotations

from dataclasses import replace
from typing import Mapping

from agents.kernel.capabilities.tools.builtin.src_origin.agent_metadata import metadata_value
from agents.kernel.specs import AgentSpec


def apply_src_origin_agent_initial_prompt(
    spec: AgentSpec,
    metadata: dict[str, object],
) -> AgentSpec:
    found, value = metadata_value(metadata, "initialPrompt", "initial_prompt")
    if not found:
        return spec
    initial_prompt = _clean_text(value)
    if not initial_prompt:
        return spec
    spec_metadata = dict(spec.metadata)
    spec_metadata["initial_prompt"] = initial_prompt
    spec_metadata["src_origin_initial_prompt"] = "true"
    return replace(spec, metadata=spec_metadata)


def prompt_with_src_origin_initial_prompt(prompt: str, metadata: Mapping[str, object]) -> str:
    initial_prompt = _clean_text(metadata.get("initial_prompt"))
    user_prompt = _clean_text(prompt)
    if not initial_prompt:
        return user_prompt
    if not user_prompt:
        return initial_prompt
    return "%s\n\n%s" % (initial_prompt, user_prompt)


def _clean_text(value: object) -> str:
    return str(value or "").strip()
