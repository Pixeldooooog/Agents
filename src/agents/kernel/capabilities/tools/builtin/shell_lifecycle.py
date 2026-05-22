from __future__ import annotations

import asyncio
import math
import uuid
from collections.abc import Callable
from typing import Any

from agents.kernel.capabilities.sandbox.types import SandboxBackgroundCommand
from agents.kernel.capabilities.tools.context import ToolRuntimeContext
from agents.kernel.capabilities.tools.registry import ToolExecutionError


ASSISTANT_AUTO_BACKGROUND_SECONDS = 15.0
DISALLOWED_AUTO_BACKGROUND_COMMANDS = {"sleep"}

ShellContractFormatter = Callable[..., None]
ShellResultInterpreter = Callable[[str, int, str, str], dict[str, Any]]
ShellFailureFormatter = Callable[[dict[str, Any]], str]
ShellTokenParser = Callable[[str], list[str]]


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
    task_id = new_shell_task_id(context)
    output_path = shell_output_path(task_id)
    handle = await context.sandbox_client.start_background_command(
        task_id=task_id,
        command=command,
        output_path=output_path,
        timeout_seconds=timeout_seconds,
    )
    context.background_commands[task_id] = handle
    try:
        task = handle._task
        if task is not None:
            await asyncio.wait_for(asyncio.shield(task), timeout=max(0.0, auto_background_after_seconds))
    except asyncio.TimeoutError:
        return background_shell_payload(
            handle,
            command=command,
            description=description,
            timeout_seconds=timeout_seconds,
            dangerously_disable_sandbox=dangerously_disable_sandbox,
            assistant_auto_backgrounded=True,
            apply_contract=apply_contract,
        )
    except asyncio.CancelledError:
        await _kill_and_wait(handle)
        context.background_commands.pop(task_id, None)
        raise
    context.background_commands.pop(task_id, None)
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


def _is_auto_background_allowed(command: str, *, shell_tokens: ShellTokenParser) -> bool:
    tokens = shell_tokens(command)
    if not tokens:
        return True
    return tokens[0] not in DISALLOWED_AUTO_BACKGROUND_COMMANDS
