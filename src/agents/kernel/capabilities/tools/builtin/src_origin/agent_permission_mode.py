from __future__ import annotations

from dataclasses import replace

from agents.kernel.capabilities.tools.builtin.src_origin.agent_metadata import metadata_value
from agents.kernel.specs import AgentSpec


_SRC_ORIGIN_PERMISSION_MODES = {
    "acceptEdits": "auto",
    "auto": "auto",
    "bubble": "ask",
    "bypassPermissions": "auto",
    "default": "auto",
    "dontAsk": "auto",
    "plan": "ask",
    "ask": "ask",
    "deny": "deny",
}


def apply_src_origin_agent_permission_mode(
    spec: AgentSpec,
    metadata: dict[str, object],
) -> AgentSpec:
    mode = _permission_mode(metadata)
    if mode is None:
        return spec
    permissions = replace(spec.tool_permissions, mode=_SRC_ORIGIN_PERMISSION_MODES[mode])
    return replace(spec, permission_profile=mode, tool_permissions=permissions)


def _permission_mode(metadata: dict[str, object]) -> str | None:
    found, value = metadata_value(metadata, "permissionMode", "permission_mode")
    if not found:
        return None
    mode = str(value or "").strip()
    return mode if mode in _SRC_ORIGIN_PERMISSION_MODES else None
