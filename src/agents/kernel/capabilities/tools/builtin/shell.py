from __future__ import annotations

import asyncio
import math
import shlex
from typing import Any

from agents.kernel.capabilities.tools.context import ToolRuntimeContext
from agents.kernel.capabilities.tools.registry import ToolExecutionError
from agents.kernel.capabilities.tools.builtin.shell_notifications import (
    claim_shell_task_notification,
    emit_shell_task_notification,
    emit_shell_task_started,
    record_shell_background_command,
    release_shell_task_notification_claim,
    watch_shell_task_completion,
)
from agents.kernel.capabilities.tools.builtin.shell_lifecycle import (
    assistant_auto_background_after_seconds,
    background_shell_payload,
    new_shell_task_id,
    read_background_output,
    resolve_background_command,
    run_foreground_with_shell_progress,
    run_with_assistant_auto_background,
    should_stream_shell_progress,
    shell_output_path,
)


SILENT_SHELL_COMMANDS = {
    "mv",
    "cp",
    "rm",
    "mkdir",
    "rmdir",
    "chmod",
    "chown",
    "chgrp",
    "touch",
    "ln",
    "cd",
    "export",
    "unset",
    "wait",
}

SHELL_SEMANTIC_NEUTRAL_COMMANDS = {"echo", "printf", "true", "false", ":"}
SHELL_SEARCH_COMMANDS = {"find", "grep", "rg", "ag", "ack", "locate", "which", "whereis"}
SHELL_READ_COMMANDS = {"cat", "head", "tail", "less", "more", "wc", "stat", "file", "strings", "jq", "awk", "cut", "sort", "uniq", "tr"}
SHELL_LIST_COMMANDS = {"ls", "tree", "du"}
DEFAULT_RUN_TIMEOUT_SECONDS = 20.0
MAX_RUN_TIMEOUT_SECONDS = 120.0
SHELL_COMMAND_SEPARATORS = {"&&", "||", "|", ";"}
SHELL_REDIRECT_OPERATORS = {">", ">>", "<", "<<", ">&", "<&", "2>", "2>>", "1>", "1>>"}


RUN_COMMAND_SCHEMA = {
    "type": "object",
    "properties": {
        "command": {"type": "string", "description": "Shell command to run in the workspace."},
        "timeout_seconds": {"type": "number", "minimum": 1, "maximum": 120},
        "timeout": {"type": "number", "minimum": 1, "maximum": 120000, "description": "Timeout in milliseconds, compatible with src-origin BashTool."},
        "description": {"type": "string", "description": "Short description of what this command does."},
        "run_in_background": {"type": "boolean", "description": "Start the command in the background and return a task id immediately."},
        "dangerouslyDisableSandbox": {"type": "boolean", "description": "Request unsandboxed execution. This runtime rejects the override unless an explicit policy supports it."},
    },
    "required": ["command"],
}

SHELL_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "task_id": {"type": "string", "description": "Background shell task id."},
        "block": {"type": "boolean", "description": "Wait for the command to finish before returning output."},
        "timeout_seconds": {"type": "number", "minimum": 0, "maximum": 600},
        "max_bytes": {"type": "integer", "minimum": 1, "maximum": 200000},
    },
    "required": ["task_id"],
}

SHELL_BACKGROUNDS_SCHEMA = {
    "type": "object",
    "properties": {},
}

SHELL_KILL_SCHEMA = {
    "type": "object",
    "properties": {
        "task_id": {"type": "string", "description": "Background shell task id to stop."},
    },
    "required": ["task_id"],
}


