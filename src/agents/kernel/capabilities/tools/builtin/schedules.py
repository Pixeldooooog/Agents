from __future__ import annotations

from typing import Any

from agents.kernel.capabilities.tools.builtin.tasks import task_background, task_create
from agents.kernel.capabilities.tools.context import ToolRuntimeContext
from agents.kernel.schedules import ScheduleRecord, short_schedule_id
from agents.kernel.specs import AgentSpec


SCHEDULE_CREATE_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "input": {"type": "string"},
        "schedule": {"type": "string", "description": "Human-readable schedule or cron expression."},
        "enabled": {"type": "boolean"},
        "metadata": {"type": "object", "additionalProperties": {"type": "string"}},
    },
    "required": ["title", "schedule"],
}

SCHEDULE_LIST_SCHEMA = {
    "type": "object",
    "properties": {
        "enabled": {"type": "boolean", "description": "Optional enabled-state filter."},
        "limit": {"type": "integer", "minimum": 1, "maximum": 100},
    },
}

SCHEDULE_DELETE_SCHEMA = {
    "type": "object",
    "properties": {
        "schedule_id": {"type": "string", "description": "Schedule id or unambiguous short id."},
    },
    "required": ["schedule_id"],
}

SCHEDULE_RUN_SCHEMA = {
    "type": "object",
    "properties": {
        "schedule_id": {"type": "string", "description": "Schedule id or unambiguous short id."},
        "background": {"type": "boolean", "description": "Run as a background task when possible."},
    },
    "required": ["schedule_id"],
}


async def schedule_create(
    context: ToolRuntimeContext,
    title: str,
    schedule: str,
    input: str = "",
    enabled: bool = True,
    metadata: dict[str, str] | None = None,
) -> dict[str, Any]:
    title_text = _required_text(title, "title")
    schedule_text = _required_text(schedule, "schedule")
    record = ScheduleRecord.create(
        spec=_agent_spec(context),
        title=title_text,
        input=str(input or title_text),
        schedule=schedule_text,
        enabled=bool(enabled),
        metadata={"source": "tool", **_string_metadata(metadata)},
    )
    await _save_schedule(context, record)
    return {"schedule": record.to_dict()}


async def schedule_list(
    context: ToolRuntimeContext,
    enabled: bool | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    schedules = [record.to_dict() for record in await _scoped_schedules(context)]
    if enabled is not None:
        schedules = [schedule for schedule in schedules if bool(schedule.get("enabled", True)) is bool(enabled)]
    limit = max(1, min(int(limit or 50), 100))
    return {"schedules": [dict(schedule) for schedule in schedules[:limit]], "count": min(len(schedules), limit), "total": len(schedules)}


async def schedule_delete(context: ToolRuntimeContext, schedule_id: str) -> dict[str, Any]:
    target = await _resolve_schedule(context, schedule_id)
    await _delete_schedule(context, target.schedule_id)
    return {"schedule": target.to_dict(), "deleted": True}


async def schedule_run(
    context: ToolRuntimeContext,
    schedule_id: str,
    background: bool = True,
) -> dict[str, Any]:
    record = await _resolve_schedule(context, schedule_id)
    metadata = {**_string_metadata(record.metadata), "source": "schedule", "schedule_id": record.schedule_id}
    if bool(background):
        payload = await task_background(
            context,
            title=record.title,
            input=record.input,
            metadata=metadata,
            step_name="scheduled",
        )
    else:
        payload = await task_create(
            context,
            title=record.title,
            input=record.input,
            metadata=metadata,
        )
    updated = record.with_last_run(str(payload["task"]["task_id"]))
    await _save_schedule(context, updated)
    return {"schedule": updated.to_dict(), **payload}


async def _resolve_schedule(context: ToolRuntimeContext, schedule_id: str) -> ScheduleRecord:
    target = _required_text(schedule_id, "schedule_id")
    store = getattr(context, "schedule_store", None)
    if store is not None and target.startswith("sched_"):
        record = await store.load(target)
        if record is not None and _record_in_current_scope(context, record):
            return record
    if target in context.scheduled_tasks:
        return _record_from_payload(context.scheduled_tasks[target])
    matches = [record for record in await _scoped_schedules(context) if short_schedule_id(record.schedule_id).startswith(target)]
    if not matches:
        raise KeyError("schedule not found: %s" % target)
    if len(matches) > 1:
        raise ValueError("schedule id is ambiguous: %s" % target)
    return matches[0]


async def _save_schedule(context: ToolRuntimeContext, record: ScheduleRecord) -> None:
    store = getattr(context, "schedule_store", None)
    if store is not None:
        await store.save(record)
        persisted = await store.load(record.schedule_id)
        record = persisted or record
    context.scheduled_tasks[record.schedule_id] = record.to_dict()


async def _delete_schedule(context: ToolRuntimeContext, schedule_id: str) -> None:
    store = getattr(context, "schedule_store", None)
    if store is not None:
        await store.delete(schedule_id)
    context.scheduled_tasks.pop(schedule_id, None)


async def _scoped_schedules(context: ToolRuntimeContext) -> list[ScheduleRecord]:
    store = getattr(context, "schedule_store", None)
    if store is not None:
        workspace = context.workspace
        records = await store.list_for_scope(
            workspace.tenant_id,
            user_id=workspace.user_id,
            agent_id=workspace.agent_id,
            workspace_id=workspace.workspace_id,
        )
        context.scheduled_tasks = {record.schedule_id: record.to_dict() for record in records}
        return records
    return sorted(
        [_record_from_payload(record) for record in context.scheduled_tasks.values()],
        key=lambda record: (record.updated_at, record.schedule_id),
        reverse=True,
    )


def _record_from_payload(payload: dict[str, Any]) -> ScheduleRecord:
    return ScheduleRecord(
        schedule_id=str(payload.get("schedule_id") or ""),
        title=str(payload.get("title") or ""),
        input=str(payload.get("input") or ""),
        schedule=str(payload.get("schedule") or ""),
        enabled=bool(payload.get("enabled", True)),
        agent_id=str(payload.get("agent_id") or ""),
        tenant_id=str(payload.get("tenant_id") or ""),
        user_id=str(payload.get("user_id") or ""),
        workspace_id=str(payload.get("workspace_id") or ""),
        metadata=_string_metadata(payload.get("metadata")),
        created_at=float(payload.get("created_at") or 0),
        updated_at=float(payload.get("updated_at") or 0),
        last_run_task_id=str(payload.get("last_run_task_id") or ""),
        last_run_at=float(payload.get("last_run_at") or 0),
    )


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


def _record_in_current_scope(context: ToolRuntimeContext, record: ScheduleRecord) -> bool:
    workspace = context.workspace
    return (
        record.tenant_id == workspace.tenant_id
        and record.user_id in ("", workspace.user_id)
        and record.agent_id in ("", workspace.agent_id)
        and record.workspace_id in ("", workspace.workspace_id)
    )


def _required_text(value: Any, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError("%s is required" % name)
    return text


def _string_metadata(metadata: Any) -> dict[str, str]:
    return {str(key): str(value) for key, value in dict(metadata or {}).items()}


def _short_schedule_id(schedule_id: str) -> str:
    return short_schedule_id(schedule_id)
