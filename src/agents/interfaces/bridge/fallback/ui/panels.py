from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from rich.console import Console
from rich.table import Table
from rich.text import Text

from agents.platform.commands import COMMANDS
from agents.interfaces.bridge.fallback.ui.format import (
    estimate_session_tokens,
    model_base_url,
    model_endpoint,
    model_label,
    path_writable,
    short_endpoint,
    short_path,
    yes_no,
)


def startup(
    console: Console,
    session,
    *,
    profile: str,
    permission: str,
    sandbox_provider: str,
    tools: Iterable[str],
    model_profile: str = "",
) -> None:
    runtime_label = model_label(model_profile, session.runtime.protocol, session.runtime.model)
    workspace = short_path(str(session.workspace.path)) if getattr(session, "workspace", None) is not None else "no workspace"
    tool_list = list(tools)

    console.print(Text.assemble(("Agents Code", "bold cyan"), ("  ", "dim"), (runtime_label, "bold")))
    console.print(
        Text.assemble(
            ("  ", "dim"),
            (workspace, "dim"),
            ("  ", "dim"),
            profile,
            (" · ", "dim"),
            permission,
            (" · ", "dim"),
            sandbox_provider,
            (" · ", "dim"),
            str(len(tool_list)),
            " tools",
        )
    )
    console.print(Text.assemble(("  ", "dim"), ("/help", "dim"), " ", ("/model", "dim"), " ", ("/status", "dim"), " ", ("/doctor", "dim")))


def help(console: Console) -> None:
    table = Table.grid(padding=(0, 2))
    table.add_column(style="cyan")
    table.add_column(style="dim")
    console.print(Text("commands", style="bold"))
    for command in COMMANDS:
        label = ", ".join((command.name, *command.aliases))
        table.add_row(label, command.action)
    console.print(table)


def status(console: Console, session, *, profile: str, permission: str, tools: Iterable[str], model_profile: str = "") -> None:
    rows = {
        "model": "%s · %s" % (session.runtime.protocol, session.runtime.model),
        "profile": profile,
        "permission": permission,
        "messages": str(max(0, len(getattr(session, "messages", [])) - 1)),
        "tokens": estimate_session_tokens(session),
        "tools": str(len(list(tools))),
    }
    if model_profile:
        rows["model profile"] = model_profile
    endpoint = model_endpoint(session)
    if endpoint:
        rows["endpoint"] = endpoint
    if getattr(session, "workspace", None) is not None:
        rows["workspace"] = str(session.workspace.path)
    key_values(console, "Status", rows)


def model(console: Console, session, profiles: Iterable[Any] = ()) -> None:
    profile_list = list(profiles)
    if not profile_list:
        key_values(
            console,
            "Model",
            {
                "protocol": str(session.runtime.protocol),
                "model": str(session.runtime.model),
            },
        )
        return
    active_protocol = str(session.runtime.protocol)
    active_model = str(session.runtime.model)
    active_base_url = model_base_url(session).rstrip("/")
    console.print(Text("models", style="bold"))
    for profile in profile_list:
        profile_base_url = str(getattr(profile, "base_url", "") or "").rstrip("/")
        is_active = (
            getattr(profile, "protocol", "") == active_protocol
            and getattr(profile, "model", "") == active_model
            and (not active_base_url or not profile_base_url or active_base_url == profile_base_url)
        )
        status_text = "ready" if getattr(profile, "configured", False) else "missing key/model"
        marker = "●" if is_active else " "
        name = str(getattr(profile, "name", ""))
        protocol = str(getattr(profile, "protocol", ""))
        model_name = str(getattr(profile, "model", "")) or "-"
        endpoint = short_endpoint(str(getattr(profile, "endpoint", "")) or "-", limit=22)
        status_suffix = "" if status_text == "ready" else "  %s" % status_text
        console.print(
            Text.assemble(
                ("%s " % marker, "bold cyan" if is_active else "dim"),
                (name.ljust(16), "bold" if is_active else ""),
                (" %s · %s" % (protocol, model_name), "cyan" if is_active else ""),
                ("  %s" % endpoint, "dim"),
                (status_suffix, "yellow" if status_text != "ready" else "dim"),
            )
        )


def doctor(
    console: Console,
    session,
    *,
    profiles: Iterable[Any],
    tools: Iterable[str],
    env_file: str,
    model_profile: str = "",
) -> None:
    profile_list = list(profiles)
    workspace = getattr(session, "workspace", None)
    workspace_path = Path(str(workspace.path)) if workspace is not None else None
    retry_policy = getattr(getattr(session.runtime, "model_client", None), "retry_policy", None)
    rows = {
        "env file": env_file,
        "model": "%s · %s" % (session.runtime.protocol, session.runtime.model),
        "model profile": model_profile or "custom override",
        "endpoint": model_endpoint(session) or "not exposed",
        "max retries": str(getattr(retry_policy, "max_attempts", "unknown")),
        "retry base delay": str(getattr(retry_policy, "base_delay", "unknown")),
        "configured profiles": str(len([profile for profile in profile_list if getattr(profile, "configured", False)])),
        "enabled tools": str(len(list(tools))),
        "workspace": str(workspace_path) if workspace_path is not None else "not bound",
        "workspace writable": yes_no(path_writable(workspace_path)) if workspace_path is not None else "n/a",
    }
    key_values(console, "Doctor", rows)


def workspace(console: Console, session) -> None:
    current = getattr(session, "workspace", None)
    key_values(
        console,
        "Workspace",
        {
            "path": str(current.path),
            "tenant": current.tenant_id,
            "user": current.user_id,
            "agent": current.agent_id,
            "workspace": current.workspace_id,
        },
    )


def tools(console: Console, tools: Iterable[str]) -> None:
    table = Table.grid(padding=(0, 1))
    table.add_column(style="magenta")
    console.print(Text("enabled tools", style="bold"))
    for tool in tools:
        table.add_row(str(tool))
    console.print(table)


def context(console: Console, session) -> None:
    key_values(
        console,
        "Context",
        {
            "tokens": estimate_session_tokens(session),
            "limit": str(getattr(session, "max_context_tokens", "")),
            "messages": str(len(getattr(session, "messages", []))),
            "trace items": str(len(getattr(session, "context_trace", []))),
        },
    )


def trace(console: Console, session) -> None:
    trace_items = list(getattr(session, "context_trace", []) or [])
    if not trace_items:
        console.print(Text.assemble(("  ", "dim"), ("notice", "dim"), " ", ("No context trace is available.", "dim")))
        return
    table = Table.grid(padding=(0, 2))
    table.add_column(style="cyan")
    table.add_column(style="dim")
    table.add_column()
    console.print(Text("context trace", style="bold"))
    for item in trace_items[:20]:
        included = "included" if getattr(item, "included", False) else "skipped"
        reason = getattr(item, "reason", "")
        status = included if not reason else "%s: %s" % (included, reason)
        table.add_row(str(getattr(item, "id", "")), str(getattr(item, "tokens", "")), status)
    if len(trace_items) > 20:
        table.add_row("...", "", "%s more" % (len(trace_items) - 20))
    console.print(table)


def key_values(console: Console, title: str, rows: dict[str, str]) -> None:
    table = Table.grid(padding=(0, 2))
    table.add_column(style="cyan")
    table.add_column()
    console.print(Text(title.lower(), style="bold"))
    for key, value in rows.items():
        table.add_row(key, str(value))
    console.print(table)