async def run_command(
    context: ToolRuntimeContext,
    command: str,
    timeout_seconds: float | None = DEFAULT_RUN_TIMEOUT_SECONDS,
    timeout: float | None = None,
    description: str = "",
    run_in_background: bool = False,
    dangerouslyDisableSandbox: bool = False,
) -> dict[str, Any]:
    if bool(dangerouslyDisableSandbox):
        raise ToolExecutionError(
            "dangerouslyDisableSandbox is not supported by this runtime",
            raw={
                "command": command,
                "failed": True,
                "dangerouslyDisableSandbox": True,
                "return_code_interpretation": "Sandbox override rejected",
                "returnCodeInterpretation": "Sandbox override rejected",
            },
        )
    resolved_timeout_seconds = _resolve_run_timeout_seconds(timeout_seconds=timeout_seconds, timeout=timeout)
    if bool(run_in_background):
        return await shell_run_background(
            context,
            command=command,
            timeout_seconds=resolved_timeout_seconds,
            description=description,
            dangerously_disable_sandbox=bool(dangerouslyDisableSandbox),
        )
    sleep_pattern = detect_blocked_sleep_pattern(command)
    if sleep_pattern is not None:
        raise ValueError(
            "Blocked: %s. Use sleep.wait for deliberate waiting, or set run_in_background=true "
            "for commands that should continue while you do other work." % sleep_pattern
        )
    auto_background_after = assistant_auto_background_after_seconds(
        context,
        command,
        shell_tokens=_shell_tokens,
        max_timeout_seconds=MAX_RUN_TIMEOUT_SECONDS,
    )
    if auto_background_after is not None:
        return await run_with_assistant_auto_background(
            context,
            command=command,
            timeout_seconds=resolved_timeout_seconds,
            description=description,
            dangerously_disable_sandbox=bool(dangerouslyDisableSandbox),
            auto_background_after_seconds=auto_background_after,
            apply_contract=_apply_shell_contract_fields,
            interpret_result=interpret_command_result,
            failure_content=_shell_failure_content,
        )
    if should_stream_shell_progress(context, command, shell_tokens=_shell_tokens):
        return await run_foreground_with_shell_progress(
            context,
            command=command,
            timeout_seconds=resolved_timeout_seconds,
            description=description,
            dangerously_disable_sandbox=bool(dangerouslyDisableSandbox),
            auto_background_after_seconds=None,
            assistant_auto_backgrounded=False,
            apply_contract=_apply_shell_contract_fields,
            interpret_result=interpret_command_result,
            failure_content=_shell_failure_content,
        )
    result = await context.sandbox_client.run_command(command, timeout_seconds=resolved_timeout_seconds)
    payload = result.to_dict()
    _apply_shell_contract_fields(
        payload,
        command=command,
        description=description,
        timeout_seconds=resolved_timeout_seconds,
        background=False,
        dangerously_disable_sandbox=bool(dangerouslyDisableSandbox),
    )
    if result.timed_out:
        payload["failed"] = True
        payload["return_code_interpretation"] = "Command timed out"
        payload["returnCodeInterpretation"] = payload["return_code_interpretation"]
    else:
        interpretation = interpret_command_result(command, int(result.exit_code or 0), result.stdout, result.stderr)
        payload["failed"] = bool(interpretation["is_error"])
        if interpretation["message"]:
            payload["return_code_interpretation"] = interpretation["message"]
            payload["returnCodeInterpretation"] = interpretation["message"]
    if payload["failed"]:
        raise ToolExecutionError(_shell_failure_content(payload), raw=payload)
    return payload


async def shell_run_background(
    context: ToolRuntimeContext,
    command: str,
    timeout_seconds: float = DEFAULT_RUN_TIMEOUT_SECONDS,
    description: str = "",
    dangerously_disable_sandbox: bool = False,
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
        assistant_auto_backgrounded=False,
    )
    emit_shell_task_started(context, handle)
    watch_shell_task_completion(context, handle)
    return background_shell_payload(
        handle,
        command=command,
        description=description,
        timeout_seconds=timeout_seconds,
        dangerously_disable_sandbox=dangerously_disable_sandbox,
        assistant_auto_backgrounded=False,
        apply_contract=_apply_shell_contract_fields,
    )


def _apply_shell_contract_fields(
    payload: dict[str, Any],
    *,
    command: str,
    description: str,
    timeout_seconds: float,
    background: bool,
    dangerously_disable_sandbox: bool,
) -> None:
    payload["description"] = str(description or command)
    payload["background"] = bool(background)
    payload["timeout_seconds"] = timeout_seconds
    payload["timeout_ms"] = int(round(timeout_seconds * 1000))
    payload["interrupted"] = False
    payload["isImage"] = False
    payload["dangerouslyDisableSandbox"] = bool(dangerously_disable_sandbox)
    payload["no_output_expected"] = is_silent_shell_command(command)
    payload["noOutputExpected"] = payload["no_output_expected"]
    command_classification = classify_shell_command(command)
    payload["command_classification"] = command_classification
    payload["commandClassification"] = command_classification


def _resolve_run_timeout_seconds(timeout_seconds: float | None = DEFAULT_RUN_TIMEOUT_SECONDS, timeout: float | None = None) -> float:
    if timeout is not None:
        return _validate_run_timeout_seconds(float(timeout) / 1000.0, name="timeout")
    return _validate_run_timeout_seconds(timeout_seconds if timeout_seconds is not None else DEFAULT_RUN_TIMEOUT_SECONDS, name="timeout_seconds")


