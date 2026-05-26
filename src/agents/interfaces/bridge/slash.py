from __future__ import annotations

import asyncio
import json
import shutil
from collections.abc import Awaitable, Callable
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from agents.kernel.capabilities.memory import MemoryScope
from agents.kernel.capabilities.skills import SkillLoader
from agents.kernel.capabilities.tools.builtin.memory import memory_add, memory_edit, memory_forget
from agents.kernel.capabilities.tools.builtin.commands import (
    command_delete,
    command_read,
    command_render,
    command_save,
)
from agents.kernel.capabilities.tools.builtin.hooks import hook_add, hook_delete, hook_list
from agents.kernel.capabilities.tools.builtin.mcp.management import mcp_clear, mcp_configure, mcp_disable, mcp_enable, mcp_reload, mcp_remove
from agents.kernel.capabilities.tools.builtin.planning import plan_clear, plan_enter, plan_exit, todo_write
from agents.kernel.capabilities.tools.builtin.extensions import skill_install, skill_uninstall
from agents.kernel.capabilities.tools.builtin.permissions import permission_add_rule, permission_remove_rule, permission_sources
from agents.kernel.capabilities.tools.builtin.plugins import plugin_install, plugin_uninstall
from agents.kernel.capabilities.tools.builtin.prompts import prompt_delete, prompt_render, prompt_save
from agents.kernel.capabilities.tools.builtin.session_context import session_summary
from agents.kernel.config import resolve_model_profile
from agents.kernel.context import ContextLayer, ContextTraceItem
from agents.kernel.governance import build_tool_permission_policy
from agents.kernel.governance.permissions import ToolPermissionDecision
from agents.kernel.schema import ToolCall
from agents.kernel.session_state import save_session_state
from agents.kernel.state import AgentProfile
from agents.platform.profiles import permission_settings
from agents.interfaces.bridge.payloads import (
    agents_payload,
    capabilities_payload,
    commands_payload_for_state,
    context_payload,
    doctor_payload,
    hooks_payload,
    messages_payload,
    mcp_payload,
    memory_payload,
    model_profiles_payload,
    parse_positive_int,
    permissions_payload,
    plan_payload,
    plugins_payload,
    prompt_payload,
    runtime_payload,
    session_records_payload,
    session_payload,
    short_session_id,
    skills_payload,
    status_payload,
    todo_payload,
    trace_payload,
    tools_payload,
    workspace_payload,
)
from agents.interfaces.bridge.sessions import save_session_snapshot
from agents.interfaces.bridge.slash_commands.common import (
    BridgeWriter,
    agent_spec_for_state as _agent_spec_for_state,
    create_session_from_agent_profile as _create_session_from_agent_profile,
    error_message as _error_message,
    merge_unique as _merge_unique,
    split_once as _split_once,
    split_once_preserve as _split_once_preserve,
    tool_context as _tool_context,
)
from agents.interfaces.bridge.slash_commands.schedules import handle_schedules_command as _handle_schedules_command
from agents.interfaces.bridge.slash_commands.tasks import handle_tasks_command as _handle_tasks_command
from agents.interfaces.bridge.slash_commands.workflows import handle_workflows_command as _handle_workflows_command
from agents.interfaces.bridge.workspace_diff import diff_rows

MakeSession = Callable[..., Awaitable[Any]]
CloseSessionModelClient = Callable[[Any], Awaitable[None]]


async def handle_slash_command(
    state: Any,
    value: str,
    *,
    make_session: MakeSession,
    close_session_model_client: CloseSessionModelClient,
    write: BridgeWriter,
) -> None:
    parts = value.strip().split(maxsplit=1)
    command = parts[0] if parts else ""
    argument = parts[1] if len(parts) > 1 else ""
    if command in {"/quit", "/exit"}:
        write({"type": "exit"})
        return
    if command == "/clear":
        state.session.clear()
        save_session_snapshot(state)
        write({"type": "notice", "message": "cleared"})
        return
    if command in {"/help", "?"}:
        write({"type": "commands", "commands": commands_payload_for_state(state)})
        return
    if command in {"/commands", "/cmds"}:
        await _handle_commands_command(state, argument, write=write)
        return
    if command in {"/model", "/models"}:
        await _handle_model_command(state, argument, make_session=make_session, close_session_model_client=close_session_model_client, write=write)
        return
    if command in {"/sessions", "/resume"} and not argument:
        write({"type": "sessions", "sessions": session_records_payload(state.session_store.list())})
        return
    if command == "/sessions":
        _handle_sessions_command(state, argument, write=write)
        return
    if command == "/session":
        write({"type": "session", "session": session_payload(state)})
        return
    if command == "/summary":
        _handle_summary_command(state, argument, write=write)
        return
    if command == "/resume":
        await _handle_resume_command(state, argument, write=write)
        return
    if command == "/export":
        _handle_export_command(state, argument, write=write)
        return
    if command == "/fork":
        _handle_fork_command(state, argument, write=write)
        return
    if command == "/rewind":
        _handle_rewind_command(state, argument, write=write)
        return
    if command == "/agents":
        await _handle_agents_command(
            state,
            argument,
            close_session_model_client=close_session_model_client,
            write=write,
        )
        return
    if command == "/tasks":
        await _handle_tasks_command(state, argument, write=write)
        return
    if command in {"/schedules", "/schedule"}:
        await _handle_schedules_command(state, argument, write=write)
        return
    if command == "/hooks":
        await _handle_hooks_command(state, argument, write=write)
        return
    if command in {"/todo", "/todos"}:
        await _handle_todo_command(state, argument, write=write)
        return
    if command == "/plan":
        await _handle_plan_command(state, argument, write=write)
        return
    if command in {"/workflows", "/workflow"}:
        await _handle_workflows_command(state, argument, write=write)
        return
    if command in {"/capabilities", "/caps"}:
        write({"type": "capabilities", "capabilities": capabilities_payload(state)})
        return
    if command == "/plugins":
        await _handle_plugins_command(state, argument, write=write)
        return
    if command == "/status":
        write({"type": "status", "status": status_payload(state)})
        return
    if command == "/tools":
        write({"type": "tools", "tools": tools_payload(state)})
        return
    if command in {"/permissions", "/permission", "/perms"}:
        await _handle_permissions_command(state, argument, write=write)
        return
    if command == "/diff":
        write({"type": "diff", "diff": diff_rows(state)})
        return
    if command == "/workspace":
        write({"type": "workspace", "workspace": workspace_payload(state)})
        return
    if command == "/context":
        _handle_context_command(state, argument, write=write)
        return
    if command == "/trace":
        write({"type": "trace", "trace": trace_payload(state)})
        return
    if command == "/prompt":
        await _handle_prompt_command(state, argument, write=write)
        return
    if command == "/compact":
        _handle_compact_command(state, argument, write=write)
        return
    if command == "/doctor":
        write({"type": "doctor", "doctor": doctor_payload(state)})
        return
    if command == "/skills":
        await _handle_skills_command(state, argument, write=write)
        return
    if command == "/mcp":
        await _handle_mcp_command(state, argument, write=write)
        return
    if command == "/memory":
        await _handle_memory_command(state, argument, write=write)
        return
    write({"type": "error", "message": "unknown command: %s" % value})


async def _handle_model_command(
    state: Any,
    argument: str,
    *,
    make_session: MakeSession,
    close_session_model_client: CloseSessionModelClient,
    write: BridgeWriter,
) -> None:
    if argument:
        profile = resolve_model_profile(state.model_profiles, argument)
        if profile is None:
            write({"type": "error", "message": "unknown model profile: %s" % argument})
            return
        previous_messages = list(getattr(state.session, "messages", []))
        await close_session_model_client(state.session)
        state.session = await make_session(
            state.args,
            settings=state.settings,
            persistence=state.persistence,
            profile=state.profile,
            active_workspace=state.active_workspace,
            active_tools=state.active_tools,
            permission_mode=state.permission_mode,
            approval_tools=state.approval_tools,
            model_profile=profile,
        )
        state.session.messages = previous_messages
        _sync_extension_state_from_context(state)
        save_session_snapshot(state)
        write({"type": "model_switched", "profile": profile.name, "runtime": runtime_payload(state)})
    write({"type": "model_profiles", "profiles": model_profiles_payload(state)})


