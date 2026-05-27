from __future__ import annotations

from typing import Any

from agents.interfaces.bridge.payload_format import _compact_text, _csv_setting, _join_limited
from agents.kernel.governance import classify_tool_risk
from agents.kernel.schema import ToolSpec


def tools_payload(state: Any) -> list[list[str]]:
    active_tools = [str(name) for name in getattr(state, "active_tools", [])]
    if not active_tools:
        return [["tools", "none enabled"]]

    registry = getattr(getattr(getattr(state, "session", None), "runtime", None), "tools", None)
    rows: list[list[str]] = []
    for name in active_tools:
        spec = _tool_spec(registry, name)
        rows.append([name, _tool_detail(name, spec)])
    return rows


def permissions_payload(state: Any) -> list[list[str]]:
    active_tools = [str(name) for name in getattr(state, "active_tools", [])]
    approval_tools = [str(name) for name in getattr(state, "approval_tools", [])]
    high_risk_tools = [
        name
        for name in active_tools
        if classify_tool_risk(name).value in {"high", "critical"}
    ]
    agent_settings = getattr(state.settings, "agent", None)
    mcp_settings = getattr(state.settings, "mcp", None)
    return [
        ["profile", str(getattr(state, "permission", "") or "guarded")],
        ["runtime_mode", str(getattr(state, "permission_mode", "") or "auto")],
        ["approval_required", _join_limited(approval_tools) if approval_tools else "none"],
        ["active_tools", str(len(active_tools))],
        ["high_risk_tools", _join_limited(high_risk_tools) if high_risk_tools else "none"],
        ["sandbox_profile", str(getattr(agent_settings, "SANDBOX_PROFILE", "") or "-")],
        ["sandbox_provider", str(getattr(agent_settings, "SANDBOX_PROVIDER", "") or "local")],
        ["sandbox_allowed_commands", _join_limited(_csv_setting(getattr(agent_settings, "SANDBOX_ALLOWED_COMMANDS", "")))],
        ["mcp_execution_mode", str(getattr(mcp_settings, "EXECUTION_MODE", "") or "-")],
    ]


def _tool_spec(registry: Any, name: str) -> ToolSpec | None:
    if registry is None or not hasattr(registry, "specs"):
        return None
    try:
        specs = list(registry.specs([name]))
    except Exception:
        return None
    return specs[0] if specs else None


def _tool_detail(name: str, spec: ToolSpec | None) -> str:
    metadata = _tool_metadata(spec)
    source = str(metadata.get("source") or _tool_source(name, spec))
    risk = str(metadata.get("risk") or classify_tool_risk(name).value)
    flags = _tool_flags(metadata)
    description = _compact_text(str(getattr(spec, "description", "") or ""))
    parts = ["enabled", source, "risk %s" % risk, flags, description]
    return " · ".join(part for part in parts if part)


def _tool_metadata(spec: ToolSpec | None) -> dict[str, Any]:
    raw = getattr(spec, "raw", None)
    if isinstance(raw, dict) and isinstance(raw.get("metadata"), dict):
        return dict(raw["metadata"])
    return {}


def _tool_source(name: str, spec: ToolSpec | None) -> str:
    if _is_mcp_tool_name(name) or name.startswith("mcp."):
        return "mcp"
    if name.startswith("memory."):
        return "memory"
    if name.startswith("skill."):
        return "skill"
    if name.startswith("tool."):
        return "meta"
    if name.startswith("todo."):
        return "todo"
    if name.startswith("plan."):
        return "plan"
    if name.startswith("task."):
        return "task"
    if name.startswith("agent."):
        return "agent"
    source = str(getattr(spec, "source", "") or "")
    return source if source and source != "registry" else "builtin"


def _tool_flags(metadata: dict[str, Any]) -> str:
    flags = []
    if metadata.get("writes_files"):
        flags.append("writes")
    if metadata.get("writes_state"):
        flags.append("state")
    if metadata.get("requires_process"):
        flags.append("process")
    if metadata.get("requires_network"):
        flags.append("network")
    if metadata.get("spawns_agent"):
        flags.append("agent")
    if metadata.get("model_call"):
        flags.append("model")
    return ", ".join(flags)


def _mcp_summary(state: Any) -> str:
    mcp_settings = getattr(state.settings, "mcp", None)
    command = str(getattr(mcp_settings, "SERVER_COMMAND", "") or "").strip()
    url = str(getattr(mcp_settings, "SERVER_URL", "") or "").strip()
    if not command and not url:
        return "not configured"
    count = len([name for name in getattr(state, "active_tools", []) if _is_mcp_tool_name(name)])
    return "%s · %s tools" % (getattr(mcp_settings, "SERVER_NAME", "") or "default", count)


def _is_mcp_tool_name(name: Any) -> bool:
    return str(name).startswith("mcp_")
