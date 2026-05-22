from __future__ import annotations

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


def _shell_background_metadata(context: ToolRuntimeContext, handle: SandboxBackgroundCommand) -> dict[str, Any]:
    return context.background_command_metadata.setdefault(handle.task_id, {})


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
