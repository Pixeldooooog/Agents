from __future__ import annotations

from dataclasses import replace
from typing import Any

from agents.kernel.capabilities.tools.context import ToolRuntimeContext
from agents.kernel.governance import build_tool_permission_policy, describe_tool_impact
from agents.kernel.schema import ToolCall
from agents.kernel.specs import AgentSpec
from agents.kernel.session_state import save_session_state


PERMISSION_STATUS_SCHEMA = {"type": "object", "properties": {}}
PERMISSION_SOURCES_SCHEMA = {"type": "object", "properties": {}}

PERMISSION_EXPLAIN_SCHEMA = {
    "type": "object",
    "properties": {
        "tool": {"type": "string", "description": "Tool name to check."},
        "arguments": {"type": "object", "additionalProperties": True},
    },
    "required": ["tool"],
}

PERMISSION_RULE_SCHEMA = {
    "type": "object",
    "properties": {
        "behavior": {"type": "string", "enum": ["allow", "deny", "ask"]},
        "tool": {"type": "string", "description": "Tool name, wildcard, or command rule such as Bash(git *) / shell.run(git:*)."},
    },
    "required": ["behavior", "tool"],
}

PERMISSION_REMOVE_RULE_SCHEMA = {
    "type": "object",
    "properties": {
        "tool": {"type": "string", "description": "Tool name, wildcard, or command rule such as Bash(git *) / shell.run(git:*)."},
        "behavior": {"type": "string", "enum": ["", "allow", "deny", "ask"], "description": "Optional behavior to remove."},
    },
    "required": ["tool"],
}


def permission_sources(context: ToolRuntimeContext) -> dict[str, Any]:
    spec = _agent_spec(context)
    permissions = spec.tool_permissions
    return {
        "mode": permissions.normalized_mode(),
        "permission_profile": spec.permission_profile or permissions.mode,
        "rules": [rule.to_dict() for rule in permissions.rules(source="agent_spec")],
        "rules_by_source": permissions.rules_by_source(source="agent_spec"),
        "restrict_allowed_tools": permissions.allowed_tools is not None,
        "runtime_policy": type(_runtime_permission_policy(context)).__name__ if _runtime_permission_policy(context) is not None else "",
        "settings": _settings_sources(context),
        "enabled_tools": list(getattr(context, "enabled_tools", []) or []),
    }


def permission_status(context: ToolRuntimeContext) -> dict[str, Any]:
    spec = _agent_spec(context)
    permissions = spec.tool_permissions
    runtime_policy = _runtime_permission_policy(context)
    return {
        "profile": permissions.normalized_mode(),
        "permission_profile": spec.permission_profile or permissions.mode,
        "allowed_tools": list(permissions.allowed_tools or []),
        "restrict_allowed_tools": permissions.allowed_tools is not None,
        "denied_tools": list(permissions.denied_tools),
        "approval_required_tools": list(permissions.approval_required_tools),
        "enabled_tools": list(getattr(context, "enabled_tools", []) or []),
        "runtime_policy": type(runtime_policy).__name__ if runtime_policy is not None else "",
        "rules_by_source": permissions.rules_by_source(source="agent_spec"),
    }


