from __future__ import annotations

import asyncio
from typing import Any

from agents.kernel.capabilities.tools.context import ToolRuntimeContext
from agents.kernel.capabilities.tools.builtin.task_schemas import (
    SRC_ORIGIN_TASK_CREATE_SCHEMA,
    SRC_ORIGIN_TASK_GET_SCHEMA,
    SRC_ORIGIN_TASK_LIST_SCHEMA,
    SRC_ORIGIN_TASK_OUTPUT_SCHEMA,
    SRC_ORIGIN_TASK_STOP_SCHEMA,
    SRC_ORIGIN_TASK_UPDATE_SCHEMA,
    TASK_BACKGROUND_SCHEMA,
    TASK_BACKGROUNDS_SCHEMA,
    TASK_CREATE_SCHEMA,
    TASK_GET_SCHEMA,
    TASK_LIST_SCHEMA,
    TASK_OUTPUT_SCHEMA,
    TASK_RUN_SCHEMA,
    TASK_STATUS_VALUES,
    TASK_STOP_SCHEMA,
    TASK_UPDATE_SCHEMA,
)
from agents.kernel.specs import AgentSpec


async def task_create(
    context: ToolRuntimeContext,
    title: str,
    input: str = "",
    metadata: dict[str, str] | None = None,
) -> dict[str, Any]:
    store = _task_store(context)
    from agents.kernel.tasks.engine import TaskEngine

    task = await TaskEngine(store).create_task(
        _agent_spec(context),
        title=_required_text(title, "title"),
        input=str(input or title),
        metadata={"source": "tool", **_string_metadata(metadata)},
    )
    return {"task": _task_payload(task)}


async def task_list(
    context: ToolRuntimeContext,
    status: str = "",
    agent_id: str = "",
    limit: int = 50,
) -> dict[str, Any]:
    store = _task_store(context)
    workspace = context.workspace
    tasks = await store.list_tasks(
        workspace.tenant_id,
        user_id=workspace.user_id,
        agent_id=agent_id or workspace.agent_id,
    )
    wanted_status = str(status or "").strip()
    if wanted_status:
        _task_status(wanted_status)
        tasks = [task for task in tasks if task.status.value == wanted_status]
    limit = max(1, min(int(limit or 50), 100))
    return {"tasks": [_task_payload(task) for task in tasks[:limit]], "count": min(len(tasks), limit), "total": len(tasks)}


async def task_get(context: ToolRuntimeContext, task_id: str) -> dict[str, Any]:
    store = _task_store(context)
    task = await _resolve_task(context, task_id)
    steps = await store.list_steps(task.task_id)
    return {"task": _task_payload(task), "steps": [_step_payload(step) for step in steps]}


