from __future__ import annotations

import asyncio
import math
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from agents.kernel.capabilities.sandbox.types import SandboxBackgroundCommand
from agents.kernel.capabilities.tools.context import ToolRuntimeContext
from agents.kernel.capabilities.tools.registry import ToolExecutionError
from agents.kernel.capabilities.tools.builtin.shell_notifications import (
    emit_shell_task_started,
    record_shell_background_command,
    watch_shell_task_completion,
)


ASSISTANT_AUTO_BACKGROUND_SECONDS = 15.0
DISALLOWED_AUTO_BACKGROUND_COMMANDS = {"sleep"}
SHELL_PROGRESS_AFTER_SECONDS = 2.0
SHELL_PROGRESS_INTERVAL_SECONDS = 1.0
SHELL_STALL_AFTER_SECONDS = 10.0

ShellContractFormatter = Callable[..., None]
ShellResultInterpreter = Callable[[str, int, str, str], dict[str, Any]]
ShellFailureFormatter = Callable[[dict[str, Any]], str]
ShellTokenParser = Callable[[str], list[str]]


@dataclass(frozen=True)
class ShellProgressSettings:
    after_seconds: float = SHELL_PROGRESS_AFTER_SECONDS
    interval_seconds: float = SHELL_PROGRESS_INTERVAL_SECONDS
    stall_after_seconds: float = SHELL_STALL_AFTER_SECONDS


async def run_with_assistant_auto_background(
    context: ToolRuntimeContext,
    *,
    command: str,
    timeout_seconds: float,
    description: str,
    dangerously_disable_sandbox: bool,
    auto_background_after_seconds: float,
    apply_contract: ShellContractFormatter,
    interpret_result: ShellResultInterpreter,
    failure_content: ShellFailureFormatter,
) -> dict[str, Any]:
    payload = await run_foreground_with_shell_progress(
        context,
        command=command,
        timeout_seconds=timeout_seconds,
        description=description,
        dangerously_disable_sandbox=dangerously_disable_sandbox,
        auto_background_after_seconds=auto_background_after_seconds,
        assistant_auto_backgrounded=True,
        apply_contract=apply_contract,
        interpret_result=interpret_result,
        failure_content=failure_content,
    )
    return payload


async def run_foreground_with_shell_progress(
    context: ToolRuntimeContext,
    *,
    command: str,
    timeout_seconds: float,
    description: str,
    dangerously_disable_sandbox: bool,
    auto_background_after_seconds: float | None,
    assistant_auto_backgrounded: bool,
    apply_contract: ShellContractFormatter,
    interpret_result: ShellResultInterpreter,
    failure_content: ShellFailureFormatter,
) -> dict[str, Any]:
    task_id = new_shell_task_id(context)
    output_path = shell_output_path(task_id)
    handle = await context.sandbox_client.start_background_command(
        task_id=task_id,
        command=command,
        output_path=output_path,
        timeout_seconds=timeout_seconds,
    )
    context.background_commands[task_id] = handle
    record_shell_background_command(
        context,
        handle,
        command=command,
        description=description,
        timeout_seconds=timeout_seconds,
        dangerously_disable_sandbox=dangerously_disable_sandbox,
        assistant_auto_backgrounded=assistant_auto_backgrounded,
    )
    try:
        completed = await _wait_for_background_completion(
            context,
            handle,
            command=command,
            description=description,
            timeout_seconds=timeout_seconds,
            auto_background_after_seconds=auto_background_after_seconds,
        )
        if not completed:
            emit_shell_task_started(context, handle)
            watch_shell_task_completion(context, handle)
            return background_shell_payload(
                handle,
                command=command,
                description=description,
                timeout_seconds=timeout_seconds,
                dangerously_disable_sandbox=dangerously_disable_sandbox,
                assistant_auto_backgrounded=assistant_auto_backgrounded,
                apply_contract=apply_contract,
            )
    except asyncio.CancelledError:
        await _kill_and_wait(handle)
        context.background_commands.pop(task_id, None)
        context.background_command_metadata.pop(task_id, None)
        raise
    context.background_commands.pop(task_id, None)
    context.background_command_metadata.pop(task_id, None)
    output = read_background_output(context, handle, max_bytes=context.sandbox.max_output_bytes)
    payload = _foreground_payload_from_background(
        handle,
        command=command,
        description=description,
        timeout_seconds=timeout_seconds,
        dangerously_disable_sandbox=dangerously_disable_sandbox,
        output=output,
        apply_contract=apply_contract,
        interpret_result=interpret_result,
    )
    if payload["failed"]:
        raise ToolExecutionError(failure_content(payload), raw=payload)
    return payload


