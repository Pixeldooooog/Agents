from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

from agents.interfaces.bridge.payloads import parse_positive_int, tasks_payload
from agents.interfaces.bridge.sessions import save_session_snapshot
from agents.interfaces.bridge.slash_commands.common import (
    BridgeWriter,
    agent_spec_for_state,
    create_session_from_agent_profile,
    short_task_id,
    split_once,
    task_run_service,
)
from agents.kernel.tasks import InMemoryTaskQueue, TaskEngine, TaskQueue, TaskRunner, TaskStatus, TaskStepStatus


async def handle_tasks_command(state: Any, argument: str, *, write: BridgeWriter) -> None:
    action, rest = split_once(argument)
    if not action:
        write({"type": "tasks", "tasks": await tasks_payload(state)})
        return
    if action == "create":
        await _handle_task_create(state, rest, write=write)
        return
    if action == "run":
        await _handle_task_run(state, rest, write=write)
        return
    if action in {"start", "background", "bg"}:
        await _handle_task_start_background(state, rest, write=write)
        return
    if action == "enqueue":
        await _handle_task_enqueue(state, rest, write=write)
        return
    if action == "queue":
        write({"type": "task_queue", "queue": await _task_queue_payload(state)})
        return
    if action == "drain":
        await _handle_task_drain(state, rest, write=write)
        return
    if action == "cancel":
        await _handle_task_cancel(state, rest, write=write)
        return
    write({"type": "error", "message": "unknown tasks command: %s" % action})


async def _handle_task_create(state: Any, rest: str, *, write: BridgeWriter) -> None:
    store = getattr(getattr(state, "persistence", None), "tasks", None)
    if store is None or not hasattr(store, "create_task"):
        write({"type": "error", "message": "task store is not available"})
        return
    title, input_text = _parse_task_create(rest)
    if not title:
        write({"type": "error", "message": "usage: /tasks create <title> -- <input>"})
        return
    task = await store.create_task(
        agent_spec_for_state(state),
        title=title,
        input=input_text or title,
        metadata={"source": "terminal"},
    )
    write({"type": "notice", "message": "task created: %s" % short_task_id(task.task_id)})
    write({"type": "tasks", "tasks": await tasks_payload(state)})


async def _handle_task_cancel(state: Any, rest: str, *, write: BridgeWriter) -> None:
    store = getattr(getattr(state, "persistence", None), "tasks", None)
    target = rest.strip()
    if store is None or not hasattr(store, "list_tasks") or not hasattr(store, "set_task_status"):
        write({"type": "error", "message": "task store is not available"})
        return
    if not target:
        write({"type": "error", "message": "usage: /tasks cancel <id>"})
        return
    matches = await _matching_tasks(state, store, target, write=write)
    if matches is None:
        return
    if not matches:
        write({"type": "error", "message": "task not found: %s" % target})
        return
    if len(matches) > 1:
        write({"type": "error", "message": "task id is ambiguous: %s" % target})
        return
    await TaskEngine(store).cancel_task(matches[0].task_id)
    background = _background_task_handles(state).pop(matches[0].task_id, None)
    if background is not None and not background.done():
        background.cancel()
    write({"type": "notice", "message": "task canceled: %s" % short_task_id(matches[0].task_id)})
    write({"type": "tasks", "tasks": await tasks_payload(state)})


async def _handle_task_start_background(state: Any, rest: str, *, write: BridgeWriter) -> None:
    store = getattr(getattr(state, "persistence", None), "tasks", None)
    target = rest.strip()
    if store is None or not hasattr(store, "list_tasks"):
        write({"type": "error", "message": "task store is not available"})
        return
    if not target:
        write({"type": "error", "message": "usage: /tasks start <id>"})
        return
    matches = await _matching_tasks(state, store, target, write=write)
    if matches is None:
        return
    if not matches:
        write({"type": "error", "message": "task not found: %s" % target})
        return
    if len(matches) > 1:
        write({"type": "error", "message": "task id is ambiguous: %s" % target})
        return
    task = matches[0]
    handles = _background_task_handles(state)
    existing = handles.get(task.task_id)
    if existing is not None and not existing.done():
        write({"type": "error", "message": "task already running in background: %s" % short_task_id(task.task_id)})
        return
    handles[task.task_id] = asyncio.create_task(_run_task_background(state, task.task_id, write=write))
    write({"type": "notice", "message": "task started in background: %s" % short_task_id(task.task_id)})
    write({"type": "tasks", "tasks": await tasks_payload(state)})