async def _handle_commands_command(state: Any, argument: str, *, write: BridgeWriter) -> None:
    action, rest = _split_once(argument)
    if not action or action in {"list", "ls"}:
        write({"type": "commands", "commands": commands_payload_for_state(state)})
        return
    context = _tool_context(state)
    if context is None:
        write({"type": "error", "message": "tool context is not available"})
        return
    if action in {"read", "show", "view"}:
        name = rest.strip()
        if not name:
            write({"type": "error", "message": "usage: /commands read <name>"})
            return
        try:
            payload = command_read(context, name)
        except Exception as exc:  # noqa: BLE001 - command file errors should be surfaced.
            write({"type": "error", "message": "command read failed: %s" % exc})
            return
        write({"type": "prompt", "prompt": _command_detail_rows(payload)})
        return
    if action == "render":
        name, arguments = _split_once_preserve(rest)
        if not name:
            write({"type": "error", "message": "usage: /commands render <name> [arguments]"})
            return
        try:
            payload = command_render(context, name, arguments=arguments)
        except Exception as exc:  # noqa: BLE001 - command rendering errors should be surfaced.
            write({"type": "error", "message": "command render failed: %s" % exc})
            return
        write({"type": "prompt", "prompt": [["command", payload["command"]["name"]], ["prompt", payload["prompt"]]]})
        return
    if action == "save":
        name, body = _parse_command_save(rest)
        if not name or not body:
            write({"type": "error", "message": "usage: /commands save <name> [description] -- <prompt>"})
            return
        payload = await _execute_slash_tool(
            state,
            tool_name="command.save",
            arguments={
                "name": name,
                "content": body,
                "description": _command_description(body),
                "overwrite": True,
            },
            write=write,
            error_label="command save",
            fallback=lambda: command_save(context, name=name, content=body, description=_command_description(body), overwrite=True),
        )
        if payload is None:
            return
        write({"type": "notice", "message": "command saved: %s" % payload["name"]})
        write({"type": "commands", "commands": commands_payload_for_state(state)})
        return
    if action in {"delete", "remove", "rm"}:
        name = rest.strip()
        if not name:
            write({"type": "error", "message": "usage: /commands delete <name>"})
            return
        payload = await _execute_slash_tool(
            state,
            tool_name="command.delete",
            arguments={"name": name},
            write=write,
            error_label="command delete",
            fallback=lambda: command_delete(context, name=name),
        )
        if payload is None:
            return
        if not payload.get("deleted"):
            write({"type": "error", "message": "command not found: %s" % payload["name"]})
            return
        write({"type": "notice", "message": "command deleted: %s" % payload["name"]})
        write({"type": "commands", "commands": commands_payload_for_state(state)})
        return
    write({"type": "error", "message": "unknown commands command: %s" % action})


async def _handle_resume_command(state: Any, argument: str, *, write: BridgeWriter) -> None:
    record = state.session_store.load(argument)
    if record is None:
        write({"type": "error", "message": "session not found: %s" % argument})
        return
    state.session.messages = list(record.messages)
    _sync_session_prompt_from_messages(state.session)
    state.session_id = record.session_id
    write({"type": "session_resumed", "session_id": record.session_id, "messages": messages_payload(record.messages)})
    write(
        {
            "type": "notice",
            "message": "resumed %s · %s messages" % (short_session_id(record.session_id), record.message_count),
        }
    )
    write({"type": "status", "status": status_payload(state)})
    if record.pending_run_id and record.pending_approval:
        await _restore_pending_approval(state, record, write=write)


def _handle_sessions_command(state: Any, argument: str, *, write: BridgeWriter) -> None:
    action, rest = _split_once(argument)
    if action in {"delete", "remove", "forget"}:
        target = rest.strip()
        if not target:
            write({"type": "error", "message": "usage: /sessions delete <id>"})
            return
        record = state.session_store.delete(target)
        if record is None:
            write({"type": "error", "message": "session not found: %s" % target})
            return
        write({"type": "notice", "message": "session deleted: %s" % short_session_id(record.session_id)})
        write({"type": "sessions", "sessions": session_records_payload(state.session_store.list())})
        return
    write({"type": "error", "message": "unknown sessions command: %s" % action})


def _handle_export_command(state: Any, argument: str, *, write: BridgeWriter) -> None:
    try:
        export_format, target = _parse_export_argument(state, argument)
        content = _session_export_content(state, export_format)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    except Exception as exc:  # noqa: BLE001 - command output should surface export failures.
        write({"type": "error", "message": "session export failed: %s" % exc})
        return
    write({"type": "notice", "message": "session exported: %s" % _display_export_path(state, target)})
    write({"type": "session", "session": session_payload(state)})


def _handle_fork_command(state: Any, argument: str, *, write: BridgeWriter) -> None:
    keep_count = parse_positive_int(argument) if argument.strip() else None
    if argument.strip() and keep_count is None:
        write({"type": "error", "message": "usage: /fork [non_system_message_count]"})
        return
    messages = _fork_messages(list(getattr(state.session, "messages", []) or []), keep_count)
    if not messages:
        write({"type": "error", "message": "session has no messages to fork"})
        return
    state.session_id = state.session_store.new_session_id()
    state.session.messages = messages
    save_session_snapshot(state)
    write({"type": "notice", "message": "forked session: %s" % short_session_id(state.session_id)})
    write({"type": "session_resumed", "session_id": state.session_id, "messages": messages_payload(messages)})
    write({"type": "status", "status": status_payload(state)})


def _handle_rewind_command(state: Any, argument: str, *, write: BridgeWriter) -> None:
    if argument.strip():
        drop_count = parse_positive_int(argument)
        if drop_count is None:
            write({"type": "error", "message": "usage: /rewind [drop_last_non_system_count]"})
            return
    else:
        drop_count = 1
    messages, dropped = _rewind_messages(list(getattr(state.session, "messages", []) or []), drop_count)
    state.session.messages = messages
    save_session_snapshot(state)
    write({"type": "notice", "message": "rewound %s message%s" % (dropped, "" if dropped == 1 else "s")})
    write({"type": "session_resumed", "session_id": state.session_id, "messages": messages_payload(messages)})
    write({"type": "context", "context": context_payload(state)})


def _handle_compact_command(state: Any, argument: str, *, write: BridgeWriter) -> None:
    compact = getattr(state.session, "compact", None)
    if compact is None:
        write({"type": "error", "message": "context compaction is not available"})
        return
    target_tokens = parse_positive_int(argument)
    stats = compact(target_tokens)
    save_session_snapshot(state)
    dropped = int(stats.get("dropped_messages", 0))
    write({"type": "notice", "message": "compacted %s message%s" % (dropped, "" if dropped == 1 else "s")})
    write({"type": "context", "context": {key: str(value) for key, value in stats.items()}})


def _handle_summary_command(state: Any, argument: str, *, write: BridgeWriter) -> None:
    context = _tool_context(state)
    if context is None:
        write({"type": "error", "message": "tool context is not available"})
        return
    max_messages = parse_positive_int(argument) or 50
    try:
        payload = session_summary(context, max_messages=max_messages)
    except Exception as exc:  # noqa: BLE001 - slash commands report tool-facing errors.
        write({"type": "error", "message": _error_message(exc)})
        return
    rows = [
        ["summary", str(payload.get("summary") or "")],
        ["messages", "%s / %s" % (payload.get("messages", 0), payload.get("total", 0))],
        ["roles", ", ".join("%s=%s" % (role, count) for role, count in dict(payload.get("roles") or {}).items()) or "-"],
    ]
    write({"type": "session", "session": rows})


def _handle_context_command(state: Any, argument: str, *, write: BridgeWriter) -> None:
    action, rest = _split_once(argument)
    if not action:
        write({"type": "context", "context": context_payload(state)})
        return
    if action == "messages":
        write({"type": "context_messages", "messages": _context_message_rows(state)})
        return
    if action == "drop":
        count = parse_positive_int(rest) or 0
        if count <= 0:
            write({"type": "error", "message": "usage: /context drop <count>"})
            return
        dropped = _drop_context_messages(state, count)
        save_session_snapshot(state)
        write({"type": "notice", "message": "dropped %s context message%s" % (dropped, "" if dropped == 1 else "s")})
        write({"type": "context", "context": context_payload(state)})
        return
    write({"type": "error", "message": "unknown context command: %s" % action})


async def _handle_prompt_command(state: Any, argument: str, *, write: BridgeWriter) -> None:
    action, rest = _split_once(argument)
    if not action:
        write({"type": "prompt", "prompt": prompt_payload(state)})
        return
    if action == "show":
        prompt = str(getattr(state.session, "system_prompt", "") or "")
        write({"type": "prompt", "prompt": [["system_prompt", prompt or "empty"]]})
        return
    if action == "set":
        _set_session_prompt(state.session, rest)
        await _persist_prompt_override(state, overridden=True)
        if hasattr(state.session, "context_trace"):
            state.session.context_trace = []
        save_session_snapshot(state)
        write({"type": "notice", "message": "session prompt updated"})
        write({"type": "prompt", "prompt": prompt_payload(state)})
        return
    if action in {"reset", "clear"}:
        _set_session_prompt(state.session, _default_system_prompt(state))
        await _persist_prompt_override(state, overridden=False)
        if hasattr(state.session, "context_trace"):
            state.session.context_trace = []
        save_session_snapshot(state)
        write({"type": "notice", "message": "session prompt reset"})
        write({"type": "prompt", "prompt": prompt_payload(state)})
        return
    if action in {"templates", "list"}:
        write({"type": "prompt", "prompt": _prompt_templates_payload(state)})
        return
    if action == "save":
        await _handle_prompt_save(state, rest, write=write)
        return
    if action == "use":
        await _handle_prompt_use(state, rest, write=write)
        return
    if action == "render":
        _handle_prompt_render(state, rest, write=write)
        return
    if action in {"delete", "remove"}:
        await _handle_prompt_delete(state, rest, write=write)
        return
    write({"type": "error", "message": "unknown prompt command: %s" % action})