def background_shell_payload(
    handle: SandboxBackgroundCommand,
    *,
    command: str,
    description: str,
    timeout_seconds: float,
    dangerously_disable_sandbox: bool,
    assistant_auto_backgrounded: bool,
    apply_contract: ShellContractFormatter,
) -> dict[str, Any]:
    payload = handle.to_dict()
    apply_contract(
        payload,
        command=command,
        description=description,
        timeout_seconds=timeout_seconds,
        background=True,
        dangerously_disable_sandbox=dangerously_disable_sandbox,
    )
    payload["backgroundTaskId"] = handle.task_id
    payload["backgroundedByUser"] = False
    payload["assistantAutoBackgrounded"] = bool(assistant_auto_backgrounded)
    payload.setdefault("stdout", "")
    payload.setdefault("stderr", "")
    payload.setdefault("exit_code", 0)
    return payload


def assistant_auto_background_after_seconds(
    context: ToolRuntimeContext,
    command: str,
    *,
    shell_tokens: ShellTokenParser,
    max_timeout_seconds: float,
) -> float | None:
    if context.agent_spec is None or int(context.subagent_depth or 0) > 0:
        return None
    if not _is_auto_background_allowed(command, shell_tokens=shell_tokens):
        return None
    metadata = dict(getattr(context.agent_spec, "metadata", None) or {})
    enabled = metadata.get("shellAssistantAutoBackground", metadata.get("shell_assistant_auto_background", True))
    if enabled is False:
        return None
    value = metadata.get(
        "shellAssistantAutoBackgroundAfterSeconds",
        metadata.get("shell_assistant_auto_background_after_seconds", ASSISTANT_AUTO_BACKGROUND_SECONDS),
    )
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        seconds = ASSISTANT_AUTO_BACKGROUND_SECONDS
    if not math.isfinite(seconds) or seconds <= 0:
        return None
    return min(seconds, max_timeout_seconds)


def should_stream_shell_progress(
    context: ToolRuntimeContext,
    command: str,
    *,
    shell_tokens: ShellTokenParser,
) -> bool:
    if not context.has_runtime_event_sink():
        return False
    return _is_auto_background_allowed(command, shell_tokens=shell_tokens)


def shell_progress_settings(context: ToolRuntimeContext) -> ShellProgressSettings:
    metadata = dict(getattr(getattr(context, "agent_spec", None), "metadata", None) or {})
    return ShellProgressSettings(
        after_seconds=_metadata_seconds(
            metadata,
            "shellProgressAfterSeconds",
            "shell_progress_after_seconds",
            default=SHELL_PROGRESS_AFTER_SECONDS,
        ),
        interval_seconds=max(
            0.05,
            _metadata_seconds(
                metadata,
                "shellProgressIntervalSeconds",
                "shell_progress_interval_seconds",
                default=SHELL_PROGRESS_INTERVAL_SECONDS,
            ),
        ),
        stall_after_seconds=_metadata_seconds(
            metadata,
            "shellStallAfterSeconds",
            "shell_stall_after_seconds",
            default=SHELL_STALL_AFTER_SECONDS,
        ),
    )


def new_shell_task_id(context: ToolRuntimeContext) -> str:
    while True:
        task_id = "shell_%s" % uuid.uuid4().hex[:12]
        if task_id not in context.background_commands:
            return task_id


def shell_output_path(task_id: str) -> str:
    return ".agents/task-output/%s.log" % task_id


def resolve_background_command(context: ToolRuntimeContext, task_id: str) -> SandboxBackgroundCommand:
    value = str(task_id or "").strip()
    if not value:
        raise ValueError("task_id is required")
    matches = [handle for key, handle in context.background_commands.items() if key == value or key.startswith(value)]
    if not matches:
        raise KeyError("background shell task not found: %s" % value)
    if len(matches) > 1:
        raise ValueError("ambiguous background shell task id: %s" % value)
    return matches[0]


def read_background_output(context: ToolRuntimeContext, handle: SandboxBackgroundCommand, max_bytes: int) -> dict[str, Any]:
    try:
        result = context.sandbox_client.read_text(
            handle.output_path,
            max_bytes=max(1, min(int(max_bytes or 20000), 200000)),
        )
    except FileNotFoundError:
        return {"content": "", "bytes": 0, "truncated": False}
    return {"content": result.content, "bytes": result.bytes, "truncated": result.truncated}


def _foreground_payload_from_background(
    handle: SandboxBackgroundCommand,
    *,
    command: str,
    description: str,
    timeout_seconds: float,
    dangerously_disable_sandbox: bool,
    output: dict[str, Any],
    apply_contract: ShellContractFormatter,
    interpret_result: ShellResultInterpreter,
) -> dict[str, Any]:
    payload = {
        "command": command,
        "exit_code": int(handle.exit_code or 0),
        "stdout": output["content"],
        "stderr": "",
        "timed_out": bool(handle.timed_out),
        "truncated": output["truncated"],
    }
    apply_contract(
        payload,
        command=command,
        description=description,
        timeout_seconds=timeout_seconds,
        background=False,
        dangerously_disable_sandbox=dangerously_disable_sandbox,
    )
    if handle.timed_out:
        payload["failed"] = True
        payload["return_code_interpretation"] = "Command timed out"
        payload["returnCodeInterpretation"] = payload["return_code_interpretation"]
    else:
        interpretation = interpret_result(command, int(handle.exit_code or 0), output["content"], "")
        payload["failed"] = bool(interpretation["is_error"])
        if interpretation["message"]:
            payload["return_code_interpretation"] = interpretation["message"]
            payload["returnCodeInterpretation"] = interpretation["message"]
    return payload


