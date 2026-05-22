from __future__ import annotations

import asyncio
import contextlib
import html
import time
from typing import Any

from agents.kernel.capabilities.sandbox.types import SandboxBackgroundCommand
from agents.kernel.capabilities.tools.context import ToolRuntimeContext


def record_shell_background_command(
    context: ToolRuntimeContext,
    handle: SandboxBackgroundCommand,
    *,
    command: str,
    description: str,
    timeout_seconds: float,
    dangerously_disable_sandbox: bool,
    assistant_auto_backgrounded: bool,
) -> None:
    metadata = _shell_background_metadata(context, handle)
    metadata.update(
        {
            "command": command,
            "description": str(description or command),
            "timeout_seconds": float(timeout_seconds or 0),
            "dangerously_disable_sandbox": bool(dangerously_disable_sandbox),
            "assistant_auto_backgrounded": bool(assistant_auto_backgrounded),
            "tool_use_id": str(context.current_tool_call_id or metadata.get("tool_use_id") or ""),
            "output_file": handle.output_path,
        }
    )


def emit_shell_task_started(context: ToolRuntimeContext, handle: SandboxBackgroundCommand) -> bool:
    metadata = _shell_background_metadata(context, handle)
    if metadata.get("task_started_emitted") or not context.has_runtime_event_sink():
        return False
    metadata["task_started_emitted"] = True
    context.emit_runtime_event(
        "task_started",
        name="shell.run",
        payload={
            "task_id": handle.task_id,
            "tool_use_id": str(metadata.get("tool_use_id") or ""),
            "description": str(metadata.get("description") or handle.command),
            "task_type": "shell",
            "prompt": str(metadata.get("command") or handle.command),
            "metadata": _shell_task_event_metadata(metadata, handle),
        },
    )
    return True


def emit_shell_task_notification(
    context: ToolRuntimeContext,
    handle: SandboxBackgroundCommand,
    *,
    output: dict[str, Any] | None = None,
) -> bool:
    status = _shell_task_notification_status(handle.status)
    if status is None:
        return False
    metadata = _shell_background_metadata(context, handle)
    metadata["task_notification_observed"] = True
    if metadata.get("task_notification_emitted") or not context.has_runtime_event_sink():
        return False
    metadata["task_notification_emitted"] = True
    context.emit_runtime_event(
        "task_notification",
        name=str(context.current_tool_name or "shell.output"),
        payload={
            "task_id": handle.task_id,
            "tool_use_id": str(metadata.get("tool_use_id") or ""),
            "status": status,
            "output_file": str(metadata.get("output_file") or handle.output_path),
            "summary": _shell_task_notification_summary(handle, output=output, metadata=metadata),
            "usage": {
                "total_tokens": 0,
                "tool_uses": 0,
                "duration_ms": _shell_task_duration_ms(handle),
            },
            "metadata": _shell_task_event_metadata(metadata, handle),
        },
    )
    return True


def claim_shell_task_notification(context: ToolRuntimeContext, handle: SandboxBackgroundCommand) -> None:
    _shell_background_metadata(context, handle)["task_notification_claimed"] = True


def release_shell_task_notification_claim(context: ToolRuntimeContext, handle: SandboxBackgroundCommand) -> None:
    _shell_background_metadata(context, handle).pop("task_notification_claimed", None)


def watch_shell_task_completion(context: ToolRuntimeContext, handle: SandboxBackgroundCommand) -> bool:
    metadata = _shell_background_metadata(context, handle)
    if metadata.get("task_notification_watcher_started"):
        return False
    task = handle._task
    if task is None:
        return False
    metadata["task_notification_watcher_started"] = True

    def enqueue_when_done(completed: Any) -> None:
        with contextlib.suppress(asyncio.CancelledError, Exception):
            completed.exception()
        _enqueue_shell_task_completion(context, handle)

    task.add_done_callback(enqueue_when_done)
    return True


def _shell_background_metadata(context: ToolRuntimeContext, handle: SandboxBackgroundCommand) -> dict[str, Any]:
    return context.background_command_metadata.setdefault(handle.task_id, {})


def _enqueue_shell_task_completion(context: ToolRuntimeContext, handle: SandboxBackgroundCommand) -> bool:
    status = _shell_task_notification_status(handle.status)
    if status is None:
        return False
    metadata = _shell_background_metadata(context, handle)
    if (
        metadata.get("task_notification_observed")
        or metadata.get("task_notification_enqueued")
        or metadata.get("task_notification_claimed")
    ):
        return False
    enqueue = context.async_message_enqueue
    if enqueue is None:
        return False
    output = _read_notification_output(context, handle)
    metadata["task_notification_enqueued"] = True
    enqueue(
        {
            "type": "user",
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": _shell_task_notification_text(handle, output=output, metadata=metadata),
                    }
                ],
            },
            "priority": "later",
            "isReplay": False,
            "isSynthetic": True,
        }
    )
    return True


