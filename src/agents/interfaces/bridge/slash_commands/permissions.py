from __future__ import annotations

from typing import Any

from agents.interfaces.bridge.payloads import permissions_payload
from agents.interfaces.bridge.slash_commands.common import (
    BridgeWriter,
    agent_spec_for_state,
    split_once,
    tool_context,
)
from agents.kernel.capabilities.tools.builtin.permissions import permission_add_rule, permission_remove_rule, permission_sources
from agents.kernel.governance import build_tool_permission_policy
from agents.kernel.session_state import save_session_state
from agents.platform.profiles import permission_settings


async def handle_permissions_command(state: Any, argument: str, *, write: BridgeWriter) -> None:
    action, rest = split_once(argument)
    if action == "audit":
        await _handle_permissions_audit(state, rest, write=write)
        return
    if action in {"sources", "rules"}:
        _handle_permissions_sources(state, write=write)
        return
    if action in {"allow", "deny", "ask"} and rest.strip():
        await _handle_permission_rule_command(state, action, rest, write=write)
        return
    if action in {"remove", "unset"}:
        await _handle_permission_remove_rule_command(state, rest, write=write)
        return
    requested = rest if action == "set" else action
    if not requested:
        write({"type": "permissions", "permissions": permissions_payload(state)})
        return
    try:
        permission_mode, approval_tools = permission_settings(requested, state.profile)
    except Exception as exc:
        write({"type": "error", "message": str(exc)})
        return
    state.permission = requested
    state.permission_mode = permission_mode
    state.approval_tools = approval_tools
    set_runtime_permission_policy(state)
    await persist_permission_override(state)
    write({"type": "notice", "message": "permission switched: %s -> %s" % (state.permission, state.permission_mode)})
    write({"type": "permissions", "permissions": permissions_payload(state)})


def set_runtime_permission_policy(state: Any) -> None:
    runtime = getattr(state.session, "runtime", None)
    orchestrator = getattr(runtime, "tool_orchestrator", None)
    if orchestrator is None:
        return
    orchestrator.permission_policy = build_tool_permission_policy(agent_spec_for_state(state))


async def persist_permission_override(state: Any) -> None:
    context = tool_context(state)
    if context is None:
        return
    context.permission_overridden = True
    context.permission_profile_override = str(getattr(state, "permission", "") or "")
    context.permission_mode_override = str(getattr(state, "permission_mode", "") or "")
    spec = agent_spec_for_state(state)
    permissions = spec.tool_permissions
    context.permission_restrict_allowed_tools = permissions.allowed_tools is not None
    context.permission_allowed_tools_override = [str(tool) for tool in list(permissions.allowed_tools or [])]
    context.permission_denied_tools_override = [str(tool) for tool in list(permissions.denied_tools or [])]
    context.approval_required_tools_override = [str(tool) for tool in list(getattr(state, "approval_tools", []) or [])]
    context.agent_spec = spec
    await save_session_state(context)


def sync_permission_state_from_context(state: Any) -> None:
    context = tool_context(state)
    if context is None:
        return
    state.permission = str(getattr(context, "permission_profile_override", "") or getattr(state, "permission", ""))
    state.permission_mode = str(getattr(context, "permission_mode_override", "") or getattr(state, "permission_mode", ""))
    state.approval_tools = [str(tool) for tool in list(getattr(context, "approval_required_tools_override", []) or [])]


async def _handle_permissions_audit(state: Any, run_id: str, *, write: BridgeWriter) -> None:
    target = run_id.strip()
    if not target:
        write({"type": "error", "message": "usage: /permissions audit <run_id>"})
        return
    store = getattr(getattr(state, "persistence", None), "approval_audit", None)
    list_for_run = getattr(store, "list_for_run", None)
    if list_for_run is None:
        write({"type": "error", "message": "approval audit store is not available"})
        return
    records = await list_for_run(target)
    rows = []
    for record in records:
        risk = str((record.impact or {}).get("risk") or "unknown")
        decision = record.decision if record.approved else "deny"
        rows.append([record.approval_id, "%s · %s · risk %s" % (record.tool_name, decision, risk)])
    write({"type": "permissions", "permissions": rows or [["audit", "none for run %s" % target]]})


def _handle_permissions_sources(state: Any, *, write: BridgeWriter) -> None:
    context = tool_context(state)
    if context is None:
        write({"type": "error", "message": "tool context is not available"})
        return
    payload = permission_sources(context)
    rows = [
        ["mode", str(payload.get("mode") or "")],
        ["permission_profile", str(payload.get("permission_profile") or "")],
        ["runtime_policy", str(payload.get("runtime_policy") or "-") or "-"],
    ]
    for rule in list(payload.get("rules") or []):
        key = "%s:%s" % (rule.get("source", ""), rule.get("behavior", ""))
        detail = str(rule.get("tool") or "")
        if rule.get("content"):
            detail = "%s · %s" % (detail, rule["content"])
        rows.append([key, detail])
    for item in list(payload.get("settings") or []):
        rows.append([str(item.get("source") or ""), "%s=%s" % (item.get("key", ""), item.get("value", ""))])
    write({"type": "permissions", "permissions": rows})


async def _handle_permission_rule_command(state: Any, behavior: str, tool: str, *, write: BridgeWriter) -> None:
    context = tool_context(state)
    if context is None:
        write({"type": "error", "message": "tool context is not available"})
        return
    try:
        await permission_add_rule(context, behavior=behavior, tool=tool.strip())
    except Exception as exc:  # noqa: BLE001 - permission rule errors are command output.
        write({"type": "error", "message": "permission rule failed: %s" % exc})
        return
    sync_permission_state_from_context(state)
    write({"type": "notice", "message": "permission rule added: %s %s" % (behavior, tool.strip())})
    _handle_permissions_sources(state, write=write)


async def _handle_permission_remove_rule_command(state: Any, rest: str, *, write: BridgeWriter) -> None:
    behavior, tool = _parse_permission_remove(rest)
    if not tool:
        write({"type": "error", "message": "usage: /permissions remove [allow|deny|ask] <tool>"})
        return
    context = tool_context(state)
    if context is None:
        write({"type": "error", "message": "tool context is not available"})
        return
    try:
        await permission_remove_rule(context, tool=tool, behavior=behavior)
    except Exception as exc:  # noqa: BLE001 - permission rule errors are command output.
        write({"type": "error", "message": "permission rule remove failed: %s" % exc})
        return
    sync_permission_state_from_context(state)
    write({"type": "notice", "message": "permission rule removed: %s" % tool})
    _handle_permissions_sources(state, write=write)


def _parse_permission_remove(rest: str) -> tuple[str, str]:
    behavior, tool = split_once(rest)
    if behavior in {"allow", "deny", "ask"}:
        return behavior, tool.strip()
    return "", str(rest or "").strip()
