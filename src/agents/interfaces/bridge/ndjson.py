from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from agents.kernel.assembly import create_agent_session_async
from agents.kernel.capabilities.tools.builtin.commands import command_render
from agents.kernel.config import (
    AgentConfigError,
    ModelProfile,
    build_model_profiles,
    resolve_model_profile,
    runtime_settings,
)
from agents.kernel.specs import AgentSpec
from agents.platform import create_terminal_persistence
from agents.platform.sessions import RunService
from agents.interfaces.bridge.active import active_task_running, cancel_active_run, start_active_task
from agents.interfaces.bridge.payloads import commands_payload_for_state, model_profiles_payload, runtime_payload, workspace_payload
from agents.interfaces.bridge.sessions import TerminalSessionStore
from agents.interfaces.bridge.slash import handle_slash_command
from agents.interfaces.bridge.turns import run_approval, run_turn
from agents.platform.commands import command_lookup
from agents.platform.profiles import (
    enabled_tools,
    local_user_id,
    normalize_profile,
    permission_settings,
    settings_for_terminal,
    system_prompt as terminal_system_prompt,
    workspace_path as resolve_terminal_workspace_path,
)


@dataclass
class BridgeState:
    args: argparse.Namespace
    profile: str
    permission: str
    active_workspace: Path | None
    active_tools: list[str]
    permission_mode: str
    approval_tools: list[str]
    settings: Any
    persistence: Any
    model_profiles: list[ModelProfile]
    session: Any
    session_store: TerminalSessionStore
    session_id: str
    event_offsets: dict[str, int]
    active_task: asyncio.Task | None = None
    active_run_id: str = ""
    task_queue: Any = None