def _read_notification_output(context: ToolRuntimeContext, handle: SandboxBackgroundCommand) -> dict[str, Any]:
    try:
        result = context.sandbox_client.read_text(handle.output_path, max_bytes=context.sandbox.max_output_bytes)
    except Exception:  # noqa: BLE001 - notification delivery must not fail the completed task.
        return {"content": "", "bytes": 0, "truncated": False}
    return {"content": result.content, "bytes": result.bytes, "truncated": result.truncated}


def _shell_task_notification_text(
    handle: SandboxBackgroundCommand,
    *,
    output: dict[str, Any],
    metadata: dict[str, Any],
) -> str:
    status = _shell_task_xml_status(handle.status)
    summary = _shell_task_model_summary(handle, metadata=metadata)
    parts = [
        "<task_notification>",
        "<task_id>%s</task_id>" % html.escape(handle.task_id),
        "<output_file>%s</output_file>" % html.escape(str(metadata.get("output_file") or handle.output_path)),
        "<status>%s</status>" % html.escape(status),
        "<summary>%s</summary>" % html.escape(summary),
        "</task_notification>",
    ]
    content = str(output.get("content") or "").strip()
    if content:
        parts.extend(["", "Last output:", _truncate_summary(content)])
    return "\n".join(parts)


def _shell_task_model_summary(handle: SandboxBackgroundCommand, *, metadata: dict[str, Any]) -> str:
    description = str(metadata.get("description") or handle.command or handle.task_id)
    exit_code = handle.exit_code
    if handle.status == "completed":
        suffix = " (exit code %s)" % exit_code if exit_code is not None else ""
        return 'Background Bash command "%s" completed%s' % (description, suffix)
    if handle.status in {"failed", "timed_out", "error"}:
        suffix = " with exit code %s" % exit_code if exit_code is not None else ""
        return 'Background Bash command "%s" failed%s' % (description, suffix)
    if handle.status == "killed":
        return 'Background Bash command "%s" was stopped' % description
    return "%s: %s" % (str(handle.status or "completed"), description)


def _shell_task_xml_status(status: str) -> str:
    value = str(status or "").lower()
    if value == "completed":
        return "completed"
    if value == "killed":
        return "killed"
    if value in {"failed", "timed_out", "error"}:
        return "failed"
    return value or "completed"


def _shell_task_notification_status(status: str) -> str | None:
    value = str(status or "").lower()
    if value == "completed":
        return "completed"
    if value in {"failed", "timed_out", "error"}:
        return "failed"
    if value == "killed":
        return "stopped"
    return None


def _shell_task_notification_summary(
    handle: SandboxBackgroundCommand,
    *,
    output: dict[str, Any] | None,
    metadata: dict[str, Any],
) -> str:
    if handle.error:
        return _truncate_summary(handle.error)
    content = str((output or {}).get("content") or "")
    if content:
        return _truncate_summary(_last_output_lines(content, limit=8).strip())
    description = str(metadata.get("description") or handle.command or handle.task_id)
    return "%s: %s" % (str(handle.status or "completed"), description)


def _shell_task_duration_ms(handle: SandboxBackgroundCommand) -> int:
    ended_at = handle.ended_at if handle.ended_at is not None else time.time()
    return max(0, int((float(ended_at) - float(handle.started_at or ended_at)) * 1000))


def _shell_task_event_metadata(metadata: dict[str, Any], handle: SandboxBackgroundCommand) -> dict[str, Any]:
    return {
        "task_type": "shell",
        "kind": "local_shell",
        "command": str(metadata.get("command") or handle.command),
        "timeout_seconds": float(metadata.get("timeout_seconds") or 0),
        "assistant_auto_backgrounded": bool(metadata.get("assistant_auto_backgrounded", False)),
        "dangerously_disable_sandbox": bool(metadata.get("dangerously_disable_sandbox", False)),
        "output_path": str(metadata.get("output_file") or handle.output_path),
    }


def _last_output_lines(content: str, limit: int = 8) -> str:
    if not content:
        return ""
    lines = content.splitlines()
    selected = lines[-max(1, int(limit or 8)) :]
    suffix = "\n" if content.endswith("\n") and selected else ""
    return "\n".join(selected) + suffix


def _truncate_summary(value: str, limit: int = 2000) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)] + "..."
