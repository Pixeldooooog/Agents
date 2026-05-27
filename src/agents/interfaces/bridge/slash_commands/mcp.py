from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from typing import Any

from agents.interfaces.bridge.payloads import mcp_payload, tools_payload
from agents.interfaces.bridge.slash_commands.common import (
    BridgeWriter,
    error_message,
    merge_unique,
    remove_runtime_enabled_tools,
    replace_runtime_enabled_tools,
    split_once,
    tool_context,
)
from agents.kernel.capabilities.tools.builtin.mcp.management import mcp_clear, mcp_configure, mcp_disable, mcp_enable, mcp_reload, mcp_remove


async def handle_mcp_command(state: Any, argument: str, *, write: BridgeWriter) -> None:
    action, rest = split_once(argument)
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
    context = tool_context(state)
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
    context = tool_context(state)
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
    context = tool_context(state)
    if context is None:
        write({"type": "error", "message": "tool context is not available"})
        return
    name = rest.strip()
    try:
        result = await mcp_enable(context, name=name)
    except Exception as exc:  # noqa: BLE001 - command errors should be user-visible.
        write({"type": "error", "message": error_message(exc)})
        return
    write({"type": "notice", "message": "mcp enabled: %s" % result.get("enabled", name or "default")})
    write({"type": "mcp", "mcp": mcp_payload(state)})


async def _handle_mcp_disable(state: Any, rest: str, *, write: BridgeWriter) -> None:
    context = tool_context(state)
    if context is None:
        write({"type": "error", "message": "tool context is not available"})
        return
    name = rest.strip()
    try:
        result = await mcp_disable(context, name=name)
    except Exception as exc:  # noqa: BLE001 - command errors should be user-visible.
        write({"type": "error", "message": error_message(exc)})
        return
    write({"type": "notice", "message": "mcp disabled: %s" % result.get("disabled", name or "default")})
    write({"type": "mcp", "mcp": mcp_payload(state)})


async def _handle_mcp_remove(state: Any, rest: str, *, write: BridgeWriter) -> None:
    context = tool_context(state)
    if context is None:
        write({"type": "error", "message": "tool context is not available"})
        return
    name = rest.strip()
    try:
        result = await mcp_remove(context, name=name)
    except Exception as exc:  # noqa: BLE001 - command errors should be user-visible.
        write({"type": "error", "message": error_message(exc)})
        return
    write({"type": "notice", "message": "mcp removed: %s" % result.get("removed", name or "default")})
    write({"type": "mcp", "mcp": mcp_payload(state)})


async def _handle_mcp_reload(state: Any, *, write: BridgeWriter) -> None:
    registry = getattr(getattr(getattr(state, "session", None), "runtime", None), "tools", None)
    if registry is None or not hasattr(registry, "names"):
        write({"type": "error", "message": "tool registry is not available"})
        return
    context = tool_context(state)
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
    state.active_tools = merge_unique([tool for tool in list(getattr(state, "active_tools", []) or []) if tool not in set(removed)], added)
    remove_runtime_enabled_tools(state, removed)
    replace_runtime_enabled_tools(state, added)
    write({"type": "notice", "message": "mcp reloaded: %s tool%s" % (len(added), "" if len(added) == 1 else "s")})
    write({"type": "mcp", "mcp": mcp_payload(state)})
    write({"type": "tools", "tools": tools_payload(state)})


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
