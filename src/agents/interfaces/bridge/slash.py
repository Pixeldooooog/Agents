from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from agents.kernel.capabilities.memory import MemoryScope
from agents.kernel.capabilities.tools.builtin.memory import memory_add, memory_edit, memory_forget
from agents.kernel.capabilities.tools.builtin.hooks import hook_add, hook_delete, hook_list
from agents.kernel.capabilities.tools.builtin.planning import plan_clear, plan_enter, plan_exit, todo_write
from agents.kernel.config import resolve_model_profile
from agents.kernel.state import AgentProfile
from agents.interfaces.bridge.payloads import (
    agents_payload,
    capabilities_payload,
    commands_payload_for_state,
    doctor_payload,
    hooks_payload,
    memory_payload,
    model_profiles_payload,
    permissions_payload,
    plan_payload,
    runtime_payload,
    session_records_payload,
    session_payload,
    status_payload,
    todo_payload,
    trace_payload,
    tools_payload,
    workspace_payload,
)
from agents.interfaces.bridge.sessions import save_session_snapshot
from agents.interfaces.bridge.slash_commands.commands import handle_commands_command as _handle_commands_command
from agents.interfaces.bridge.slash_commands.common import (
    BridgeWriter,
    agent_spec_for_state as _agent_spec_for_state,
    create_session_from_agent_profile as _create_session_from_agent_profile,
    error_message as _error_message,
    split_once as _split_once,
    split_once_preserve as _split_once_preserve,
    tool_context as _tool_context,
)
from agents.interfaces.bridge.slash_commands.extensions import (
    handle_plugins_command as _handle_plugins_command,
    handle_skills_command as _handle_skills_command,
    sync_extension_state_from_context as _sync_extension_state_from_context,
)
from agents.interfaces.bridge.slash_commands.mcp import handle_mcp_command as _handle_mcp_command
from agents.interfaces.bridge.slash_commands.permissions import (
    handle_permissions_command as _handle_permissions_command,
    set_runtime_permission_policy as _set_runtime_permission_policy,
)
from agents.interfaces.bridge.slash_commands.prompts import handle_prompt_command as _handle_prompt_command
from agents.interfaces.bridge.slash_commands.schedules import handle_schedules_command as _handle_schedules_command
from agents.interfaces.bridge.slash_commands.sessions import (
    handle_compact_command as _handle_compact_command,
    handle_context_command as _handle_context_command,
    handle_export_command as _handle_export_command,
    handle_fork_command as _handle_fork_command,
    handle_resume_command as _handle_resume_command,
    handle_rewind_command as _handle_rewind_command,
    handle_sessions_command as _handle_sessions_command,
    handle_summary_command as _handle_summary_command,
)
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