async def _handle_permissions_command(state: Any, argument: str, *, write: BridgeWriter) -> None:
    action, rest = _split_once(argument)
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
    _set_runtime_permission_policy(state)
    await _persist_permission_override(state)
    write({"type": "notice", "message": "permission switched: %s -> %s" % (state.permission, state.permission_mode)})
    write({"type": "permissions", "permissions": permissions_payload(state)})


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
    context = _tool_context(state)
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
    context = _tool_context(state)
    if context is None:
        write({"type": "error", "message": "tool context is not available"})
        return
    try:
        await permission_add_rule(context, behavior=behavior, tool=tool.strip())
    except Exception as exc:  # noqa: BLE001 - permission rule errors are command output.
        write({"type": "error", "message": "permission rule failed: %s" % exc})
        return
    _sync_permission_state_from_context(state)
    write({"type": "notice", "message": "permission rule added: %s %s" % (behavior, tool.strip())})
    _handle_permissions_sources(state, write=write)


async def _handle_permission_remove_rule_command(state: Any, rest: str, *, write: BridgeWriter) -> None:
    behavior, tool = _parse_permission_remove(rest)
    if not tool:
        write({"type": "error", "message": "usage: /permissions remove [allow|deny|ask] <tool>"})
        return
    context = _tool_context(state)
    if context is None:
        write({"type": "error", "message": "tool context is not available"})
        return
    try:
        await permission_remove_rule(context, tool=tool, behavior=behavior)
    except Exception as exc:  # noqa: BLE001 - permission rule errors are command output.
        write({"type": "error", "message": "permission rule remove failed: %s" % exc})
        return
    _sync_permission_state_from_context(state)
    write({"type": "notice", "message": "permission rule removed: %s" % tool})
    _handle_permissions_sources(state, write=write)


async def _handle_prompt_save(state: Any, rest: str, *, write: BridgeWriter) -> None:
    name, content = _split_once_preserve(rest)
    safe_name = _safe_file_stem(name)
    if not safe_name:
        write({"type": "error", "message": "usage: /prompt save <name> [text]"})
        return
    text = content.strip() or str(getattr(state.session, "system_prompt", "") or "").strip()
    if not text:
        write({"type": "error", "message": "prompt is empty"})
        return
    context = _tool_context(state)
    payload = await _execute_slash_tool(
        state,
        tool_name="prompt.save",
        arguments={"name": safe_name, "content": text, "overwrite": True},
        write=write,
        error_label="prompt save",
        fallback=(lambda: prompt_save(context, name=safe_name, content=text, overwrite=True))
        if context is not None
        else (lambda: _prompt_save_local(state, safe_name, text)),
    )
    if payload is None:
        return
    write({"type": "notice", "message": "prompt saved: %s" % safe_name})
    write({"type": "prompt", "prompt": _prompt_templates_payload(state)})


async def _handle_prompt_use(state: Any, rest: str, *, write: BridgeWriter) -> None:
    safe_name = _safe_file_stem(rest.strip())
    if not safe_name:
        write({"type": "error", "message": "usage: /prompt use <name>"})
        return
    path = _prompt_template_root(state) / ("%s.md" % safe_name)
    if not path.exists():
        write({"type": "error", "message": "prompt template not found: %s" % safe_name})
        return
    _set_session_prompt(state.session, path.read_text(encoding="utf-8"))
    await _persist_prompt_override(state, overridden=True)
    if hasattr(state.session, "context_trace"):
        state.session.context_trace = []
    save_session_snapshot(state)
    write({"type": "notice", "message": "prompt loaded: %s" % safe_name})
    write({"type": "prompt", "prompt": prompt_payload(state)})


def _handle_prompt_render(state: Any, rest: str, *, write: BridgeWriter) -> None:
    name, arguments = _split_once_preserve(rest)
    if not name:
        write({"type": "error", "message": "usage: /prompt render <name> [arguments]"})
        return
    context = _tool_context(state)
    if context is None:
        write({"type": "error", "message": "tool context is not available"})
        return
    try:
        payload = prompt_render(context, name=name, raw_arguments=arguments)
    except Exception as exc:  # noqa: BLE001 - prompt render errors are command output.
        write({"type": "error", "message": "prompt render failed: %s" % exc})
        return
    write({"type": "prompt", "prompt": [["template", payload["name"]], ["prompt", payload["prompt"]]]})


async def _handle_prompt_delete(state: Any, rest: str, *, write: BridgeWriter) -> None:
    safe_name = _safe_file_stem(rest.strip())
    if not safe_name:
        write({"type": "error", "message": "usage: /prompt delete <name>"})
        return
    context = _tool_context(state)
    payload = await _execute_slash_tool(
        state,
        tool_name="prompt.delete",
        arguments={"name": safe_name},
        write=write,
        error_label="prompt delete",
        fallback=(lambda: prompt_delete(context, name=safe_name))
        if context is not None
        else (lambda: _prompt_delete_local(state, safe_name)),
    )
    if payload is None:
        return
    if not payload.get("deleted", True):
        write({"type": "error", "message": "prompt template not found: %s" % safe_name})
        return
    write({"type": "notice", "message": "prompt deleted: %s" % safe_name})
    write({"type": "prompt", "prompt": _prompt_templates_payload(state)})


def _prompt_templates_payload(state: Any) -> list[list[str]]:
    root = _prompt_template_root(state)
    rows: list[list[str]] = []
    for path in sorted(root.glob("*.md")) if root.exists() else []:
        text = path.read_text(encoding="utf-8").strip().replace("\n", " ")
        rows.append([path.stem, text[:120] if text else "empty"])
    return rows or [["templates", "none"]]


async def _handle_skills_command(state: Any, argument: str, *, write: BridgeWriter) -> None:
    action, rest = _split_once(argument)
    if not action:
        write({"type": "skills", "skills": skills_payload(state)})
        return
    if action in {"use", "enable"}:
        await _handle_skill_use(state, rest, write=write)
        return
    if action in {"disable", "remove"}:
        await _handle_skill_disable(state, rest, write=write)
        return
    if action == "install":
        await _handle_skill_install(state, rest, write=write)
        return
    if action in {"uninstall", "delete"}:
        await _handle_skill_uninstall(state, rest, write=write)
        return
    write({"type": "error", "message": "unknown skills command: %s" % action})


async def _handle_plugins_command(state: Any, argument: str, *, write: BridgeWriter) -> None:
    action, rest = _split_once(argument)
    if not action:
        write({"type": "plugins", "plugins": plugins_payload(state)})
        return
    if action in {"enable", "use"}:
        await _handle_plugin_enable(state, rest, write=write)
        return
    if action in {"disable", "remove"}:
        await _handle_plugin_disable(state, rest, write=write)
        return
    if action == "install":
        await _handle_plugin_install(state, rest, write=write)
        return
    if action in {"uninstall", "delete"}:
        await _handle_plugin_uninstall(state, rest, write=write)
        return
    write({"type": "error", "message": "unknown plugins command: %s" % action})


async def _handle_plugin_enable(state: Any, name: str, *, write: BridgeWriter) -> None:
    plugin_name = name.strip()
    if not plugin_name:
        write({"type": "error", "message": "usage: /plugins enable <name>"})
        return
    manifest = _load_plugin_manifest(state, plugin_name)
    if manifest is None:
        write({"type": "error", "message": "plugin not found: %s" % plugin_name})
        return
    resolved_name = str(manifest["raw"].get("name") or manifest["path"].parent.name)
    tools = [str(tool) for tool in manifest["raw"].get("tools", []) if str(tool)]
    missing_tools = _missing_skill_tools(state, tools)
    if missing_tools:
        write({"type": "error", "message": "plugin %s references unavailable tools: %s" % (resolved_name, ", ".join(missing_tools))})
        return
    enabled_plugins = set(getattr(state, "enabled_plugins", set()) or set())
    enabled_plugins.add(resolved_name)
    state.enabled_plugins = enabled_plugins
    plugin_tools = dict(getattr(state, "plugin_tools", {}) or {})
    plugin_tools[resolved_name] = [tool for tool in tools if tool not in set(getattr(state, "active_tools", []) or [])]
    state.plugin_tools = plugin_tools
    state.active_tools = _merge_unique(list(getattr(state, "active_tools", []) or []), tools)
    _replace_runtime_enabled_tools(state, tools)
    _append_plugin_prompt(state.session, resolved_name, manifest["raw"], manifest["plugin_dir"])
    await _persist_extension_state(state)
    write({"type": "notice", "message": "plugin enabled: %s" % resolved_name})
    write({"type": "plugins", "plugins": plugins_payload(state)})
    if tools:
        write({"type": "tools", "tools": tools_payload(state)})


async def _handle_plugin_disable(state: Any, name: str, *, write: BridgeWriter) -> None:
    plugin_name = name.strip()
    if not plugin_name:
        write({"type": "error", "message": "usage: /plugins disable <name>"})
        return
    enabled_plugins = set(getattr(state, "enabled_plugins", set()) or set())
    if plugin_name not in enabled_plugins:
        write({"type": "error", "message": "plugin is not enabled: %s" % plugin_name})
        return
    enabled_plugins.remove(plugin_name)
    state.enabled_plugins = enabled_plugins
    plugin_tools = dict(getattr(state, "plugin_tools", {}) or {})
    removed_tools = list(plugin_tools.pop(plugin_name, []) or [])
    state.plugin_tools = plugin_tools
    retained_plugin_tools = _managed_tools_except(state, removed_tools)
    state.active_tools = [
        tool
        for tool in list(getattr(state, "active_tools", []) or [])
        if tool not in removed_tools or tool in retained_plugin_tools
    ]
    _remove_runtime_enabled_tools(state, [tool for tool in removed_tools if tool not in retained_plugin_tools])
    await _persist_extension_state(state)
    write({"type": "notice", "message": "plugin disabled: %s" % plugin_name})
    write({"type": "plugins", "plugins": plugins_payload(state)})
    if removed_tools:
        write({"type": "tools", "tools": tools_payload(state)})