async def _handle_task_enqueue(state: Any, rest: str, *, write: BridgeWriter) -> None:
    store = getattr(getattr(state, "persistence", None), "tasks", None)
    target = rest.strip()
    if store is None or not hasattr(store, "list_tasks"):
        write({"type": "error", "message": "task store is not available"})
        return
    if not target:
        write({"type": "error", "message": "usage: /tasks enqueue <id>"})
        return
    matches = await _matching_tasks(state, store, target, write=write)
    if matches is None:
        return
    if not matches:
        write({"type": "error", "message": "task not found: %s" % target})
        return
    if len(matches) > 1:
        write({"type": "error", "message": "task id is ambiguous: %s" % target})
        return
    task = matches[0]
    await _task_queue(state).enqueue(task.task_id, metadata={"source": "terminal"}, **_task_queue_scope(state))
    write({"type": "notice", "message": "task queued: %s" % short_task_id(task.task_id)})
    write({"type": "task_queue", "queue": await _task_queue_payload(state)})


async def _handle_task_drain(state: Any, rest: str, *, write: BridgeWriter) -> None:
    queue = _task_queue(state)
    limit = parse_positive_int(rest)
    if rest.strip() and limit is None:
        write({"type": "error", "message": "usage: /tasks drain [limit]"})
        return
    ran = 0
    while limit is None or ran < limit:
        item = await queue.dequeue(**_task_queue_scope(state))
        if item is None:
            break
        await _handle_task_run(state, item.task_id, write=write)
        ran += 1
    write({"type": "notice", "message": "task queue drained: %d" % ran})
    write({"type": "task_queue", "queue": await _task_queue_payload(state)})


async def _handle_task_run(state: Any, rest: str, *, write: BridgeWriter) -> None:
    store = getattr(getattr(state, "persistence", None), "tasks", None)
    target = rest.strip()
    if store is None or not hasattr(store, "list_tasks"):
        write({"type": "error", "message": "task store is not available"})
        return
    if not target:
        write({"type": "error", "message": "usage: /tasks run <id>"})
        return
    matches = await _matching_tasks(state, store, target, write=write)
    if matches is None:
        return
    if not matches:
        write({"type": "error", "message": "task not found: %s" % target})
        return
    if len(matches) > 1:
        write({"type": "error", "message": "task id is ambiguous: %s" % target})
        return
    task = matches[0]
    engine = TaskEngine(store)
    run_id = "run_%s" % uuid4().hex
    step = await engine.add_step(task.task_id, name="terminal", input=task.input, run_id=run_id, metadata={"source": "terminal"})
    await engine.start_step(step.step_id, run_id=run_id)
    write({"type": "turn_started", "run_id": run_id})
    try:
        result = await state.session.send(step.input, run_id=run_id, task_id=task.task_id)
    except Exception as exc:
        await engine.fail_step(step.step_id, str(exc))
        write({"type": "runtime_event", "event": {"type": "error", "name": "task", "payload": {"message": str(exc)}}})
        write({"type": "turn_finished", "status": "error", "run_id": run_id})
        write({"type": "tasks", "tasks": await tasks_payload(state)})
        return
    for event in result.events:
        write({"type": "runtime_event", "event": event.to_dict()})
    status = _task_result_status(result)
    if status == "awaiting_approval":
        await store.update_step_status(step.step_id, TaskStepStatus.AWAITING_APPROVAL)
        await store.set_task_status(task.task_id, TaskStatus.AWAITING_APPROVAL)
    elif status == "finished":
        await engine.finish_step(step.step_id, output=result.content)
        await engine.finish_task(task.task_id)
    else:
        await engine.fail_step(step.step_id, result.content or "task failed")
    save_session_snapshot(state)
    write({"type": "turn_finished", "status": status, "run_id": run_id})
    write({"type": "tasks", "tasks": await tasks_payload(state)})


def _task_queue(state: Any) -> TaskQueue:
    persistent_queue = getattr(getattr(state, "persistence", None), "task_queue", None)
    if persistent_queue is not None:
        return persistent_queue
    queue = getattr(state, "task_queue", None)
    if queue is None:
        queue = InMemoryTaskQueue()
        setattr(state, "task_queue", queue)
    return queue


