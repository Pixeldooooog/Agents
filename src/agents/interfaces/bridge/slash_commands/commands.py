from __future__ import annotations

from typing import Any

from agents.interfaces.bridge.payloads import commands_payload_for_state
from agents.interfaces.bridge.slash_commands.common import (
    BridgeWriter,
    split_once,
    split_once_preserve,
    tool_context,
)
from agents.interfaces.bridge.slash_commands.tool_execution import execute_slash_tool
from agents.kernel.capabilities.tools.builtin.commands import (
    command_delete,
    command_read,
    command_render,
    command_save,
)


async def handle_commands_command(state: Any, argument: str, *, write: BridgeWriter) -> None:
    action, rest = split_once(argument)
    if not action or action in {"list", "ls"}:
        write({"type": "commands", "commands": commands_payload_for_state(state)})
        return
    context = tool_context(state)
    if context is None:
        write({"type": "error", "message": "tool context is not available"})
        return
    if action in {"read", "show", "view"}:
        _handle_command_read(context, rest, write=write)
        return
    if action == "render":
        _handle_command_render(context, rest, write=write)
        return
    if action == "save":
        await _handle_command_save(state, context, rest, write=write)
        return
    if action in {"delete", "remove", "rm"}:
        await _handle_command_delete(state, context, rest, write=write)
        return
    write({"type": "error", "message": "unknown commands command: %s" % action})


def _handle_command_read(context: Any, rest: str, *, write: BridgeWriter) -> None:
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


def _handle_command_render(context: Any, rest: str, *, write: BridgeWriter) -> None:
    name, arguments = split_once_preserve(rest)
    if not name:
        write({"type": "error", "message": "usage: /commands render <name> [arguments]"})
        return
    try:
        payload = command_render(context, name, arguments=arguments)
    except Exception as exc:  # noqa: BLE001 - command rendering errors should be surfaced.
        write({"type": "error", "message": "command render failed: %s" % exc})
        return
    write({"type": "prompt", "prompt": [["command", payload["command"]["name"]], ["prompt", payload["prompt"]]]})


async def _handle_command_save(state: Any, context: Any, rest: str, *, write: BridgeWriter) -> None:
    name, body = _parse_command_save(rest)
    if not name or not body:
        write({"type": "error", "message": "usage: /commands save <name> [description] -- <prompt>"})
        return
    description = _command_description(body)
    payload = await execute_slash_tool(
        state,
        tool_name="command.save",
        arguments={
            "name": name,
            "content": body,
            "description": description,
            "overwrite": True,
        },
        write=write,
        error_label="command save",
        fallback=lambda: command_save(
            context,
            name=name,
            content=body,
            description=description,
            overwrite=True,
        ),
    )
    if payload is None:
        return
    write({"type": "notice", "message": "command saved: %s" % payload["name"]})
    write({"type": "commands", "commands": commands_payload_for_state(state)})


async def _handle_command_delete(state: Any, context: Any, rest: str, *, write: BridgeWriter) -> None:
    name = rest.strip()
    if not name:
        write({"type": "error", "message": "usage: /commands delete <name>"})
        return
    payload = await execute_slash_tool(
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
        name, _description = split_once_preserve(before)
        return name, body.strip()
    name, body = split_once_preserve(rest)
    return name, body.strip()


def _command_description(body: str) -> str:
    for line in str(body or "").splitlines():
        text = line.strip().lstrip("#").strip()
        if text:
            return text[:160]
    return ""