async def main_async(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        state = await _create_state(args)
    except AgentConfigError as exc:
        _write({"type": "error", "message": str(exc)})
        return 2
    _write_ready(state)

    while True:
        line = await asyncio.to_thread(sys.stdin.readline)
        if not line:
            break
        try:
            command = json.loads(line)
        except json.JSONDecodeError as exc:
            _write({"type": "error", "message": "invalid json: %s" % exc})
            continue
        should_continue = await _handle_command(state, command)
        if not should_continue:
            break
    await _close_session_model_client(state.session)
    return 0


def main(argv: list[str] | None = None) -> None:
    raise SystemExit(asyncio.run(main_async(argv)))


async def _create_state(args: argparse.Namespace) -> BridgeState:
    profile = normalize_profile(args.profile)
    active_workspace = resolve_terminal_workspace_path(profile, Path(args.workspace_path) if args.workspace_path else None)
    active_tools = enabled_tools(profile, args.tools)
    permission_mode, approval_tools = permission_settings(args.permission, profile)
    settings = settings_for_terminal(profile, args.sandbox_provider, workspace_root=active_workspace)
    model_profiles = build_model_profiles(settings)
    persistence = create_terminal_persistence(settings, workspace_path=str(active_workspace or Path.cwd()))
    selected = resolve_model_profile(model_profiles, args.model_profile) if args.model_profile else None
    if args.model_profile and selected is None:
        raise AgentConfigError("unknown model profile: %s" % args.model_profile)
    session_store = TerminalSessionStore.for_workspace(active_workspace)
    session = await _make_session(
        args,
        settings=settings,
        persistence=persistence,
        profile=profile,
        active_workspace=active_workspace,
        active_tools=active_tools,
        permission_mode=permission_mode,
        approval_tools=approval_tools,
        model_profile=selected,
    )
    state = BridgeState(
        args=args,
        profile=profile,
        permission=args.permission,
        active_workspace=active_workspace,
        active_tools=active_tools,
        permission_mode=permission_mode,
        approval_tools=approval_tools,
        settings=settings,
        persistence=persistence,
        model_profiles=model_profiles,
        session=session,
        session_store=session_store,
        session_id=args.session_id or session_store.new_session_id(),
        event_offsets={},
    )
    _hydrate_bridge_extension_state(state)
    return state


def _hydrate_bridge_extension_state(state: BridgeState) -> None:
    context = getattr(getattr(state, "session", None), "tool_context", None)
    if context is None:
        return
    state.enabled_skills = set(getattr(context, "enabled_skills", set()) or set())
    state.enabled_plugins = set(getattr(context, "enabled_plugins", set()) or set())
    state.skill_tools = dict(getattr(context, "skill_tools", {}) or {})
    state.plugin_tools = dict(getattr(context, "plugin_tools", {}) or {})
    if bool(getattr(context, "permission_overridden", False)):
        state.permission = str(getattr(context, "permission_profile_override", "") or state.permission)
        state.permission_mode = str(getattr(context, "permission_mode_override", "") or state.permission_mode)
        state.approval_tools = [str(tool) for tool in list(getattr(context, "approval_required_tools_override", []) or [])]


async def _make_session(
    args: argparse.Namespace,
    *,
    settings: Any,
    persistence: Any,
    profile: str,
    active_workspace: Path | None,
    active_tools: list[str],
    permission_mode: str,
    approval_tools: list[str],
    model_profile: ModelProfile | None,
):
    user_id = args.user_id or local_user_id()
    agent_id = args.agent_id or "terminal"
    workspace_id = args.workspace_id or (active_workspace.name if active_workspace else "")
    system_prompt = terminal_system_prompt(args.system, profile, active_workspace)
    return await create_agent_session_async(
        settings,
        checkpoint_store=persistence.checkpoints,
        memory_store=persistence.memories,
        schedule_store=persistence.schedules,
        team_store=persistence.teams,
        hook_store=persistence.hooks,
        mcp_config_store=persistence.mcp_configs,
        session_state_store=persistence.session_states,
        sandbox_store=persistence.sandboxes,
        artifact_store=persistence.artifacts,
        artifact_blob_store=persistence.artifact_blobs,
        task_store=persistence.tasks,
        run_service=RunService(persistence.runs, sandbox_store=persistence.sandboxes),
        agent_profile_store=persistence.agent_profiles,
        spec=AgentSpec.from_overrides(
            protocol=model_profile.protocol if model_profile else None,
            model=model_profile.model if model_profile else None,
            base_url=model_profile.base_url if model_profile else None,
            api_key=model_profile.api_key if model_profile else None,
            system_prompt=system_prompt,
            enabled_tools=active_tools,
            tenant_id=args.tenant_id or "",
            user_id=user_id,
            agent_id=agent_id,
            workspace_id=workspace_id,
            workspace_path=str(active_workspace) if active_workspace else "",
            permission_profile=permission_mode,
            approval_required_tools=approval_tools,
        ),
    )


async def _handle_command(state: BridgeState, command: dict[str, Any]) -> bool:
    command_type = str(command.get("type") or "")
    if command_type == "exit":
        await cancel_active_run(state, _write, quiet=True)
        return False
    if command_type == "cancel":
        await cancel_active_run(state, _write, reason=str(command.get("reason") or ""))
        return True
    if active_task_running(state):
        if command_type == "slash" and str(command.get("text") or "").strip() == "/cancel":
            await cancel_active_run(state, _write)
        else:
            _write({"type": "error", "message": "run already active; use /cancel to interrupt"})
        return True
    if command_type == "user_message":
        run_id = str(command.get("run_id") or _run_id())
        start_active_task(state, run_id, _run_turn(state, str(command.get("text") or ""), run_id), _write)
        return True
    if command_type == "approval":
        run_id = str(command.get("run_id") or "")
        start_active_task(state, run_id, _run_approval(state, command), _write)
        return True
    if command_type == "slash":
        rendered = _render_workspace_command_prompt(state, str(command.get("text") or ""))
        if rendered is not None:
            run_id = str(command.get("run_id") or _run_id())
            _write({"type": "notice", "message": "command rendered"})
            start_active_task(state, run_id, _run_turn(state, rendered, run_id), _write)
            return True
        await _run_slash(state, str(command.get("text") or ""))
        return True
    _write({"type": "error", "message": "unknown bridge command: %s" % command_type})
    return True


async def _run_turn(state: BridgeState, text: str, run_id: str) -> None:
    await run_turn(state, text, run_id, _write)


async def _run_approval(state: BridgeState, command: dict[str, Any]) -> None:
    await run_approval(state, command, _write)


async def _run_slash(state: BridgeState, value: str) -> None:
    await handle_slash_command(
        state,
        value,
        make_session=_make_session,
        close_session_model_client=_close_session_model_client,
        write=_write,
    )


def _render_workspace_command_prompt(state: BridgeState, value: str) -> str | None:
    text = str(value or "").strip()
    if not text.startswith("/"):
        return None
    name, arguments = _split_command_input(text)
    if not name or name in command_lookup():
        return None
    context = getattr(getattr(state, "session", None), "tool_context", None)
    if context is None:
        return None
    try:
        payload = command_render(context, name=name, arguments=arguments)
    except (FileNotFoundError, ValueError):
        return None
    return str(payload.get("prompt") or "")


def _split_command_input(value: str) -> tuple[str, str]:
    parts = str(value or "").strip().split(maxsplit=1)
    if not parts:
        return "", ""
    return parts[0], parts[1] if len(parts) > 1 else ""


def _write_ready(state: BridgeState) -> None:
    _write(
        {
            "type": "ready",
            "session_id": state.session_id,
            "runtime": runtime_payload(state),
            "workspace": workspace_payload(state),
            "profile": state.profile,
            "permission": state.permission,
            "sandbox": str(getattr(state.settings.agent, "SANDBOX_PROVIDER", "local")),
            "tools": list(state.active_tools),
            "commands": commands_payload_for_state(state),
            "model_profiles": model_profiles_payload(state),
        }
    )


async def _close_session_model_client(session: Any) -> None:
    runtime = getattr(session, "runtime", None)
    model_client = getattr(runtime, "model_client", None)
    close = getattr(model_client, "async_close", None)
    if close is not None:
        try:
            await close()
        except Exception:
            return


def _run_id() -> str:
    return "terminal_%s" % uuid4().hex


def _write(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-profile", default="")
    parser.add_argument("--system", default="")
    parser.add_argument("--profile", default="coding")
    parser.add_argument("--tools", default="")
    parser.add_argument("--permission", default="guarded")
    parser.add_argument("--workspace-path", default="")
    parser.add_argument("--sandbox-provider", default="")
    parser.add_argument("--tenant-id", default="")
    parser.add_argument("--user-id", default="")
    parser.add_argument("--agent-id", default="")
    parser.add_argument("--workspace-id", default="")
    parser.add_argument("--session-id", default="")
    return parser.parse_args(argv)


if __name__ == "__main__":
    main()