async def _handle_plugin_install(state: Any, rest: str, *, write: BridgeWriter) -> None:
    source = Path(rest.strip()).expanduser()
    if not rest.strip():
        write({"type": "error", "message": "usage: /plugins install <local_plugin_dir>"})
        return
    context = _tool_context(state)
    payload = await _execute_slash_tool(
        state,
        tool_name="plugin.install",
        arguments={"source": str(source)},
        write=write,
        error_label="plugin install",
        fallback=(lambda: plugin_install(context, source=str(source)))
        if context is not None
        else (lambda: _plugin_install_local(state, source)),
    )
    if payload is None:
        return
    plugin = dict(payload.get("plugin") or {})
    plugin_name = str(plugin.get("name") or source.name)
    write({"type": "notice", "message": "plugin installed: %s" % plugin_name})
    write({"type": "plugins", "plugins": plugins_payload(state)})


async def _handle_plugin_uninstall(state: Any, rest: str, *, write: BridgeWriter) -> None:
    plugin_name = _safe_file_stem(rest.strip())
    if not plugin_name:
        write({"type": "error", "message": "usage: /plugins uninstall <name>"})
        return
    context = _tool_context(state)
    payload = await _execute_slash_tool(
        state,
        tool_name="plugin.uninstall",
        arguments={"name": plugin_name},
        write=write,
        error_label="plugin uninstall",
        fallback=(lambda: plugin_uninstall(context, name=plugin_name))
        if context is not None
        else (lambda: _plugin_uninstall_local(state, plugin_name)),
    )
    if payload is None:
        return
    write({"type": "notice", "message": "plugin uninstalled: %s" % plugin_name})
    write({"type": "plugins", "plugins": plugins_payload(state)})


async def _handle_mcp_command(state: Any, argument: str, *, write: BridgeWriter) -> None:
    action, rest = _split_once(argument)
    if not action:
        write({"type": "mcp", "mcp": mcp_payload(state)})
        return
    if action == "set":
        await _handle_mcp_set(state, rest, write=write)
        return
    if action in {"enable", "use"}:
        await _handle_mcp_enable(state, rest, write=write)
        return
    if action == "disable" and rest.strip():
        await _handle_mcp_disable(state, rest, write=write)
        return
    if action in {"remove", "delete", "unset"}:
        await _handle_mcp_remove(state, rest, write=write)
        return
    if action in {"clear", "disable"}:
        await _handle_mcp_clear(state, write=write)
        return
    if action == "reload":
        await _handle_mcp_reload(state, write=write)
        return
    write({"type": "error", "message": "unknown mcp command: %s" % action})


async def _handle_mcp_set(state: Any, rest: str, *, write: BridgeWriter) -> None:
    name, command = _parse_mcp_set(rest)
    if not command:
        write({"type": "error", "message": "usage: /mcp set <name> -- <command>"})
        return
    context = _tool_context(state)
    if context is not None:
        payload = await mcp_configure(context, command=command, name=name or "default")
        configured_name = payload["configured"]["name"]
    else:
        settings = _mcp_settings(state)
        settings.SERVER_NAME = name or "default"
        settings.SERVER_COMMAND = command
        settings.SERVER_TRANSPORT = "stdio"
        settings.SERVER_URL = ""
        settings.SERVER_HEADERS = {}
        settings.SERVER_HEADERS_JSON = ""
        settings.AUTH_REQUIRED = False
        settings.AUTH_URL = ""
        settings.AUTH_STATUS = ""
        settings.AUTH_MESSAGE = ""
        if not getattr(settings, "EXECUTION_MODE", ""):
            settings.EXECUTION_MODE = "trusted_control_plane"
        configured_name = settings.SERVER_NAME
    write({"type": "notice", "message": "mcp configured: %s" % configured_name})
    write({"type": "mcp", "mcp": mcp_payload(state)})


async def _handle_mcp_clear(state: Any, *, write: BridgeWriter) -> None:
    settings = _mcp_settings(state)
    removed = _remove_mcp_tools(state)
    context = _tool_context(state)
    if context is not None:
        await mcp_clear(context)
    else:
        settings.SERVER_COMMAND = ""
        settings.SERVER_NAME = ""
        settings.SERVER_URL = ""
        settings.SERVER_HEADERS = {}
        settings.SERVER_HEADERS_JSON = ""
        settings.AUTH_REQUIRED = False
        settings.AUTH_URL = ""
        settings.AUTH_STATUS = ""
        settings.AUTH_MESSAGE = ""
    write({"type": "notice", "message": "mcp cleared%s" % (" · removed %s tool%s" % (removed, "" if removed == 1 else "s") if removed else "")})
    write({"type": "mcp", "mcp": mcp_payload(state)})


async def _handle_mcp_enable(state: Any, rest: str, *, write: BridgeWriter) -> None:
    context = _tool_context(state)
    if context is None:
        write({"type": "error", "message": "tool context is not available"})
        return
    name = rest.strip()
    try:
        result = await mcp_enable(context, name=name)
    except Exception as exc:  # noqa: BLE001 - command errors should be user-visible.
        write({"type": "error", "message": _error_message(exc)})
        return
    write({"type": "notice", "message": "mcp enabled: %s" % result.get("enabled", name or "default")})
    write({"type": "mcp", "mcp": mcp_payload(state)})


async def _handle_mcp_disable(state: Any, rest: str, *, write: BridgeWriter) -> None:
    context = _tool_context(state)
    if context is None:
        write({"type": "error", "message": "tool context is not available"})
        return
    name = rest.strip()
    try:
        result = await mcp_disable(context, name=name)
    except Exception as exc:  # noqa: BLE001 - command errors should be user-visible.
        write({"type": "error", "message": _error_message(exc)})
        return
    write({"type": "notice", "message": "mcp disabled: %s" % result.get("disabled", name or "default")})
    write({"type": "mcp", "mcp": mcp_payload(state)})


async def _handle_mcp_remove(state: Any, rest: str, *, write: BridgeWriter) -> None:
    context = _tool_context(state)
    if context is None:
        write({"type": "error", "message": "tool context is not available"})
        return
    name = rest.strip()
    try:
        result = await mcp_remove(context, name=name)
    except Exception as exc:  # noqa: BLE001 - command errors should be user-visible.
        write({"type": "error", "message": _error_message(exc)})
        return
    write({"type": "notice", "message": "mcp removed: %s" % result.get("removed", name or "default")})
    write({"type": "mcp", "mcp": mcp_payload(state)})


async def _handle_mcp_reload(state: Any, *, write: BridgeWriter) -> None:
    registry = getattr(getattr(getattr(state, "session", None), "runtime", None), "tools", None)
    if registry is None or not hasattr(registry, "names"):
        write({"type": "error", "message": "tool registry is not available"})
        return
    context = _tool_context(state)
    if context is None:
        write({"type": "error", "message": "tool context is not available"})
        return
    try:
        result = await mcp_reload(context, registry)
    except Exception as exc:
        write({"type": "error", "message": "mcp reload failed: %s" % exc})
        return
    removed = [str(name) for name in result.get("removed_tools", []) or []]
    added = [str(name) for name in result.get("loaded_tools", []) or [] if _is_canonical_mcp_tool_name(name)]
    state.active_tools = _merge_unique([tool for tool in list(getattr(state, "active_tools", []) or []) if tool not in set(removed)], added)
    _remove_runtime_enabled_tools(state, removed)
    _replace_runtime_enabled_tools(state, added)
    write({"type": "notice", "message": "mcp reloaded: %s tool%s" % (len(added), "" if len(added) == 1 else "s")})
    write({"type": "mcp", "mcp": mcp_payload(state)})
    write({"type": "tools", "tools": tools_payload(state)})


async def _handle_skill_use(state: Any, name: str, *, write: BridgeWriter) -> None:
    skill_name = name.strip()
    if not skill_name:
        write({"type": "error", "message": "usage: /skills use <name>"})
        return
    try:
        skill = SkillLoader(getattr(getattr(state.settings, "server", None), "ROOT_PATH", ".")).load(skill_name)
    except Exception as exc:
        write({"type": "error", "message": "failed to load skill %s: %s" % (skill_name, exc)})
        return
    missing_tools = _missing_skill_tools(state, skill.tools)
    if missing_tools:
        write({"type": "error", "message": "skill %s references unavailable tools: %s" % (skill.name, ", ".join(missing_tools))})
        return
    enabled_skills = set(getattr(state, "enabled_skills", set()) or set())
    enabled_skills.add(skill.name)
    state.enabled_skills = enabled_skills
    _append_skill_prompt(state.session, skill.name, skill.prompt_fragments)
    skill_tools = dict(getattr(state, "skill_tools", {}) or {})
    skill_tools[skill.name] = [tool for tool in skill.tools if tool not in set(getattr(state, "active_tools", []) or [])]
    state.skill_tools = skill_tools
    state.active_tools = _merge_unique(list(getattr(state, "active_tools", []) or []), skill.tools)
    _replace_runtime_enabled_tools(state, skill.tools)
    await _persist_extension_state(state)
    write({"type": "notice", "message": "skill enabled: %s" % skill.name})
    write({"type": "skills", "skills": skills_payload(state)})