def _background_task_handles(state: Any) -> dict[str, asyncio.Task]:
    handles = getattr(state, "background_tasks", None)
    if handles is None:
        handles = {}
        setattr(state, "background_tasks", handles)
    return handles


async def _run_task_background(state: Any, task_id: str, *, write: BridgeWriter) -> None:
    store = getattr(getattr(state, "persistence", None), "tasks", None)
    if store is None:
        write({"type": "error", "message": "task store is not available"})
        return
    try:
        result = await TaskRunner(store, task_run_service(state), _task_session_factory(state)).run_task(task_id)
    except asyncio.CancelledError:
        write({"type": "notice", "message": "background task canceled: %s" % short_task_id(task_id)})
        write({"type": "tasks", "tasks": await tasks_payload(state)})
        return
    except Exception as exc:  # noqa: BLE001 - background task failures must be surfaced in the TUI.
        write({"type": "runtime_event", "event": {"type": "error", "name": "task", "payload": {"message": str(exc)}}})
        write({"type": "notice", "message": "background task failed: %s" % short_task_id(task_id)})
        write({"type": "tasks", "tasks": await tasks_payload(state)})
        return
    finally:
        handle = _background_task_handles(state).get(task_id)
        if handle is asyncio.current_task():
            _background_task_handles(state).pop(task_id, None)
    write(
        {
            "type": "notice",
            "message": "background task finished: %s · %s" % (short_task_id(task_id), result.result.status),
        }
    )
    write({"type": "tasks", "tasks": await tasks_payload(state)})


def _task_session_factory(state: Any):
    factory = getattr(state, "task_session_factory", None)
    if factory is not None:
        return factory
    return _BridgeTaskSessionFactory(state)


class _BridgeTaskSessionFactory:
    def __init__(self, state: Any):
        self.state = state

    async def create(self, task: Any) -> Any:
        return await create_session_from_agent_profile(self.state, task.to_agent_spec())


async def _task_queue_payload(state: Any) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    store = getattr(getattr(state, "persistence", None), "tasks", None)
    for index, item in enumerate(await _task_queue(state).items(**_task_queue_scope(state)), start=1):
        details = item.metadata.get("source", "terminal")
        if store is not None and hasattr(store, "load_task"):
            task = await store.load_task(item.task_id)
            if task is not None:
                status = getattr(task.status, "value", str(task.status))
                details = "%s · %s" % (task.title, status)
        rows.append((short_task_id(item.task_id), "#%d · %s" % (index, details)))
    return rows or [("queue", "empty")]


def _task_queue_scope(state: Any) -> dict[str, str]:
    workspace = getattr(getattr(state, "session", None), "workspace", None)
    return {
        "tenant_id": str(getattr(workspace, "tenant_id", "") or ""),
        "user_id": str(getattr(workspace, "user_id", "") or ""),
        "agent_id": str(getattr(workspace, "agent_id", "") or ""),
        "workspace_id": str(getattr(workspace, "workspace_id", "") or ""),
    }


def _parse_task_create(rest: str) -> tuple[str, str]:
    text = str(rest or "").strip()
    if " -- " in text:
        title, input_text = text.split(" -- ", 1)
        return title.strip(), input_text.strip()
    return text, text


async def _matching_tasks(state: Any, store: Any, target: str, *, write: BridgeWriter) -> list[Any] | None:
    workspace = getattr(state.session, "workspace", None)
    if workspace is None or not getattr(workspace, "tenant_id", "") or not getattr(workspace, "user_id", ""):
        write({"type": "error", "message": "task identity scope is not available"})
        return None
    tasks = await store.list_tasks(
        workspace.tenant_id,
        user_id=workspace.user_id,
        agent_id=getattr(workspace, "agent_id", ""),
    )
    return [task for task in tasks if _task_id_matches(task.task_id, target)]


def _task_result_status(result: Any) -> str:
    approval_required = any(
        event.type == "tool_approval_required"
        for event in getattr(result, "events", []) or []
    )
    if getattr(result, "status", "") == "awaiting_approval" or approval_required:
        return "awaiting_approval"
    if getattr(result, "status", "") and getattr(result, "status", "") != "finished":
        return str(getattr(result, "status"))
    if any(event.type == "error" for event in getattr(result, "events", []) or []):
        return "error"
    return "finished"


def _task_id_matches(task_id: str, target: str) -> bool:
    normalized = str(target).strip()
    task_key = short_task_id(task_id)
    return task_id == normalized or task_key == normalized or task_key.startswith(normalized)
