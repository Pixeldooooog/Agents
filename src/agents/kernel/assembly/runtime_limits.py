from __future__ import annotations

from typing import Any

from agents.kernel.specs import AgentSpec


def runtime_max_tool_iterations(settings: Any, spec: AgentSpec) -> int | None:
    override = _positive_int(
        spec.metadata.get("max_tool_iterations")
        or spec.metadata.get("maxTurns")
        or spec.metadata.get("max_turns")
    )
    if override is not None:
        return override
    value = getattr(settings.agent, "MAX_TOOL_ITERATIONS", 0)
    return int(value) if value is not None else None


def _positive_int(value: object) -> int | None:
    try:
        parsed = int(str(value or "").strip())
    except ValueError:
        return None
    return parsed if parsed > 0 else None