async def _handle_skill_disable(state: Any, name: str, *, write: BridgeWriter) -> None:
    skill_name = name.strip()
    if not skill_name:
        write({"type": "error", "message": "usage: /skills disable <name>"})
        return
    enabled_skills = set(getattr(state, "enabled_skills", set()) or set())
    if skill_name not in enabled_skills:
        write({"type": "error", "message": "skill is not enabled: %s" % skill_name})
        return
    enabled_skills.remove(skill_name)
    state.enabled_skills = enabled_skills
    skill_tools = dict(getattr(state, "skill_tools", {}) or {})
    removed_tools = list(skill_tools.pop(skill_name, []) or [])
    state.skill_tools = skill_tools
    retained_tools = _managed_tools_except(state, removed_tools)
    state.active_tools = [
        tool
        for tool in list(getattr(state, "active_tools", []) or [])
        if tool not in removed_tools or tool in retained_tools
    ]
    _remove_runtime_enabled_tools(state, [tool for tool in removed_tools if tool not in retained_tools])
    await _persist_extension_state(state)
    write({"type": "notice", "message": "skill disabled: %s" % skill_name})
    write({"type": "skills", "skills": skills_payload(state)})
    if removed_tools:
        write({"type": "tools", "tools": tools_payload(state)})


async def _handle_skill_install(state: Any, rest: str, *, write: BridgeWriter) -> None:
    context = _tool_context(state)
    if context is None:
        write({"type": "error", "message": "tool context is not available"})
        return
    if not rest.strip():
        write({"type": "error", "message": "usage: /skills install <local_skill_json_or_dir>"})
        return
    payload = await _execute_slash_tool(
        state,
        tool_name="skill.install",
        arguments={"source": rest.strip()},
        write=write,
        error_label="skill install",
        fallback=lambda: skill_install(context, source=rest.strip()),
    )
    if payload is None:
        return
    write({"type": "notice", "message": "skill installed: %s" % payload["skill"]["name"]})
    write({"type": "skills", "skills": skills_payload(state)})


async def _handle_skill_uninstall(state: Any, rest: str, *, write: BridgeWriter) -> None:
    context = _tool_context(state)
    if context is None:
        write({"type": "error", "message": "tool context is not available"})
        return
    if not rest.strip():
        write({"type": "error", "message": "usage: /skills uninstall <name>"})
        return
    payload = await _execute_slash_tool(
        state,
        tool_name="skill.uninstall",
        arguments={"name": rest.strip()},
        write=write,
        error_label="skill uninstall",
        fallback=lambda: skill_uninstall(context, name=rest.strip()),
    )
    if payload is None:
        return
    write({"type": "notice", "message": "skill uninstalled: %s" % payload["skill"]})
    write({"type": "skills", "skills": skills_payload(state)})


async def _restore_pending_approval(state: Any, record: Any, *, write: BridgeWriter) -> None:
    checkpoint = getattr(record, "checkpoint", None)
    save = getattr(getattr(getattr(state, "persistence", None), "checkpoints", None), "save", None)
    if checkpoint is not None and save is not None:
        try:
            await save(checkpoint)
        except Exception:
            pass
    event = dict(record.pending_approval)
    payload = dict(event.get("payload") or {})
    payload["run_id"] = record.pending_run_id
    event["payload"] = payload
    write({"type": "runtime_event", "event": event})


async def _handle_memory_command(state: Any, argument: str, *, write: BridgeWriter) -> None:
    action, rest = _split_once(argument)
    if not action:
        write({"type": "memory", "memory": await memory_payload(state)})
        return
    if action in {"add", "remember"}:
        await _handle_memory_add(state, rest, write=write)
        return
    if action in {"forget", "delete", "remove"}:
        await _handle_memory_forget(state, rest, write=write)
        return
    if action in {"edit", "update"}:
        await _handle_memory_edit(state, rest, write=write)
        return
    write({"type": "error", "message": "unknown memory command: %s" % action})


async def _handle_hooks_command(state: Any, argument: str, *, write: BridgeWriter) -> None:
    action, rest = _split_once(argument)
    if not action or action in {"list", "ls"}:
        await _write_hooks(state, write=write)
        return
    if action == "add":
        await _handle_hook_add(state, rest, write=write)
        return
    if action in {"delete", "remove", "rm"}:
        await _handle_hook_delete(state, rest, write=write)
        return
    write({"type": "error", "message": "unknown hooks command: %s" % action})


async def _handle_hook_add(state: Any, rest: str, *, write: BridgeWriter) -> None:
    context = _tool_context(state)
    if context is None:
        write({"type": "error", "message": "tool context is not available"})
        return
    event, action, name, tool, content = _parse_hook_add(rest)
    if not event or not action or not name:
        write({"type": "error", "message": "usage: /hooks add <event> <action> <name> [tool=<pattern>] -- <content>"})
        return
    try:
        payload = await hook_add(
            context,
            event=event,
            name=name,
            action=action,
            content=content,
            tool=tool,
            metadata={"source": "terminal"},
        )
    except Exception as exc:  # noqa: BLE001 - hook validation errors should be slash output.
        write({"type": "error", "message": "hook add failed: %s" % exc})
        return
    write({"type": "notice", "message": "hook added: %s" % payload["hook"]["short_id"]})
    write({"type": "hooks", "hooks": hooks_payload(state)})


async def _handle_hook_delete(state: Any, rest: str, *, write: BridgeWriter) -> None:
    context = _tool_context(state)
    target = rest.strip()
    if context is None:
        write({"type": "error", "message": "tool context is not available"})
        return
    if not target:
        write({"type": "error", "message": "usage: /hooks delete <id>"})
        return
    try:
        payload = await hook_delete(context, hook_id=target)
    except Exception as exc:  # noqa: BLE001 - lookup errors should be slash output.
        write({"type": "error", "message": "hook delete failed: %s" % exc})
        return
    write({"type": "notice", "message": "hook deleted: %s" % payload["hook"]["short_id"]})
    write({"type": "hooks", "hooks": hooks_payload(state)})


async def _write_hooks(state: Any, *, write: BridgeWriter) -> None:
    context = _tool_context(state)
    if context is not None:
        await hook_list(context, limit=30)
    write({"type": "hooks", "hooks": hooks_payload(state)})


async def _handle_todo_command(state: Any, argument: str, *, write: BridgeWriter) -> None:
    action, _ = _split_once(argument)
    context = _tool_context(state)
    if context is None:
        write({"type": "todo", "todo": todo_payload(state)})
        return
    if not action:
        write({"type": "todo", "todo": todo_payload(state)})
        return
    if action == "clear":
        await todo_write(context, todos=[])
        write({"type": "notice", "message": "todos cleared"})
        write({"type": "todo", "todo": todo_payload(state)})
        return
    write({"type": "error", "message": "unknown todo command: %s" % action})


async def _handle_plan_command(state: Any, argument: str, *, write: BridgeWriter) -> None:
    action, rest = _split_once(argument)
    context = _tool_context(state)
    if context is None:
        write({"type": "plan", "plan": plan_payload(state)})
        return
    if not action or action == "status":
        write({"type": "plan", "plan": plan_payload(state)})
        return
    if action == "enter":
        await plan_enter(context)
        write({"type": "notice", "message": "entered plan mode"})
        write({"type": "plan", "plan": plan_payload(state)})
        return
    if action == "exit":
        text = rest.strip()
        if not text:
            write({"type": "error", "message": "usage: /plan exit <plan>"})
            return
        if not context.plan_mode:
            context.plan_mode = True
        await plan_exit(context, plan=text)
        write({"type": "notice", "message": "exited plan mode"})
        write({"type": "plan", "plan": plan_payload(state)})
        return
    if action == "clear":
        await plan_clear(context)
        write({"type": "notice", "message": "plan cleared"})
        write({"type": "plan", "plan": plan_payload(state)})
        return
    write({"type": "error", "message": "unknown plan command: %s" % action})


async def _handle_agents_command(
    state: Any,
    argument: str,
    *,
    close_session_model_client: CloseSessionModelClient,
    write: BridgeWriter,
) -> None:
    action, rest = _split_once(argument)
    if not action:
        write({"type": "agents", "agents": await agents_payload(state)})
        return
    if action == "save":
        await _handle_agent_save(state, rest, write=write)
        return
    if action in {"use", "switch"}:
        await _handle_agent_use(state, rest, close_session_model_client=close_session_model_client, write=write)
        return
    write({"type": "error", "message": "unknown agents command: %s" % action})


async def _handle_agent_save(state: Any, rest: str, *, write: BridgeWriter) -> None:
    store = getattr(getattr(state, "persistence", None), "agent_profiles", None)
    if store is None or not hasattr(store, "save"):
        write({"type": "error", "message": "agent profile store is not available"})
        return
    agent_id, name = _split_once(rest)
    if not agent_id:
        write({"type": "error", "message": "usage: /agents save <agent_id> [name]"})
        return
    profile = AgentProfile.from_spec(_agent_spec_for_state(state, agent_id=agent_id), name=name)
    await store.save(profile)
    write({"type": "notice", "message": "agent saved: %s" % agent_id})
    write({"type": "agents", "agents": await agents_payload(state)})