async def task_update(
    context: ToolRuntimeContext,
    task_id: str,
    status: str = "",
    title: str = "",
    input: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    store = _task_store(context)
    task = await _resolve_task(context, task_id)
    merged_metadata = dict(task.metadata)
    for key, value in dict(metadata or {}).items():
        normalized_key = str(key)
        if value is None:
            merged_metadata.pop(normalized_key, None)
        else:
            merged_metadata[normalized_key] = str(value)
    updated_task = task.with_update(
        title=str(title) if str(title or "") else None,
        input=str(input) if str(input or "") else None,
        status=_task_status(status) if str(status or "").strip() else None,
        metadata=merged_metadata,
    )
    updated = await store.update_task(updated_task)
    if updated is None:
        raise KeyError("task not found: %s" % task_id)
    return {"task": _task_payload(updated)}


async def task_delete(context: ToolRuntimeContext, task_id: str) -> dict[str, Any]:
    task = await _resolve_task(context, task_id)
    delete_task = getattr(_task_store(context), "delete_task", None)
    if not callable(delete_task):
        raise RuntimeError("task store does not support deleting tasks")
    deleted = bool(await delete_task(task.task_id))
    return {"deleted": deleted, "task": _task_payload(task)}


async def task_stop(context: ToolRuntimeContext, task_id: str) -> dict[str, Any]:
    task = await _resolve_task(context, task_id)
    from agents.kernel.tasks.engine import TaskEngine

    updated = await TaskEngine(_task_store(context)).cancel_task(task.task_id)
    return {"task": _task_payload(updated)}


async def task_output(context: ToolRuntimeContext, task_id: str, max_bytes: int = 20000) -> dict[str, Any]:
    store = _task_store(context)
    task = await _resolve_task(context, task_id)
    steps = await store.list_steps(task.task_id)
    max_bytes = max(1, min(int(max_bytes or 20000), 200000))
    output = _truncate_utf8("\n\n".join(_step_text(step) for step in steps if _step_text(step)), max_bytes)
    return {
        "task": _task_payload(task),
        "output": output,
        "steps": [_step_payload(step, include_text=False) for step in steps],
    }


async def task_run(
    context: ToolRuntimeContext,
    task_id: str = "",
    title: str = "",
    input: str = "",
    metadata: dict[str, str] | None = None,
    step_name: str = "execute",
) -> dict[str, Any]:
    if context.agent_session_factory is None:
        raise RuntimeError("agent session factory is not available")
    if int(context.subagent_depth or 0) >= int(context.max_subagent_depth or 1):
        raise RuntimeError("subagent depth limit reached")
    store = _task_store(context)
    if str(task_id or "").strip():
        task = await _resolve_task(context, task_id)
    else:
        prompt = _required_text(input or title, "input")
        from agents.kernel.tasks.engine import TaskEngine

        task = await TaskEngine(store).create_task(
            _agent_spec(context),
            title=_task_title(title or prompt),
            input=prompt,
            metadata={"source": "tool", "tool": "task.run", **_string_metadata(metadata)},
        )

    from agents.kernel.tasks.runner import TaskRunner

    result = await TaskRunner(store, _run_coordinator(context), _ContextTaskSessionFactory(context)).run_task(
        task.task_id,
        step_name=_step_name(step_name),
    )
    return {
        "task": _task_payload(result.task),
        "step": _step_payload(result.step),
        "run": _run_payload(result.run),
        "result": {
            "status": result.result.status,
            "content": result.result.content,
            "messages": len(result.result.messages),
            "tool_results": len(result.result.tool_results),
        },
    }


async def task_background(
    context: ToolRuntimeContext,
    task_id: str = "",
    title: str = "",
    input: str = "",
    metadata: dict[str, str] | None = None,
    step_name: str = "execute",
) -> dict[str, Any]:
    if context.agent_session_factory is None:
        raise RuntimeError("agent session factory is not available")
    task = await _task_for_run(context, task_id=task_id, title=title, input=input, metadata=metadata, source_tool="task.background")
    if task.task_id in context.background_tasks and not context.background_tasks[task.task_id].done():
        raise RuntimeError("task is already running in background: %s" % task.task_id)
    handle = asyncio.create_task(_run_background_task(context, task.task_id, step_name=_step_name(step_name)))
    context.background_tasks[task.task_id] = handle
    return {"task": _task_payload(task), "background": {"running": True, "done": False}}


async def task_backgrounds(context: ToolRuntimeContext) -> dict[str, Any]:
    tasks = []
    for task_id, handle in list(context.background_tasks.items()):
        payload = {"task_id": task_id, "done": bool(handle.done()), "cancelled": bool(handle.cancelled())}
        if handle.done() and not handle.cancelled():
            exc = handle.exception()
            if exc is not None:
                payload["error"] = str(exc)
            elif task_id in context.background_task_results:
                payload["result"] = context.background_task_results[task_id]
        tasks.append(payload)
    return {"background_tasks": tasks, "count": len(tasks)}


async def _run_background_task(context: ToolRuntimeContext, task_id: str, step_name: str) -> None:
    from agents.kernel.tasks.runner import TaskRunner

    result = await TaskRunner(_task_store(context), _run_coordinator(context), _ContextTaskSessionFactory(context)).run_task(
        task_id,
        step_name=step_name,
    )
    context.background_task_results[task_id] = {
        "task": _task_payload(result.task),
        "step": _step_payload(result.step, include_text=False),
        "run": _run_payload(result.run),
        "status": result.result.status,
    }


def _task_store(context: ToolRuntimeContext):
    store = getattr(context, "task_store", None)
    if store is None:
        raise RuntimeError("task store is not available")
    return store


def _run_coordinator(context: ToolRuntimeContext):
    service = getattr(context, "run_service", None)
    if service is not None:
        return service
    from agents.platform.sessions import RunService

    service = RunService(sandbox_store=getattr(context, "sandbox_store", None))
    context.run_service = service
    return service


async def _task_for_run(
    context: ToolRuntimeContext,
    *,
    task_id: str = "",
    title: str = "",
    input: str = "",
    metadata: dict[str, str] | None = None,
    source_tool: str,
) -> Any:
    store = _task_store(context)
    if str(task_id or "").strip():
        return await _resolve_task(context, task_id)
    prompt = _required_text(input or title, "input")
    from agents.kernel.tasks.engine import TaskEngine

    return await TaskEngine(store).create_task(
        _agent_spec(context),
        title=_task_title(title or prompt),
        input=prompt,
        metadata={"source": "tool", "tool": source_tool, **_string_metadata(metadata)},
    )


class _ContextTaskSessionFactory:
    def __init__(self, context: ToolRuntimeContext):
        self.context = context

    async def create(self, task: Any) -> Any:
        return await self.context.agent_session_factory(task.to_agent_spec(), task_id=task.task_id)


def _agent_spec(context: ToolRuntimeContext) -> AgentSpec:
    spec = getattr(context, "agent_spec", None)
    if isinstance(spec, AgentSpec):
        return spec
    workspace = context.workspace
    return AgentSpec.from_overrides(
        tenant_id=workspace.tenant_id,
        user_id=workspace.user_id,
        agent_id=workspace.agent_id,
        workspace_id=workspace.workspace_id,
        workspace_path=str(workspace.path),
    )


async def _resolve_task(context: ToolRuntimeContext, task_id: str) -> Any:
    store = _task_store(context)
    target = _required_text(task_id, "task_id")
    task = await store.load_task(target)
    if task is not None and _task_in_scope(context, task):
        return task
    matches = [task for task in await _scoped_tasks(context) if _task_id_matches(task.task_id, target)]
    if not matches:
        raise KeyError("task not found: %s" % target)
    if len(matches) > 1:
        raise ValueError("task id is ambiguous: %s" % target)
    return matches[0]


async def _scoped_tasks(context: ToolRuntimeContext) -> list[Any]:
    workspace = context.workspace
    return await _task_store(context).list_tasks(
        workspace.tenant_id,
        user_id=workspace.user_id,
        agent_id=workspace.agent_id,
    )


def _task_in_scope(context: ToolRuntimeContext, task: Any) -> bool:
    workspace = context.workspace
    return (
        task.tenant_id == workspace.tenant_id
        and task.user_id in ("", workspace.user_id)
        and task.agent_id in ("", workspace.agent_id)
    )


def _task_id_matches(task_id: str, target: str) -> bool:
    return task_id == target or task_id.replace("task_", "", 1).startswith(target)


def _task_status(value: str) -> Any:
    from agents.kernel.tasks.types import TaskStatus

    try:
        return TaskStatus(str(value or ""))
    except ValueError as exc:
        raise ValueError("unknown task status: %s" % value) from exc


def _task_payload(task: Any) -> dict[str, Any]:
    return {
        "task_id": task.task_id,
        "short_id": _short_task_id(task.task_id),
        "title": task.title,
        "input": task.input,
        "status": task.status.value,
        "agent_id": task.agent_id,
        "workspace_id": task.workspace_id,
        "metadata": dict(task.metadata),
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }


def _step_payload(step: Any, *, include_text: bool = True) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "step_id": step.step_id,
        "task_id": step.task_id,
        "index": step.index,
        "name": step.name,
        "run_id": step.run_id,
        "status": step.status.value,
        "created_at": step.created_at,
        "updated_at": step.updated_at,
    }
    if include_text:
        payload["input"] = step.input
        payload["output"] = step.output
        payload["error"] = step.error
    return payload