async def _kill_and_wait(handle: SandboxBackgroundCommand) -> None:
    if handle.done():
        return
    handle.kill()
    task = handle._task
    if task is not None:
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=2.0)
        except asyncio.TimeoutError:
            pass


async def _wait_for_background_completion(
    context: ToolRuntimeContext,
    handle: SandboxBackgroundCommand,
    *,
    command: str,
    description: str,
    timeout_seconds: float,
    auto_background_after_seconds: float | None,
) -> bool:
    task = handle._task
    if task is None:
        return True
    settings = shell_progress_settings(context)
    started_at = time.monotonic()
    auto_background_deadline = math.inf
    if auto_background_after_seconds is not None:
        auto_background_deadline = started_at + max(0.0, auto_background_after_seconds)
    next_progress_at = started_at + settings.after_seconds
    last_output_bytes = int(handle.output_bytes or 0)
    last_output_change_at = started_at
    stalled_emitted = False
    while True:
        if task.done():
            return True
        now = time.monotonic()
        if now >= auto_background_deadline:
            return False
        wait_until = min(auto_background_deadline, next_progress_at)
        wait_seconds = max(0.0, wait_until - now)
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=wait_seconds)
            return True
        except asyncio.TimeoutError:
            pass
        if task.done():
            return True
        now = time.monotonic()
        if now >= auto_background_deadline:
            return False
        if now < next_progress_at:
            continue
        output = read_background_output(context, handle, max_bytes=context.sandbox.max_output_bytes)
        total_bytes = int(handle.output_bytes or output["bytes"] or 0)
        if total_bytes != last_output_bytes:
            last_output_bytes = total_bytes
            last_output_change_at = now
            stalled_emitted = False
        elapsed_seconds = int(now - started_at)
        _emit_shell_progress(
            context,
            handle,
            command=command,
            description=description,
            timeout_seconds=timeout_seconds,
            output=output,
            elapsed_seconds=elapsed_seconds,
            status="running",
        )
        if (
            settings.stall_after_seconds > 0
            and not stalled_emitted
            and now - last_output_change_at >= settings.stall_after_seconds
        ):
            _emit_shell_progress(
                context,
                handle,
                command=command,
                description=description,
                timeout_seconds=timeout_seconds,
                output=output,
                elapsed_seconds=elapsed_seconds,
                status="stalled",
            )
            stalled_emitted = True
        next_progress_at = now + settings.interval_seconds


def _emit_shell_progress(
    context: ToolRuntimeContext,
    handle: SandboxBackgroundCommand,
    *,
    command: str,
    description: str,
    timeout_seconds: float,
    output: dict[str, Any],
    elapsed_seconds: int,
    status: str,
) -> None:
    content = str(output.get("content") or "")
    context.emit_runtime_event(
        "tool_progress",
        name=getattr(context, "current_tool_name", "") or "shell.run",
        payload={
            "status": status,
            "input": {
                "command": command,
                "description": description,
                "timeout_seconds": timeout_seconds,
            },
            "output": _last_output_lines(content),
            "full_output": content,
            "elapsed_time_seconds": elapsed_seconds,
            "total_lines": _line_count(content),
            "total_bytes": int(handle.output_bytes or output.get("bytes") or 0),
            "task_id": handle.task_id,
            "timeout_ms": int(float(timeout_seconds or 0) * 1000),
            "metadata": {
                "progress_type": "bash_progress",
                "stalled": status == "stalled",
                "output_path": handle.output_path,
            },
        },
    )


def _last_output_lines(content: str, limit: int = 5) -> str:
    if not content:
        return ""
    lines = content.splitlines()
    selected = lines[-max(1, int(limit or 5)) :]
    suffix = "\n" if content.endswith("\n") and selected else ""
    return "\n".join(selected) + suffix


def _line_count(content: str) -> int:
    if not content:
        return 0
    return content.count("\n") + (0 if content.endswith("\n") else 1)


def _metadata_seconds(metadata: dict[str, Any], camel_key: str, snake_key: str, *, default: float) -> float:
    value = metadata.get(camel_key, metadata.get(snake_key, default))
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        seconds = default
    if not math.isfinite(seconds) or seconds < 0:
        return default
    return seconds


def _is_auto_background_allowed(command: str, *, shell_tokens: ShellTokenParser) -> bool:
    tokens = shell_tokens(command)
    if not tokens:
        return True
    return tokens[0] not in DISALLOWED_AUTO_BACKGROUND_COMMANDS