async def _handle_agent_use(
    state: Any,
    rest: str,
    *,
    close_session_model_client: CloseSessionModelClient,
    write: BridgeWriter,
) -> None:
    agent_id = rest.strip()
    if not agent_id:
        write({"type": "error", "message": "usage: /agents use <agent_id>"})
        return
    store = getattr(getattr(state, "persistence", None), "agent_profiles", None)
    if store is None or not hasattr(store, "load"):
        write({"type": "error", "message": "agent profile store is not available"})
        return
    workspace = getattr(state.session, "workspace", None)
    if workspace is None or not getattr(workspace, "tenant_id", "") or not getattr(workspace, "user_id", ""):
        write({"type": "error", "message": "agent identity scope is not available"})
        return
    profile = await store.load(workspace.tenant_id, workspace.user_id, agent_id)
    if profile is None:
        write({"type": "error", "message": "agent not found: %s" % agent_id})
        return
    spec = profile.to_agent_spec().with_workspace_defaults()
    previous_messages = [message for message in list(getattr(state.session, "messages", [])) if getattr(message, "role", "") != "system"]
    await close_session_model_client(state.session)
    state.active_tools = list(spec.enabled_tools or state.active_tools)
    state.permission_mode = spec.tool_permissions.normalized_mode()
    state.approval_tools = list(spec.tool_permissions.approval_required_tools)
    state.permission = spec.permission_profile or state.permission_mode
    if spec.workspace.path:
        state.active_workspace = Path(spec.workspace.path)
    state.session = await _create_session_from_agent_profile(state, spec)
    state.session.messages = list(getattr(state.session, "messages", []) or []) + previous_messages
    _sync_extension_state_from_context(state)
    save_session_snapshot(state)
    write({"type": "notice", "message": "agent switched: %s" % profile.agent_id})
    write({"type": "runtime", "runtime": runtime_payload(state)})
    write({"type": "tools", "tools": tools_payload(state)})
    write({"type": "permissions", "permissions": permissions_payload(state)})


async def _handle_memory_add(state: Any, rest: str, *, write: BridgeWriter) -> None:
    workspace = getattr(state.session, "workspace", None)
    if workspace is None or not getattr(workspace, "tenant_id", "") or not getattr(workspace, "user_id", ""):
        write({"type": "error", "message": "memory identity scope is not available"})
        return
    scope, content = _parse_memory_add(rest, workspace)
    if not content:
        write({"type": "error", "message": "usage: /memory add [user|agent|workspace] <text>"})
        return
    try:
        result = await memory_add(_memory_tool_context(state), content=content, scope=scope.value, metadata={"source": "terminal"})
    except Exception as exc:  # noqa: BLE001 - slash commands report tool-facing errors.
        write({"type": "error", "message": str(exc)})
        return
    memory = dict(result.get("memory") or {})
    write({"type": "notice", "message": "memory saved: %s" % memory.get("short_id", "")})
    write({"type": "memory", "memory": await memory_payload(state)})


async def _handle_memory_forget(state: Any, rest: str, *, write: BridgeWriter) -> None:
    target = rest.strip()
    if not target:
        write({"type": "error", "message": "usage: /memory forget <id>"})
        return
    try:
        result = await memory_forget(_memory_tool_context(state), memory_id=target)
    except Exception as exc:  # noqa: BLE001 - slash commands report tool-facing errors.
        write({"type": "error", "message": _error_message(exc)})
        return
    memory = dict(result.get("memory") or {})
    write({"type": "notice", "message": "memory forgotten: %s" % memory.get("short_id", "")})
    write({"type": "memory", "memory": await memory_payload(state)})


async def _handle_memory_edit(state: Any, rest: str, *, write: BridgeWriter) -> None:
    target, content = _split_once_preserve(rest)
    if not target or not content.strip():
        write({"type": "error", "message": "usage: /memory edit <id> <text>"})
        return
    try:
        result = await memory_edit(_memory_tool_context(state), memory_id=target, content=content.strip())
    except Exception as exc:  # noqa: BLE001 - slash commands report tool-facing errors.
        write({"type": "error", "message": _error_message(exc)})
        return
    memory = dict(result.get("memory") or {})
    write({"type": "notice", "message": "memory updated: %s" % memory.get("short_id", "")})
    write({"type": "memory", "memory": await memory_payload(state)})


def _memory_tool_context(state: Any) -> Any:
    context = _tool_context(state)
    store = getattr(getattr(state, "persistence", None), "memories", None)
    if context is not None:
        if getattr(context, "memory_store", None) is None and store is not None:
            context.memory_store = store
        return context
    return SimpleNamespace(workspace=getattr(getattr(state, "session", None), "workspace", None), memory_store=store)


def _parse_memory_add(rest: str, workspace: Any) -> tuple[MemoryScope, str]:
    first, remainder = _split_once(rest)
    if first in {scope.value for scope in MemoryScope}:
        return MemoryScope(first), remainder.strip()
    if getattr(workspace, "workspace_id", ""):
        return MemoryScope.WORKSPACE, rest.strip()
    if getattr(workspace, "agent_id", ""):
        return MemoryScope.AGENT, rest.strip()
    return MemoryScope.USER, rest.strip()


def _short_memory_id(memory_id: str) -> str:
    return str(memory_id).replace("mem_", "", 1)[:12]


def _set_session_prompt(session: Any, text: str) -> None:
    setter = getattr(session, "set_system_prompt", None)
    if setter is not None:
        setter(text)
        return
    context_window = getattr(session, "context_window", None)
    if context_window is not None:
        context_window.system_prompt = str(text or "").strip()


def _sync_session_prompt_from_messages(session: Any) -> None:
    messages = list(getattr(session, "messages", []) or [])
    prompt = ""
    if messages and getattr(messages[0], "role", "") == "system":
        prompt = messages[0].content_text()
    context_window = getattr(session, "context_window", None)
    if context_window is not None:
        context_window.system_prompt = str(prompt or "").strip()


def _context_message_rows(state: Any) -> list[list[str]]:
    rows: list[list[str]] = []
    for index, message in enumerate(list(getattr(state.session, "messages", []) or [])[-30:]):
        role = str(getattr(message, "role", ""))
        content = message.content_text() if hasattr(message, "content_text") else str(message)
        rows.append([str(index), "%s · %s" % (role, content.replace("\n", " ")[:160])])
    return rows or [["messages", "none"]]


def _drop_context_messages(state: Any, count: int) -> int:
    messages = list(getattr(state.session, "messages", []) or [])
    kept: list[Any] = []
    dropped = 0
    for message in messages:
        if dropped < count and getattr(message, "role", "") != "system":
            dropped += 1
            continue
        kept.append(message)
    state.session.messages = kept
    return dropped


def _set_runtime_permission_policy(state: Any) -> None:
    runtime = getattr(state.session, "runtime", None)
    orchestrator = getattr(runtime, "tool_orchestrator", None)
    if orchestrator is None:
        return
    orchestrator.permission_policy = build_tool_permission_policy(_agent_spec_for_state(state))


def _append_skill_prompt(session: Any, skill_name: str, fragments: list[str]) -> None:
    prompt = str(getattr(session, "system_prompt", "") or "")
    marker = "## skills: skill.%s." % skill_name
    if marker in prompt:
        return
    rendered = "\n\n".join(
        "## skills: skill.%s.%s\n%s" % (skill_name, index, fragment.strip())
        for index, fragment in enumerate(fragments)
        if fragment.strip()
    )
    if rendered:
        _set_session_prompt(session, "\n\n".join(part for part in [prompt, rendered] if part.strip()))
    trace = list(getattr(session, "context_trace", []) or [])
    for index, fragment in enumerate(fragments):
        text = fragment.strip()
        if text:
            trace.append(
                ContextTraceItem(
                    id="skill.%s.%s" % (skill_name, index),
                    layer=ContextLayer.SKILLS,
                    source="skill:%s" % skill_name,
                    tokens=max(1, len(text.encode("utf-8")) // 4),
                    included=True,
                )
            )
    if hasattr(session, "context_trace"):
        session.context_trace = trace


def _append_plugin_prompt(session: Any, plugin_name: str, raw: dict[str, Any], plugin_dir: Path) -> None:
    fragments: list[str] = []
    prompt = str(raw.get("prompt") or "").strip()
    if prompt:
        fragments.append(prompt)
    for relative_path in raw.get("prompt_fragments", []) or []:
        try:
            text = (plugin_dir / str(relative_path)).read_text(encoding="utf-8").strip()
        except Exception:
            continue
        if text:
            fragments.append(text)
    if not fragments:
        return
    current = str(getattr(session, "system_prompt", "") or "")
    marker = "## plugins: plugin.%s." % plugin_name
    if marker in current:
        return
    rendered = "\n\n".join(
        "## plugins: plugin.%s.%s\n%s" % (plugin_name, index, fragment)
        for index, fragment in enumerate(fragments)
    )
    _set_session_prompt(session, "\n\n".join(part for part in [current, rendered] if part.strip()))


def _missing_skill_tools(state: Any, tools: list[str]) -> list[str]:
    registry = getattr(getattr(getattr(state, "session", None), "runtime", None), "tools", None)
    if registry is None or not hasattr(registry, "names"):
        return list(tools)
    available = set(registry.names())
    return [tool for tool in tools if tool not in available]


def _load_plugin_manifest(state: Any, name: str) -> dict[str, Any] | None:
    root = Path(getattr(getattr(state.settings, "server", None), "ROOT_PATH", ".")).expanduser()
    for manifest_path in _plugin_manifest_paths(root):
        try:
            raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        plugin_dir = manifest_path.parent.parent if manifest_path.parent.name == ".codex-plugin" else manifest_path.parent
        plugin_name = str(raw.get("name") or plugin_dir.name)
        if name in {plugin_name, plugin_dir.name}:
            return {"raw": raw, "path": manifest_path, "plugin_dir": plugin_dir}
    return None


def _plugin_manifest_paths(root: Path) -> list[Path]:
    paths: list[Path] = []
    for plugins_dir in [root / ".agents" / "plugins", root / "plugins"]:
        if not plugins_dir.exists():
            continue
        paths.extend(sorted(plugins_dir.glob("*/.codex-plugin/plugin.json")))
        paths.extend(sorted(plugins_dir.glob("*/plugin.json")))
    return paths


def _plugin_install_local(state: Any, source: Path) -> dict[str, Any]:
    source_dir = Path(source).expanduser()
    if not source_dir.exists() or not source_dir.is_dir():
        raise FileNotFoundError("plugin source not found: %s" % source)
    manifest_path = _plugin_manifest_for_dir(source_dir)
    if manifest_path is None:
        raise FileNotFoundError("plugin manifest not found in: %s" % source_dir)
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    plugin_name = _safe_file_stem(str(raw.get("name") or source_dir.name))
    if not plugin_name:
        raise ValueError("plugin name is invalid")
    target = _plugin_install_root(state) / plugin_name
    if target.exists():
        raise FileExistsError("plugin already installed: %s" % plugin_name)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_dir, target)
    return {
        "plugin": {
            "name": plugin_name,
            "description": str(raw.get("description") or ""),
            "version": str(raw.get("version") or ""),
            "path": str(target),
        },
        "installed": True,
    }