def _validate_run_timeout_seconds(value: float, *, name: str) -> float:
    try:
        seconds = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("%s must be a finite positive timeout" % name) from exc
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError("%s must be a finite positive timeout" % name)
    return min(seconds, MAX_RUN_TIMEOUT_SECONDS)


async def shell_output(
    context: ToolRuntimeContext,
    task_id: str,
    block: bool = True,
    timeout_seconds: float = 30.0,
    max_bytes: int = 20000,
) -> dict[str, Any]:
    handle = resolve_background_command(context, task_id)
    retrieval_status = "not_ready"
    if bool(block) and not handle.done():
        task = handle._task
        if task is not None:
            claim_shell_task_notification(context, handle)
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=max(0.0, float(timeout_seconds or 0.0)))
            except asyncio.TimeoutError:
                retrieval_status = "timeout"
            finally:
                if not handle.done():
                    release_shell_task_notification_claim(context, handle)
    if handle.done():
        retrieval_status = "success"
    elif not bool(block):
        retrieval_status = "not_ready"
    output = read_background_output(context, handle, max_bytes=max_bytes)
    if handle.done():
        emit_shell_task_notification(context, handle, output=output)
    return {
        "retrieval_status": retrieval_status,
        "task": handle.to_dict(),
        "output": output["content"],
        "bytes": output["bytes"],
        "truncated": output["truncated"],
    }


async def shell_backgrounds(context: ToolRuntimeContext) -> dict[str, Any]:
    tasks = []
    for handle in context.background_commands.values():
        if handle.done():
            output = read_background_output(context, handle, max_bytes=context.sandbox.max_output_bytes)
            emit_shell_task_notification(context, handle, output=output)
        tasks.append(handle.to_dict())
    return {"background_commands": tasks, "count": len(tasks)}


async def shell_kill(context: ToolRuntimeContext, task_id: str) -> dict[str, Any]:
    handle = resolve_background_command(context, task_id)
    claim_shell_task_notification(context, handle)
    if not handle.done():
        handle.kill()
        task = handle._task
        if task is not None:
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=2.0)
            except asyncio.TimeoutError:
                pass
    if not handle.done():
        handle.status = "killed"
    output = read_background_output(context, handle, max_bytes=context.sandbox.max_output_bytes)
    emit_shell_task_notification(context, handle, output=output)
    return {"task": handle.to_dict(), "killed": handle.status == "killed"}


def detect_blocked_sleep_pattern(command: str) -> str | None:
    tokens = _shell_tokens(command)
    if not tokens or tokens[0] != "sleep":
        return None
    segment: list[str] = []
    rest: list[str] = []
    separator = ""
    for token in tokens:
        if token in {"&&", "||", ";", "|"}:
            separator = token
            continue
        if not separator:
            segment.append(token)
        else:
            rest.append(token)
    if separator == "|":
        return None
    if len(segment) != 2:
        return None
    try:
        seconds = int(segment[1])
    except ValueError:
        return None
    if str(seconds) != segment[1] or seconds < 2:
        return None
    return "sleep %d followed by: %s" % (seconds, " ".join(rest)) if rest else "standalone sleep %d" % seconds


def is_silent_shell_command(command: str) -> bool:
    tokens = _shell_tokens(command)
    if not tokens:
        return False
    has_command = False
    last_operator = ""
    expect_command = True
    skip_next_redirect_target = False
    for token in tokens:
        if skip_next_redirect_target:
            skip_next_redirect_target = False
            continue
        if token in {">", ">>", ">&"}:
            skip_next_redirect_target = True
            continue
        if token in {"&&", "||", "|", ";"}:
            last_operator = token
            expect_command = True
            continue
        if not expect_command:
            continue
        base_command = token.strip().split()[0] if token.strip() else ""
        if not base_command:
            continue
        if "=" in base_command and not base_command.startswith("="):
            continue
        if last_operator == "||" and base_command in SHELL_SEMANTIC_NEUTRAL_COMMANDS:
            expect_command = False
            continue
        has_command = True
        expect_command = False
        if base_command not in SILENT_SHELL_COMMANDS:
            return False
    return has_command