def _run_payload(run: Any) -> dict[str, Any]:
    return {
        "run_id": run.run_id,
        "agent_id": run.agent_id,
        "tenant_id": run.tenant_id,
        "user_id": run.user_id,
        "workspace_id": run.workspace_id,
        "status": run.status.value,
        "created_at": run.created_at,
        "updated_at": run.updated_at,
        "metadata": dict(run.metadata),
    }


def _step_text(step: Any) -> str:
    parts = []
    if step.output:
        parts.append(step.output)
    if step.error:
        parts.append("ERROR: %s" % step.error)
    return "\n".join(parts)


def _short_task_id(task_id: str) -> str:
    return task_id.replace("task_", "", 1)[:12]


def _string_metadata(metadata: dict[str, Any] | None) -> dict[str, str]:
    return {str(key): str(value) for key, value in dict(metadata or {}).items()}


def _required_text(value: str, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError("%s is required" % name)
    return text


def _task_title(value: str) -> str:
    first = str(value or "").strip().splitlines()[0].strip()
    return (first[:77] + "...") if len(first) > 80 else first


def _step_name(value: str) -> str:
    text = str(value or "execute").strip() or "execute"
    return text[:80]


def _truncate_utf8(value: str, max_bytes: int) -> str:
    data = str(value or "").encode("utf-8")
    if len(data) <= max_bytes:
        return str(value or "")
    return data[:max_bytes].decode("utf-8", errors="ignore") + "\n[truncated]"