async def permission_explain(
    context: ToolRuntimeContext,
    tool: str,
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    call = ToolCall(id="permission_explain", name=_required_text(tool, "tool"), arguments=dict(arguments or {}))
    policy = _runtime_permission_policy(context) or build_tool_permission_policy(_agent_spec(context))
    decision = await policy.authorize(call)
    return {
        "tool": call.name,
        "arguments": dict(call.arguments),
        "decision": decision.to_dict(),
        "impact": describe_tool_impact(call).to_dict(),
    }


async def permission_add_rule(context: ToolRuntimeContext, behavior: str, tool: str) -> dict[str, Any]:
    behavior = _permission_behavior(behavior)
    tool_name = _required_text(tool, "tool")
    spec = _agent_spec(context)
    permissions = spec.tool_permissions
    allowed = list(permissions.allowed_tools or [])
    denied = list(permissions.denied_tools)
    approval = list(permissions.approval_required_tools)
    restrict_allowed = permissions.allowed_tools is not None
    if behavior == "allow":
        restrict_allowed = True
        allowed = _add_unique(allowed, tool_name)
        denied = _remove_value(denied, tool_name)
        approval = _remove_value(approval, tool_name)
    elif behavior == "deny":
        denied = _add_unique(denied, tool_name)
        allowed = _remove_value(allowed, tool_name)
        approval = _remove_value(approval, tool_name)
    elif behavior == "ask":
        approval = _add_unique(approval, tool_name)
        allowed = _remove_value(allowed, tool_name)
        denied = _remove_value(denied, tool_name)
    updated = replace(
        spec,
        tool_permissions=replace(
            permissions,
            allowed_tools=allowed if restrict_allowed else None,
            denied_tools=denied,
            approval_required_tools=approval,
        ),
    )
    await _apply_permission_spec(context, updated)
    return {"added": {"behavior": behavior, "tool": tool_name}, "status": permission_status(context)}


async def permission_remove_rule(context: ToolRuntimeContext, tool: str, behavior: str = "") -> dict[str, Any]:
    tool_name = _required_text(tool, "tool")
    behavior = str(behavior or "").strip().lower()
    if behavior and behavior not in {"allow", "deny", "ask"}:
        raise ValueError("unknown permission behavior: %s" % behavior)
    spec = _agent_spec(context)
    permissions = spec.tool_permissions
    allowed = list(permissions.allowed_tools or [])
    denied = list(permissions.denied_tools)
    approval = list(permissions.approval_required_tools)
    restrict_allowed = permissions.allowed_tools is not None
    removed: list[dict[str, str]] = []
    if behavior in {"", "allow"} and tool_name in allowed:
        allowed = _remove_value(allowed, tool_name)
        removed.append({"behavior": "allow", "tool": tool_name})
    if behavior in {"", "deny"} and tool_name in denied:
        denied = _remove_value(denied, tool_name)
        removed.append({"behavior": "deny", "tool": tool_name})
    if behavior in {"", "ask"} and tool_name in approval:
        approval = _remove_value(approval, tool_name)
        removed.append({"behavior": "ask", "tool": tool_name})
    if restrict_allowed and not allowed:
        restrict_allowed = False
    updated = replace(
        spec,
        tool_permissions=replace(
            permissions,
            allowed_tools=allowed if restrict_allowed else None,
            denied_tools=denied,
            approval_required_tools=approval,
        ),
    )
    await _apply_permission_spec(context, updated)
    return {"removed": removed, "status": permission_status(context)}


def _runtime_permission_policy(context: ToolRuntimeContext) -> Any | None:
    session = getattr(context, "session", None)
    runtime = getattr(session, "runtime", None)
    orchestrator = getattr(runtime, "tool_orchestrator", None)
    return getattr(orchestrator, "permission_policy", None)


async def _apply_permission_spec(context: ToolRuntimeContext, spec: AgentSpec) -> None:
    context.agent_spec = spec
    permissions = spec.tool_permissions
    context.permission_overridden = True
    context.permission_profile_override = spec.permission_profile or permissions.mode or "auto"
    context.permission_mode_override = permissions.normalized_mode()
    context.permission_restrict_allowed_tools = permissions.allowed_tools is not None
    context.permission_allowed_tools_override = list(permissions.allowed_tools or [])
    context.permission_denied_tools_override = list(permissions.denied_tools)
    context.approval_required_tools_override = list(permissions.approval_required_tools)
    session = getattr(context, "session", None)
    runtime = getattr(session, "runtime", None)
    orchestrator = getattr(runtime, "tool_orchestrator", None)
    if orchestrator is not None:
        orchestrator.permission_policy = build_tool_permission_policy(spec)
    await save_session_state(context)


def _agent_spec(context: ToolRuntimeContext) -> AgentSpec:
    spec = getattr(context, "agent_spec", None)
    if isinstance(spec, AgentSpec):
        return spec
    workspace = context.workspace
    return AgentSpec.from_overrides(
        tenant_id=workspace.tenant_id,
        user_id=workspace.user_id,
        agent_id=workspace.agent_id,
        workspace_id=workspace.workspace_id,
        workspace_path=str(workspace.path),
        enabled_tools=list(getattr(context, "enabled_tools", []) or []),
    )


def _settings_sources(context: ToolRuntimeContext) -> list[dict[str, str]]:
    settings = getattr(context, "settings", None)
    rows: list[dict[str, str]] = []
    agent_settings = getattr(settings, "agent", None)
    if agent_settings is not None:
        for name in ["SANDBOX_PROFILE", "SANDBOX_PROVIDER", "SANDBOX_ALLOWED_COMMANDS"]:
            value = str(getattr(agent_settings, name, "") or "")
            if value:
                rows.append({"source": "settings.agent", "key": name, "value": value})
    mcp_settings = getattr(settings, "mcp", None)
    if mcp_settings is not None:
        value = str(getattr(mcp_settings, "EXECUTION_MODE", "") or "")
        if value:
            rows.append({"source": "settings.mcp", "key": "EXECUTION_MODE", "value": value})
    return rows


def _required_text(value: Any, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError("%s is required" % name)
    return text


def _permission_behavior(value: Any) -> str:
    behavior = str(value or "").strip().lower()
    if behavior not in {"allow", "deny", "ask"}:
        raise ValueError("unknown permission behavior: %s" % behavior)
    return behavior


def _add_unique(items: list[str], value: str) -> list[str]:
    return [*items, value] if value not in items else items


def _remove_value(items: list[str], value: str) -> list[str]:
    return [item for item in items if item != value]