def interpret_command_result(command: str, exit_code: int, stdout: str = "", stderr: str = "") -> dict[str, Any]:
    if int(exit_code) == 0:
        return {"is_error": False, "message": None}
    base_command = _heuristically_extract_exit_command(command)
    if base_command in {"grep", "rg"}:
        return {
            "is_error": int(exit_code) >= 2,
            "message": "No matches found" if int(exit_code) == 1 else "Command failed with exit code %d" % int(exit_code),
        }
    if base_command == "find":
        return {
            "is_error": int(exit_code) >= 2,
            "message": "Some directories were inaccessible" if int(exit_code) == 1 else "Command failed with exit code %d" % int(exit_code),
        }
    if base_command == "diff":
        return {
            "is_error": int(exit_code) >= 2,
            "message": "Files differ" if int(exit_code) == 1 else "Command failed with exit code %d" % int(exit_code),
        }
    if base_command in {"test", "["}:
        return {
            "is_error": int(exit_code) >= 2,
            "message": "Condition is false" if int(exit_code) == 1 else "Command failed with exit code %d" % int(exit_code),
        }
    return {"is_error": True, "message": "Command failed with exit code %d" % int(exit_code)}


def classify_shell_command(command: str) -> dict[str, bool]:
    tokens = _shell_tokens(command)
    if not tokens:
        return _empty_command_classification()
    has_search = False
    has_read = False
    has_list = False
    has_non_neutral_command = False
    expect_command = True
    skip_next_redirect_target = False
    for token in tokens:
        if skip_next_redirect_target:
            skip_next_redirect_target = False
            continue
        if token in SHELL_REDIRECT_OPERATORS:
            skip_next_redirect_target = True
            continue
        if token in SHELL_COMMAND_SEPARATORS:
            expect_command = True
            continue
        if not expect_command:
            continue
        base_command = token.strip().split()[0] if token.strip() else ""
        if not base_command:
            continue
        if _is_env_assignment(base_command):
            continue
        if base_command in SHELL_SEMANTIC_NEUTRAL_COMMANDS:
            expect_command = False
            continue
        has_non_neutral_command = True
        is_search = base_command in SHELL_SEARCH_COMMANDS
        is_read = base_command in SHELL_READ_COMMANDS
        is_list = base_command in SHELL_LIST_COMMANDS
        if not (is_search or is_read or is_list):
            return _empty_command_classification()
        has_search = has_search or is_search
        has_read = has_read or is_read
        has_list = has_list or is_list
        expect_command = False
    if not has_non_neutral_command:
        return _empty_command_classification()
    return {"isSearch": has_search, "isRead": has_read, "isList": has_list}


def _empty_command_classification() -> dict[str, bool]:
    return {"isSearch": False, "isRead": False, "isList": False}


def _heuristically_extract_exit_command(command: str) -> str:
    tokens = _shell_tokens(command)
    if not tokens:
        return ""
    last_segment: list[str] = []
    current_segment: list[str] = []
    for token in tokens:
        if token in SHELL_COMMAND_SEPARATORS:
            if current_segment:
                last_segment = current_segment
            current_segment = []
            continue
        current_segment.append(token)
    if current_segment:
        last_segment = current_segment
    return _extract_base_command(last_segment)


def _extract_base_command(tokens: list[str]) -> str:
    skip_next_redirect_target = False
    for token in tokens:
        if skip_next_redirect_target:
            skip_next_redirect_target = False
            continue
        if token in SHELL_REDIRECT_OPERATORS:
            skip_next_redirect_target = True
            continue
        if _is_env_assignment(token):
            continue
        return token.strip().split()[0] if token.strip() else ""
    return ""


def _is_env_assignment(token: str) -> bool:
    if "=" not in token or token.startswith("="):
        return False
    key = token.split("=", 1)[0]
    return bool(key) and key.replace("_", "").isalnum()


def _shell_failure_content(payload: dict[str, Any]) -> str:
    parts = []
    stdout = str(payload.get("stdout") or "").strip()
    stderr = str(payload.get("stderr") or "").strip()
    if stdout:
        parts.append(stdout)
    if stderr:
        parts.append(stderr)
    interpretation = str(payload.get("return_code_interpretation") or "").strip()
    if interpretation:
        parts.append(interpretation)
    if not parts:
        code = int(payload.get("exit_code") or 0)
        parts.append("Command failed with exit code %d" % code if code else "Command failed")
    return "\n".join(parts)


def _shell_tokens(command: str) -> list[str]:
    lexer = shlex.shlex(str(command or ""), posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        return list(lexer)
    except ValueError:
        return []
