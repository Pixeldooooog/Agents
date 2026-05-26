from __future__ import annotations

from typing import Any

from agents.interfaces.bridge.payloads import schedules_payload, tasks_payload
from agents.interfaces.bridge.slash_commands.common import BridgeWriter, short_task_id, split_once, tool_context
from agents.kernel.capabilities.tools.builtin.schedules import (
    schedule_create,
    schedule_delete,
    schedule_list,
    schedule_run,
)


async def handle_schedules_command(state: Any, argument: str, *, write: BridgeWriter) -> None:
    action, rest = split_once(argument)
    if not action or action in {"list", "ls"}:
        await _write_schedules(state, write=write)
        return
    if action == "create":
        await _handle_schedule_create(state, rest, write=write)
        return
    if action in {"delete", "remove", "rm", "cancel"}:
        await _handle_schedule_delete(state, rest, write=write)
        return
    if action == "run":
        await _handle_schedule_run(state, rest, background=False, write=write)
        return
    if action in {"start", "background", "bg"}:
        await _handle_schedule_run(state, rest, background=True, write=write)
        return
    write({"type": "error", "message": "unknown schedules command: %s" % action})


async def _handle_schedule_create(state: Any, rest: str, *, write: BridgeWriter) -> None:
    context = tool_context(state)
    if context is None:
        write({"type": "error", "message": "tool context is not available"})
        return
    title, schedule, input_text = _parse_schedule_create(rest)
    if not title or not schedule:
        write({"type": "error", "message": "usage: /schedules create <title> -- <schedule> [-- input]"})
        return
    try:
        payload = await schedule_create(
            context,
            title=title,
            schedule=schedule,
            input=input_text,
            metadata={"source": "terminal"},
        )
    except Exception as exc:  # noqa: BLE001 - validation errors should be slash output.
        write({"type": "error", "message": "schedule create failed: %s" % exc})
        return
    write({"type": "notice", "message": "schedule created: %s" % payload["schedule"]["short_id"]})
    write({"type": "schedules", "schedules": schedules_payload(state)})


async def _handle_schedule_delete(state: Any, rest: str, *, write: BridgeWriter) -> None:
    context = tool_context(state)
    target = rest.strip()
    if context is None:
        write({"type": "error", "message": "tool context is not available"})
        return
    if not target:
        write({"type": "error", "message": "usage: /schedules delete <id>"})
        return
    try:
        payload = await schedule_delete(context, target)
    except Exception as exc:  # noqa: BLE001 - lookup errors should be slash output.
        write({"type": "error", "message": "schedule delete failed: %s" % exc})
        return
    if not payload.get("deleted"):
        write({"type": "error", "message": "schedule not found: %s" % target})
        return
    write({"type": "notice", "message": "schedule deleted: %s" % payload["schedule"]["short_id"]})
    write({"type": "schedules", "schedules": schedules_payload(state)})


async def _handle_schedule_run(state: Any, rest: str, *, background: bool, write: BridgeWriter) -> None:
    context = tool_context(state)
    target = rest.strip()
    if context is None:
        write({"type": "error", "message": "tool context is not available"})
        return
    if not target:
        write({"type": "error", "message": "usage: /schedules %s <id>" % ("start" if background else "run")})
        return
    try:
        payload = await schedule_run(context, target, background=background)
    except Exception as exc:  # noqa: BLE001 - task/schedule failures should be slash output.
        write({"type": "error", "message": "schedule run failed: %s" % exc})
        return
    mode = "started" if background else "queued"
    write({"type": "notice", "message": "schedule %s: %s" % (mode, short_task_id(payload["task"]["task_id"]))})
    write({"type": "schedules", "schedules": schedules_payload(state)})
    write({"type": "tasks", "tasks": await tasks_payload(state)})


async def _write_schedules(state: Any, *, write: BridgeWriter) -> None:
    context = tool_context(state)
    if context is not None:
        await schedule_list(context, limit=30)
    write({"type": "schedules", "schedules": schedules_payload(state)})


def _parse_schedule_create(rest: str) -> tuple[str, str, str]:
    text = str(rest or "").strip()
    if " -- " not in text:
        return "", "", ""
    parts = [part.strip() for part in text.split(" -- ")]
    if len(parts) < 2:
        return "", "", ""
    title, schedule = parts[0], parts[1]
    input_text = " -- ".join(parts[2:]).strip() if len(parts) > 2 else title
    return title, schedule, input_text
