from __future__ import annotations

from typing import Any

from agents.kernel.capabilities.tools.context import ToolRuntimeContext
from agents.kernel.capabilities.tools.builtin.tasks import (
    task_create,
    task_delete,
    task_get,
    task_list,
    task_output,
    task_stop,
    task_update,
)


async def src_origin_task_create(
    context: ToolRuntimeContext,
    *,
    subject: str,
    description: str,
    activeForm: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = await task_create(
        context,
        title=subject,
        input=description,
        metadata=_src_origin_metadata(metadata, activeForm=activeForm),
    )
    task = payload.get("task") if isinstance(payload.get("task"), dict) else {}
    payload["srcOriginTask"] = {
        "id": _src_origin_task_id(task),
        "subject": str(task.get("title") or subject),
    }
    return payload


async def src_origin_task_list(context: ToolRuntimeContext) -> dict[str, Any]:
    payload = await task_list(context)
    payload["srcOriginTasks"] = [
        _src_origin_task_list_item(task)
        for task in payload.get("tasks") or []
        if isinstance(task, dict)
    ]
    return payload


async def src_origin_task_get(context: ToolRuntimeContext, *, taskId: str) -> dict[str, Any]:
    payload = await task_get(context, task_id=taskId)
    task = payload.get("task") if isinstance(payload.get("task"), dict) else {}
    payload["srcOriginTask"] = _src_origin_task_detail(task)
    return payload


async def src_origin_task_update(
    context: ToolRuntimeContext,
    *,
    taskId: str,
    subject: str = "",
    description: str = "",
    activeForm: str = "",
    status: str = "",
    owner: str = "",
    addBlocks: list[str] | None = None,
    addBlockedBy: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        before = await task_get(context, task_id=taskId)
    except KeyError:
        return {
            "success": False,
            "taskId": str(taskId),
            "updatedFields": [],
            "error": "Task not found",
            "verificationNudgeNeeded": False,
        }

    old_task = before.get("task") if isinstance(before.get("task"), dict) else {}
    if status == "deleted":
        deleted = await task_delete(context, task_id=taskId)
        deleted_flag = bool(deleted.get("deleted"))
        return {
            "success": deleted_flag,
            "taskId": _src_origin_task_id(old_task) or str(taskId),
            "updatedFields": ["deleted"] if deleted_flag else [],
            "error": None if deleted_flag else "Failed to delete task",
            "statusChange": (
                {"from": _src_origin_output_status(str(old_task.get("status") or "")), "to": "deleted"}
                if deleted_flag
                else None
            ),
            "verificationNudgeNeeded": False,
        }

    payload = await task_update(
        context,
        task_id=taskId,
        title=subject,
        input=description,
        status=_src_origin_task_status(status),
        metadata=_src_origin_metadata(
            metadata,
            activeForm=activeForm,
            owner=owner,
            blocks=",".join(addBlocks or []),
            blockedBy=",".join(addBlockedBy or []),
        ),
    )
    task = payload.get("task") if isinstance(payload.get("task"), dict) else {}
    updated_fields = _src_origin_updated_fields(
        subject=subject,
        description=description,
        activeForm=activeForm,
        status=status,
        owner=owner,
        addBlocks=addBlocks,
        addBlockedBy=addBlockedBy,
        metadata=metadata,
    )
    payload.update(
        {
            "success": True,
            "taskId": _src_origin_task_id(task) or str(taskId),
            "updatedFields": updated_fields,
            "statusChange": _src_origin_status_change(old_task, task, status),
            "verificationNudgeNeeded": False,
        }
    )
    return payload


async def src_origin_task_output(
    context: ToolRuntimeContext,
    *,
    task_id: str,
    block: bool = True,
    timeout: float = 30000,
) -> dict[str, Any]:
    task_id = str(task_id or "")
    max_bytes = 100000
    if task_id.startswith("shell_"):
        from agents.kernel.capabilities.tools.builtin.shell import shell_output

        result = await shell_output(
            context,
            task_id=task_id,
            block=block,
            timeout_seconds=float(timeout or 0) / 1000.0,
            max_bytes=max_bytes,
        )
        return _src_origin_shell_output_payload(result)
    result = await task_output(context, task_id=task_id, max_bytes=max_bytes)
    return _src_origin_tracked_task_output_payload(result)


async def src_origin_task_stop(
    context: ToolRuntimeContext,
    *,
    task_id: str = "",
    shell_id: str = "",
) -> dict[str, Any]:
    resolved_task_id = str(task_id or shell_id or "")
    if not resolved_task_id:
        raise ValueError("Missing required parameter: task_id")
    if resolved_task_id.startswith("shell_"):
        from agents.kernel.capabilities.tools.builtin.shell import shell_kill

        result = await shell_kill(context, task_id=resolved_task_id)
        task = result.get("task") if isinstance(result.get("task"), dict) else {}
        if not result.get("killed"):
            raise ValueError(
                "Task %s is not running (status: %s)"
                % (resolved_task_id, task.get("status") or "unknown")
            )
        return _src_origin_task_stop_payload(task, task_type="local_bash")
    result = await task_stop(context, task_id=resolved_task_id)
    task = result.get("task") if isinstance(result.get("task"), dict) else {}
    return _src_origin_task_stop_payload(task, task_type=_src_origin_tracked_task_type(task))


def format_src_origin_task_create_result(result: Any) -> str:
    payload = result if isinstance(result, dict) else {}
    task = payload.get("srcOriginTask") if isinstance(payload.get("srcOriginTask"), dict) else {}
    task_id = str(task.get("id") or "")
    subject = str(task.get("subject") or "")
    return "Task #%s created successfully: %s" % (task_id, subject)


def format_src_origin_task_list_result(result: Any) -> str:
    payload = result if isinstance(result, dict) else {}
    tasks = [task for task in payload.get("srcOriginTasks") or [] if isinstance(task, dict)]
    if not tasks:
        return "No tasks found"
    return "\n".join(_format_src_origin_task_list_item(task) for task in tasks)


def format_src_origin_task_get_result(result: Any) -> str:
    payload = result if isinstance(result, dict) else {}
    task = payload.get("srcOriginTask") if isinstance(payload.get("srcOriginTask"), dict) else {}
    if not task:
        return "Task not found"
    lines = [
        "Task #%s: %s" % (task.get("id") or "", task.get("subject") or ""),
        "Status: %s" % (task.get("status") or ""),
        "Description: %s" % (task.get("description") or ""),
    ]
    blocked_by = [str(item) for item in task.get("blockedBy") or [] if str(item)]
    blocks = [str(item) for item in task.get("blocks") or [] if str(item)]
    if blocked_by:
        lines.append("Blocked by: %s" % ", ".join("#%s" % item for item in blocked_by))
    if blocks:
        lines.append("Blocks: %s" % ", ".join("#%s" % item for item in blocks))
    return "\n".join(lines)


def format_src_origin_task_update_result(result: Any) -> str:
    payload = result if isinstance(result, dict) else {}
    task_id = str(payload.get("taskId") or "")
    if not payload.get("success", True):
        return str(payload.get("error") or "Task #%s not found" % task_id)
    fields = [str(item) for item in payload.get("updatedFields") or [] if str(item)]
    return "Updated task #%s %s" % (task_id, ", ".join(fields or ["task"]))


def _src_origin_shell_output_payload(result: dict[str, Any]) -> dict[str, Any]:
    task = result.get("task") if isinstance(result.get("task"), dict) else {}
    output = str(result.get("output") or "")
    payload = {
        "task_id": str(task.get("task_id") or ""),
        "task_type": "local_bash",
        "status": str(task.get("status") or ""),
        "description": str(task.get("command") or ""),
        "output": output,
    }
    if task.get("exit_code") is not None:
        payload["exitCode"] = task.get("exit_code")
    return {"retrieval_status": str(result.get("retrieval_status") or "success"), "task": payload}


def _src_origin_tracked_task_output_payload(result: dict[str, Any]) -> dict[str, Any]:
    task = result.get("task") if isinstance(result.get("task"), dict) else {}
    output = str(result.get("output") or "")
    return {
        "retrieval_status": "success",
        "task": {
            "task_id": str(task.get("task_id") or ""),
            "task_type": _src_origin_tracked_task_type(task),
            "status": str(task.get("status") or ""),
            "description": str(task.get("title") or task.get("input") or ""),
            "prompt": str(task.get("input") or ""),
            "output": output,
        },
    }


def _src_origin_task_stop_payload(task: dict[str, Any], *, task_type: str) -> dict[str, Any]:
    task_id = str(task.get("task_id") or "")
    command = str(task.get("command") or task.get("title") or task.get("input") or "")
    return {
        "message": "Successfully stopped task: %s (%s)" % (task_id, command),
        "task_id": task_id,
        "task_type": task_type,
        "command": command,
    }


def _src_origin_tracked_task_type(task: dict[str, Any]) -> str:
    metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
    return str(metadata.get("task_type") or metadata.get("type") or metadata.get("source") or "task")


def _src_origin_metadata(metadata: dict[str, Any] | None, **extra: Any) -> dict[str, Any]:
    payload = dict(metadata or {})
    for key, value in extra.items():
        if value not in (None, ""):
            payload[key] = value
    return payload


def _src_origin_task_status(status: str) -> str:
    mapping = {
        "pending": "created",
        "in_progress": "running",
        "completed": "finished",
    }
    value = str(status or "").strip()
    return mapping.get(value, value)


def _src_origin_output_status(status: str) -> str:
    mapping = {
        "created": "pending",
        "running": "in_progress",
        "finished": "completed",
        "error": "pending",
        "canceled": "completed",
    }
    value = str(status or "").strip()
    return mapping.get(value, value)


def _src_origin_task_id(task: dict[str, Any]) -> str:
    return str(task.get("short_id") or task.get("task_id") or "")


def _src_origin_task_list_item(task: dict[str, Any]) -> dict[str, Any]:
    metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
    blocked_by = [item for item in str(metadata.get("blockedBy") or "").split(",") if item]
    return {
        "id": _src_origin_task_id(task),
        "subject": str(task.get("title") or ""),
        "status": _src_origin_output_status(str(task.get("status") or "")),
        "owner": str(metadata.get("owner") or ""),
        "blockedBy": blocked_by,
    }


def _src_origin_task_detail(task: dict[str, Any]) -> dict[str, Any]:
    metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
    blocks = [item for item in str(metadata.get("blocks") or "").split(",") if item]
    blocked_by = [item for item in str(metadata.get("blockedBy") or "").split(",") if item]
    return {
        "id": _src_origin_task_id(task),
        "subject": str(task.get("title") or ""),
        "description": str(task.get("input") or ""),
        "status": _src_origin_output_status(str(task.get("status") or "")),
        "blocks": blocks,
        "blockedBy": blocked_by,
    }


def _format_src_origin_task_list_item(task: dict[str, Any]) -> str:
    owner = " (%s)" % task["owner"] if task.get("owner") else ""
    blocked_by = [str(item) for item in task.get("blockedBy") or [] if str(item)]
    blocked = " [blocked by %s]" % ", ".join("#%s" % item for item in blocked_by) if blocked_by else ""
    return "#%s [%s] %s%s%s" % (
        task.get("id") or "",
        task.get("status") or "",
        task.get("subject") or "",
        owner,
        blocked,
    )


def _src_origin_updated_fields(
    *,
    subject: str,
    description: str,
    activeForm: str,
    status: str,
    owner: str,
    addBlocks: list[str] | None,
    addBlockedBy: list[str] | None,
    metadata: dict[str, Any] | None,
) -> list[str]:
    fields = []
    for name, value in (
        ("subject", subject),
        ("description", description),
        ("activeForm", activeForm),
        ("status", status),
        ("owner", owner),
    ):
        if value:
            fields.append(name)
    if addBlocks:
        fields.append("blocks")
    if addBlockedBy:
        fields.append("blockedBy")
    if metadata:
        fields.append("metadata")
    return fields


def _src_origin_status_change(
    old_task: dict[str, Any],
    task: dict[str, Any],
    requested_status: str,
) -> dict[str, str] | None:
    if not requested_status:
        return None
    old_status = _src_origin_output_status(str(old_task.get("status") or ""))
    new_status = _src_origin_output_status(str(task.get("status") or ""))
    if old_status == new_status:
        return None
    return {"from": old_status, "to": new_status}