def _plugin_uninstall_local(state: Any, plugin_name: str) -> dict[str, Any]:
    if plugin_name in set(getattr(state, "enabled_plugins", set()) or set()):
        raise RuntimeError("disable plugin before uninstalling: %s" % plugin_name)
    target = _plugin_install_root(state) / plugin_name
    if not target.exists():
        raise FileNotFoundError("plugin not installed: %s" % plugin_name)
    shutil.rmtree(target)
    return {"plugin": plugin_name, "uninstalled": True}


def _plugin_install_root(state: Any) -> Path:
    root = Path(getattr(getattr(state.settings, "server", None), "ROOT_PATH", ".")).expanduser()
    return root / ".agents" / "plugins"


def _plugin_manifest_for_dir(path: Path) -> Path | None:
    candidates = [path / ".codex-plugin" / "plugin.json", path / "plugin.json"]
    return next((candidate for candidate in candidates if candidate.exists() and candidate.is_file()), None)


def _mcp_settings(state: Any) -> Any:
    settings = getattr(state, "settings", None)
    if not hasattr(settings, "mcp"):
        settings.mcp = SimpleNamespace()
    mcp = settings.mcp
    for name, value in {
        "SERVER_NAME": "",
        "SERVER_COMMAND": "",
        "SERVER_TRANSPORT": "stdio",
        "SERVER_URL": "",
        "SERVER_HEADERS": {},
        "SERVER_HEADERS_JSON": "",
        "CLIENT_TIMEOUT": 30.0,
        "SSE_READ_TIMEOUT": 300.0,
        "EXECUTION_MODE": "trusted_control_plane",
        "SANDBOX_PROFILE": "",
        "AUTH_REQUIRED": False,
        "AUTH_URL": "",
        "AUTH_STATUS": "",
        "AUTH_MESSAGE": "",
    }.items():
        if not hasattr(mcp, name):
            setattr(mcp, name, value)
    return mcp


def _parse_mcp_set(rest: str) -> tuple[str, str]:
    text = str(rest or "").strip()
    if " -- " not in text:
        return "", ""
    name, command = text.split(" -- ", 1)
    return name.strip() or "default", command.strip()


def _remove_mcp_tools(state: Any) -> int:
    active = [name for name in list(getattr(state, "active_tools", []) or []) if not _is_mcp_tool_name(name)]
    removed = len(list(getattr(state, "active_tools", []) or [])) - len(active)
    state.active_tools = active
    runtime = getattr(state.session, "runtime", None)
    config = getattr(runtime, "config", None)
    if config is not None:
        enabled = [name for name in list(getattr(config, "enabled_tools", []) or []) if not _is_mcp_tool_name(name)]
        runtime.config = replace(config, enabled_tools=enabled)
    return removed


def _is_mcp_tool_name(name: Any) -> bool:
    value = str(name)
    return value.startswith("mcp_")


def _is_canonical_mcp_tool_name(name: Any) -> bool:
    return str(name).startswith("mcp__")


def _replace_runtime_enabled_tools(state: Any, tools: list[str]) -> None:
    runtime = getattr(state.session, "runtime", None)
    config = getattr(runtime, "config", None)
    if config is not None:
        runtime.config = replace(config, enabled_tools=_merge_unique(list(getattr(config, "enabled_tools", []) or []), tools))


def _remove_runtime_enabled_tools(state: Any, tools: list[str]) -> None:
    runtime = getattr(state.session, "runtime", None)
    config = getattr(runtime, "config", None)
    if config is not None:
        removed = set(tools)
        runtime.config = replace(config, enabled_tools=[tool for tool in list(getattr(config, "enabled_tools", []) or []) if tool not in removed])


def _managed_tools_except(state: Any, excluded: list[str]) -> set[str]:
    managed: set[str] = set()
    for mapping_name in ["plugin_tools", "skill_tools"]:
        mapping = dict(getattr(state, mapping_name, {}) or {})
        for group in mapping.values():
            for tool in group:
                managed.add(tool)
    return managed


async def _persist_extension_state(state: Any) -> None:
    context = _tool_context(state)
    if context is None:
        return
    context.enabled_skills = set(getattr(state, "enabled_skills", set()) or set())
    context.enabled_plugins = set(getattr(state, "enabled_plugins", set()) or set())
    context.skill_tools = {
        str(name): [str(tool) for tool in tools]
        for name, tools in dict(getattr(state, "skill_tools", {}) or {}).items()
    }
    context.plugin_tools = {
        str(name): [str(tool) for tool in tools]
        for name, tools in dict(getattr(state, "plugin_tools", {}) or {}).items()
    }
    await save_session_state(context)


async def _persist_prompt_override(state: Any, *, overridden: bool) -> None:
    context = _tool_context(state)
    if context is None:
        return
    context.system_prompt_overridden = bool(overridden)
    context.system_prompt_override = str(getattr(state.session, "system_prompt", "") or "") if overridden else ""
    await save_session_state(context)


async def _persist_permission_override(state: Any) -> None:
    context = _tool_context(state)
    if context is None:
        return
    context.permission_overridden = True
    context.permission_profile_override = str(getattr(state, "permission", "") or "")
    context.permission_mode_override = str(getattr(state, "permission_mode", "") or "")
    spec = _agent_spec_for_state(state)
    permissions = spec.tool_permissions
    context.permission_restrict_allowed_tools = permissions.allowed_tools is not None
    context.permission_allowed_tools_override = [str(tool) for tool in list(permissions.allowed_tools or [])]
    context.permission_denied_tools_override = [str(tool) for tool in list(permissions.denied_tools or [])]
    context.approval_required_tools_override = [str(tool) for tool in list(getattr(state, "approval_tools", []) or [])]
    context.agent_spec = spec
    await save_session_state(context)


def _default_system_prompt(state: Any) -> str:
    agent = getattr(getattr(state, "settings", None), "agent", None)
    return str(getattr(agent, "SYSTEM_PROMPT", "") or "")


def _sync_extension_state_from_context(state: Any) -> None:
    context = _tool_context(state)
    if context is None:
        return
    state.enabled_skills = set(getattr(context, "enabled_skills", set()) or set())
    state.enabled_plugins = set(getattr(context, "enabled_plugins", set()) or set())
    state.skill_tools = dict(getattr(context, "skill_tools", {}) or {})
    state.plugin_tools = dict(getattr(context, "plugin_tools", {}) or {})
    if bool(getattr(context, "permission_overridden", False)):
        _sync_permission_state_from_context(state)


def _sync_permission_state_from_context(state: Any) -> None:
    context = _tool_context(state)
    if context is None:
        return
    state.permission = str(getattr(context, "permission_profile_override", "") or getattr(state, "permission", ""))
    state.permission_mode = str(getattr(context, "permission_mode_override", "") or getattr(state, "permission_mode", ""))
    state.approval_tools = [str(tool) for tool in list(getattr(context, "approval_required_tools_override", []) or [])]


def _parse_permission_remove(rest: str) -> tuple[str, str]:
    behavior, tool = _split_once(rest)
    if behavior in {"allow", "deny", "ask"}:
        return behavior, tool.strip()
    return "", str(rest or "").strip()


def _parse_hook_add(rest: str) -> tuple[str, str, str, str, str]:
    text = str(rest or "").strip()
    before, content = text, ""
    if " -- " in text:
        before, content = text.split(" -- ", 1)
    event, remainder = _split_once(before)
    action, name_part = _split_once(remainder)
    name_tokens: list[str] = []
    tool = ""
    for token in name_part.split():
        if token.startswith("tool="):
            tool = token.split("=", 1)[1].strip()
        elif token.startswith("--tool="):
            tool = token.split("=", 1)[1].strip()
        else:
            name_tokens.append(token)
    name = " ".join(name_tokens).strip()
    return event.strip(), action.strip(), name, tool, content.strip()


