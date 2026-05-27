from __future__ import annotations

from typing import Any

from agents.kernel.schema import RuntimeEvent
from agents.sdk.event_fields import _int, _text_field
from agents.sdk.event_payloads import _tool_result_payload_data
from agents.sdk.types import (
    SDKMessage,
    SDKTaskNotificationMessage,
    SDKTaskProgressMessage,
    SDKTaskStartedMessage,
)


def _task_messages_from_tool_result(
    event: RuntimeEvent,
    *,
    session_id: str,
    run_id: str,
) -> list[SDKMessage]:
    if event.type != "tool_result":
        return []
    payload = _tool_result_payload_data(event.payload)
    task = payload.get("task") if isinstance(payload.get("task"), dict) else {}
    name = str(event.name or "")
    tool_use_id = str(event.payload.get("tool_call_id") or "")
    messages: list[SDKMessage] = []
    if task and _is_task_start_tool(name):
        messages.append(_task_started_message(task, session_id=session_id, run_id=run_id, tool_use_id=tool_use_id))
    if task and _is_task_progress_tool(name):
        messages.append(_task_progress_message(task, payload, session_id=session_id, run_id=run_id, tool_use_id=tool_use_id))
    if task and _is_task_run_tool(name):
        notification = _task_notification_message(task, payload, session_id=session_id, run_id=run_id, tool_use_id=tool_use_id)
        if notification is not None:
            messages.append(notification)
    if name in {"task.backgrounds", "TaskBackgrounds"}:
        for item in payload.get("background_tasks") or []:
            if isinstance(item, dict):
                notification = _background_task_notification(item, session_id=session_id, run_id=run_id)
                if notification is not None:
                    messages.append(notification)
    return messages


def _task_started_message(
    task: dict[str, Any],
    *,
    session_id: str,
    run_id: str,
    tool_use_id: str,
) -> SDKTaskStartedMessage:
    metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
    return SDKTaskStartedMessage(
        session_id=session_id,
        run_id=run_id,
        task_id=str(task.get("task_id") or ""),
        tool_use_id=tool_use_id,
        description=str(task.get("title") or task.get("input") or ""),
        task_type=str(metadata.get("task_type") or metadata.get("type") or ""),
        workflow_name=str(metadata.get("workflow_name") or metadata.get("workflow") or ""),
        prompt=str(task.get("input") or ""),
    )


def _task_progress_message(
    task: dict[str, Any],
    payload: dict[str, Any],
    *,
    session_id: str,
    run_id: str,
    tool_use_id: str,
) -> SDKTaskProgressMessage:
    step = payload.get("step") if isinstance(payload.get("step"), dict) else {}
    return SDKTaskProgressMessage(
        session_id=session_id,
        run_id=run_id,
        task_id=str(task.get("task_id") or ""),
        tool_use_id=tool_use_id,
        description=str(task.get("title") or task.get("input") or ""),
        usage=_task_usage(payload),
        last_tool_name=str(step.get("name") or ""),
        summary=_task_summary(payload, task),
    )


def _task_notification_message(
    task: dict[str, Any],
    payload: dict[str, Any],
    *,
    session_id: str,
    run_id: str,
    tool_use_id: str,
) -> SDKTaskNotificationMessage | None:
    status = _task_notification_status(str(task.get("status") or payload.get("status") or ""))
    if status is None:
        return None
    return SDKTaskNotificationMessage(
        session_id=session_id,
        run_id=run_id,
        task_id=str(task.get("task_id") or ""),
        tool_use_id=tool_use_id,
        status=status,
        output_file=str(payload.get("output_file") or payload.get("outputFile") or ""),
        summary=_task_summary(payload, task),
        usage=_task_usage(payload),
    )


def _background_task_notification(
    item: dict[str, Any],
    *,
    session_id: str,
    run_id: str,
) -> SDKTaskNotificationMessage | None:
    result = item.get("result") if isinstance(item.get("result"), dict) else {}
    task = result.get("task") if isinstance(result.get("task"), dict) else {}
    task_id = str(task.get("task_id") or item.get("task_id") or "")
    status = _task_notification_status(str(result.get("status") or task.get("status") or ""))
    if not task_id or status is None:
        return None
    return SDKTaskNotificationMessage(
        session_id=session_id,
        run_id=run_id,
        task_id=task_id,
        status=status,
        summary=_task_summary(result, task),
        usage=_task_usage(result),
    )


def _task_started_event_message(
    event: RuntimeEvent,
    *,
    session_id: str,
    run_id: str,
) -> SDKTaskStartedMessage:
    payload = dict(event.payload or {})
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    return SDKTaskStartedMessage(
        session_id=session_id,
        run_id=run_id,
        task_id=_text_field(payload, "task_id", "taskId"),
        tool_use_id=_text_field(payload, "tool_use_id", "toolUseId", "tool_call_id", "toolCallId"),
        description=_text_field(payload, "description", "summary"),
        task_type=_text_field(payload, "task_type", "taskType") or str(metadata.get("task_type") or metadata.get("type") or ""),
        workflow_name=_text_field(payload, "workflow_name", "workflowName")
        or str(metadata.get("workflow_name") or metadata.get("workflow") or ""),
        prompt=_text_field(payload, "prompt", "input"),
    )


def _task_notification_event_message(
    event: RuntimeEvent,
    *,
    session_id: str,
    run_id: str,
) -> SDKTaskNotificationMessage | None:
    payload = dict(event.payload or {})
    status = _task_notification_status(_text_field(payload, "status"))
    if status is None:
        return None
    return SDKTaskNotificationMessage(
        session_id=session_id,
        run_id=run_id,
        task_id=_text_field(payload, "task_id", "taskId"),
        tool_use_id=_text_field(payload, "tool_use_id", "toolUseId", "tool_call_id", "toolCallId"),
        status=status,
        output_file=_text_field(payload, "output_file", "outputFile"),
        summary=_text_field(payload, "summary"),
        usage=_task_usage(payload),
    )


def _task_usage(payload: dict[str, Any]) -> dict[str, int]:
    result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
    return {
        "total_tokens": _int(usage.get("total_tokens")),
        "tool_uses": _int(usage.get("tool_uses", result.get("tool_results"))),
        "duration_ms": _int(usage.get("duration_ms")),
    }


def _is_task_start_tool(name: str) -> bool:
    return name in {"task.create", "TaskCreate", "task.background", "task.run", "Agent", "Task"}


def _is_task_progress_tool(name: str) -> bool:
    return name in {"task.update", "TaskUpdate"}


def _is_task_run_tool(name: str) -> bool:
    return name in {"task.run", "Agent", "Task"}


def _task_notification_status(status: str) -> str | None:
    normalized = str(status or "").lower()
    if normalized in {"completed", "finished", "succeeded", "success"}:
        return "completed"
    if normalized in {"failed", "error", "timed_out", "timeout"}:
        return "failed"
    if normalized in {"stopped", "canceled", "cancelled", "killed"}:
        return "stopped"
    return None


def _task_summary(payload: dict[str, Any], task: dict[str, Any]) -> str:
    result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    step = payload.get("step") if isinstance(payload.get("step"), dict) else {}
    return str(
        result.get("content")
        or step.get("output")
        or step.get("error")
        or payload.get("status")
        or task.get("title")
        or ""
    )
