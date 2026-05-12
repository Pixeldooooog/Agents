from __future__ import annotations

import asyncio
import shlex
from typing import Optional

import typer

from agents.kernel.config import AgentConfigError, ModelProfile, active_profile_name, resolve_model_profile
from agents.kernel.config.paths import ENV_FILE
from agents.platform.commands import command_lookup
from agents.interfaces.bridge.fallback.ui import TerminalUI


def handle_command(
    command: str,
    session,
    ui: TerminalUI,
    profile: str,
    permission: str,
    active_tools: list[str],
    model_profiles: list[ModelProfile],
    *,
    active_model_profile: str = "",
    switch_model,
) -> tuple[bool, object]:
    base_command = command.split(maxsplit=1)[0]
    canonical = command_lookup().get(base_command)
    command_name = canonical.name if canonical is not None else base_command
    if command_name == "/exit":
        return False, session
    if command_name == "/help":
        ui.help()
        return True, session
    if command_name == "/clear":
        session.clear()
        ui.notice("cleared")
        return True, session
    if command_name == "/status":
        ui.status(session, profile=profile, permission=permission, tools=active_tools, model_profile=active_model_profile)
        return True, session
    if command_name == "/doctor":
        ui.doctor(
            session,
            profiles=model_profiles,
            tools=active_tools,
            env_file=ENV_FILE,
            model_profile=active_model_profile,
        )
        return True, session
    if command_name in {"/model"}:
        return _handle_model_command(command, session, ui, model_profiles, switch_model)
    if command_name == "/workspace":
        ui.workspace(session)
        return True, session
    if command_name == "/tools":
        ui.tools(active_tools)
        return True, session
    if command_name == "/context":
        ui.context(session)
        return True, session
    if command_name == "/trace":
        ui.trace(session)
        return True, session
    ui.error("unknown command: %s" % command)
    ui.notice("Run /help to see available commands.")
    return True, session


def resolve_start_model_profile(name: Optional[str], profiles: list[ModelProfile], ui: TerminalUI) -> ModelProfile | None:
    if not name:
        return None
    profile = resolve_model_profile(profiles, name)
    if profile is None:
        ui.error("unknown model profile: %s. Run /model to see configured profiles." % name)
        raise typer.Exit(code=2)
    return profile


def switch_model_session(
    session,
    ui: TerminalUI,
    make_session,
    *,
    profile: ModelProfile,
    profiles: list[ModelProfile],
    close_current=None,
):
    try:
        next_session = make_session(
            protocol_override=profile.protocol,
            model_override=profile.model or None,
            base_url_override=profile.base_url or None,
            api_key_override=profile.api_key or None,
        )
    except AgentConfigError as exc:
        ui.error(str(exc))
        return session
    next_session.messages = list(getattr(session, "messages", []))
    if close_current is not None:
        close_current(session)
    ui.model_switched(
        next_session,
        profile=active_profile_name(
            [profile],
            next_session.runtime.protocol,
            next_session.runtime.model,
            model_base_url(next_session),
        )
        or profile.name,
    )
    ui.model(next_session, profiles=profiles)
    return next_session


def close_session_model_client(loop: asyncio.AbstractEventLoop, session) -> None:
    runtime = getattr(session, "runtime", None)
    model_client = getattr(runtime, "model_client", None)
    close = getattr(model_client, "async_close", None)
    if close is None or loop.is_closed():
        return
    try:
        loop.run_until_complete(close())
    except Exception:
        return


def model_base_url(session) -> str:
    runtime = getattr(session, "runtime", None)
    model_client = getattr(runtime, "model_client", None)
    config = getattr(model_client, "config", None)
    return str(getattr(config, "base_url", "") or "")


def _handle_model_command(
    command: str,
    session,
    ui: TerminalUI,
    model_profiles: list[ModelProfile],
    switch_model,
) -> tuple[bool, object]:
    target = _parse_model_command(command, model_profiles=model_profiles)
    if target is None:
        ui.model(session, profiles=model_profiles)
        return True, session
    if target == "list":
        ui.model(session, profiles=model_profiles)
        return True, session
    if not isinstance(target, ModelProfile):
        ui.error(str(target))
        return True, session
    next_session = switch_model(target)
    return True, next_session


def _parse_model_command(command: str, *, model_profiles: list[ModelProfile]) -> ModelProfile | str | None:
    parts = shlex.split(command)
    if len(parts) <= 1:
        return None
    if parts[1] in {"list", "ls"}:
        return "list"
    if len(parts) > 2:
        return "/model only accepts a configured profile name. Example: /model kimi"
    value = parts[1]
    profile = resolve_model_profile(model_profiles, value)
    if profile is None:
        return "unknown model profile: %s. Run /model to see configured profiles." % value
    return profile