async def _execute_slash_tool(
    state: Any,
    *,
    tool_name: str,
    arguments: dict[str, Any],
    write: BridgeWriter,
    error_label: str,
    fallback: Callable[[], Any] | None = None,
) -> dict[str, Any] | None:
    runtime = getattr(getattr(state, "session", None), "runtime", None)
    orchestrator = getattr(runtime, "tool_orchestrator", None)
    if orchestrator is None:
        return await _execute_slash_fallback(fallback, write=write, error_label=error_label)

    call = ToolCall(
        id="slash_%s" % uuid4().hex[:12],
        name=tool_name,
        arguments=dict(arguments or {}),
        raw={"source": "slash"},
    )
    try:
        authorizations = await orchestrator.authorize([call])
    except Exception as exc:  # noqa: BLE001 - policy failures should surface to command output.
        write({"type": "error", "message": "%s failed: %s" % (error_label, _error_message(exc))})
        return None
    if not authorizations:
        write({"type": "error", "message": "%s failed: missing permission decision" % error_label})
        return None

    decision = authorizations[0].decision
    if not decision.allowed and decision.requires_approval:
        decision = ToolPermissionDecision(
            allowed=True,
            reason=decision.reason,
            metadata={"source": "slash", "approval": "explicit_command"},
        )
    if not decision.allowed:
        reason = decision.reason or "tool call denied by permission policy"
        write({"type": "error", "message": "%s failed: %s" % (error_label, reason)})
        return None

    try:
        batch = await orchestrator.execute_with_decisions(
            [call],
            [decision],
            run_id="slash_%s" % uuid4().hex[:8],
        )
    except Exception as exc:  # noqa: BLE001 - registry failures should surface to command output.
        write({"type": "error", "message": "%s failed: %s" % (error_label, _error_message(exc))})
        return None
    if not batch.results:
        write({"type": "error", "message": "%s failed: no tool result returned" % error_label})
        return None
    result = batch.results[0]
    if result.is_error:
        if fallback is not None and str(result.content or "").strip().startswith("unknown tool:"):
            return await _execute_slash_fallback(fallback, write=write, error_label=error_label)
        message = str(result.content or "").strip() or "tool execution failed"
        write({"type": "error", "message": "%s failed: %s" % (error_label, message)})
        return None
    return _tool_result_payload(result.raw, result.content)


async def _execute_slash_fallback(
    fallback: Callable[[], Any] | None,
    *,
    write: BridgeWriter,
    error_label: str,
) -> dict[str, Any] | None:
    if fallback is None:
        write({"type": "error", "message": "%s failed: runtime tool orchestration is not available" % error_label})
        return None
    try:
        result = fallback()
        if asyncio.iscoroutine(result):
            result = await result
    except Exception as exc:  # noqa: BLE001 - fallback failures should surface to command output.
        write({"type": "error", "message": "%s failed: %s" % (error_label, _error_message(exc))})
        return None
    return _tool_result_payload(result, "")


def _tool_result_payload(raw: Any, content: str) -> dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    text = str(content or "").strip()
    if text:
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return dict(parsed)
            return {"result": parsed}
        except Exception:
            return {"result": text}
    if isinstance(raw, str):
        return {"result": raw}
    if raw is None:
        return {}
    return {"result": raw}


def _parse_export_argument(state: Any, argument: str) -> tuple[str, Path]:
    first, rest = _split_once(argument)
    if first in {"json", "markdown", "md"}:
        export_format = "markdown" if first in {"markdown", "md"} else "json"
        requested = rest.strip()
    else:
        export_format = "json"
        requested = str(argument or "").strip()
    suffix = "md" if export_format == "markdown" else "json"
    workspace = Path(getattr(state, "active_workspace", "") or ".").expanduser().resolve()
    if requested:
        raw_target = Path(requested)
        if raw_target.is_absolute():
            raise ValueError("export path must be workspace-relative")
        target = (workspace / raw_target).resolve()
    else:
        safe_session = _safe_file_stem(str(getattr(state, "session_id", "") or "session")) or "session"
        target = (workspace / ".agents" / "exports" / ("%s.%s" % (safe_session, suffix))).resolve()
    try:
        target.relative_to(workspace)
    except ValueError as exc:
        raise ValueError("export path must stay inside the workspace") from exc
    if target.suffix == "":
        target = target.with_suffix("." + suffix)
    return export_format, target


def _session_export_content(state: Any, export_format: str) -> str:
    messages = list(getattr(state.session, "messages", []) or [])
    runtime = getattr(state.session, "runtime", None)
    payload = {
        "session_id": str(getattr(state, "session_id", "") or ""),
        "profile": str(getattr(state, "profile", "") or ""),
        "model": {
            "protocol": str(getattr(runtime, "protocol", "") or ""),
            "model": str(getattr(runtime, "model", "") or ""),
        },
        "workspace_path": str(getattr(state, "active_workspace", "") or ""),
        "message_count": len(messages),
        "messages": [message.to_dict() if hasattr(message, "to_dict") else {"role": getattr(message, "role", ""), "content": _message_text(message)} for message in messages],
    }
    if export_format == "json":
        return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    lines = [
        "# Session %s" % (payload["session_id"] or "export"),
        "",
        "- Profile: %s" % (payload["profile"] or "-"),
        "- Model: %s / %s" % (payload["model"]["protocol"] or "-", payload["model"]["model"] or "-"),
        "- Workspace: %s" % (payload["workspace_path"] or "-"),
        "- Messages: %s" % payload["message_count"],
        "",
    ]
    for message in messages:
        lines.extend(["## %s" % str(getattr(message, "role", "") or "message"), "", _message_text(message), ""])
    return "\n".join(lines).rstrip() + "\n"


def _display_export_path(state: Any, target: Path) -> str:
    workspace = Path(getattr(state, "active_workspace", "") or ".").expanduser().resolve()
    try:
        return str(target.resolve().relative_to(workspace))
    except Exception:
        return str(target)


def _message_text(message: Any) -> str:
    content_text = getattr(message, "content_text", None)
    if content_text is not None:
        return str(content_text() or "")
    return str(getattr(message, "content", "") or "")


def _command_detail_rows(payload: dict[str, Any]) -> list[list[str]]:
    command = dict(payload.get("command") or {})
    metadata = dict(payload.get("metadata") or {})
    rows = [
        ["name", str(command.get("name") or "")],
        ["path", str(payload.get("path") or command.get("path") or "")],
        ["description", str(command.get("description") or metadata.get("description") or "")],
        ["argument_hint", str(command.get("argumentHint") or metadata.get("argument_hint") or "")],
    ]
    aliases = list(command.get("aliases") or [])
    if aliases:
        rows.append(["aliases", ", ".join(str(alias) for alias in aliases)])
    rows.append(["content", str(payload.get("content") or "").strip()])
    return rows


def _parse_command_save(rest: str) -> tuple[str, str]:
    if " -- " in str(rest or ""):
        before, body = str(rest or "").split(" -- ", 1)
        name, _description = _split_once_preserve(before)
        return name, body.strip()
    name, body = _split_once_preserve(rest)
    return name, body.strip()


def _command_description(body: str) -> str:
    for line in str(body or "").splitlines():
        text = line.strip().lstrip("#").strip()
        if text:
            return text[:160]
    return ""


def _fork_messages(messages: list[Any], keep_non_system: int | None) -> list[Any]:
    if keep_non_system is None:
        return list(messages)
    kept: list[Any] = []
    seen = 0
    for message in messages:
        if getattr(message, "role", "") == "system":
            kept.append(message)
            continue
        if seen < keep_non_system:
            kept.append(message)
            seen += 1
    return kept


def _rewind_messages(messages: list[Any], drop_count: int) -> tuple[list[Any], int]:
    kept = list(messages)
    dropped = 0
    index = len(kept) - 1
    while index >= 0 and dropped < drop_count:
        if getattr(kept[index], "role", "") != "system":
            kept.pop(index)
            dropped += 1
        index -= 1
    return kept, dropped


def _prompt_template_root(state: Any) -> Path:
    base = Path(getattr(state, "active_workspace", "") or getattr(getattr(state.settings, "server", None), "ROOT_PATH", ".") or ".")
    return base.expanduser() / ".agents" / "prompts"


def _prompt_save_local(state: Any, name: str, content: str) -> dict[str, Any]:
    root = _prompt_template_root(state)
    root.mkdir(parents=True, exist_ok=True)
    path = root / ("%s.md" % name)
    text = str(content or "")
    path.write_text(text, encoding="utf-8")
    return {"name": name, "path": str(path), "bytes": len(text.encode("utf-8"))}


def _prompt_delete_local(state: Any, name: str) -> dict[str, Any]:
    path = _prompt_template_root(state) / ("%s.md" % name)
    if not path.exists():
        return {"name": name, "path": str(path), "deleted": False}
    path.unlink()
    return {"name": name, "path": str(path), "deleted": True}


def _safe_file_stem(value: str) -> str:
    text = str(value or "").strip()
    return "".join(ch for ch in text if ch.isalnum() or ch in {"-", "_"}).strip("-_")
