from __future__ import annotations

import asyncio
import html
import math
import re
import time
from typing import Any

from agents.kernel.capabilities.sandbox.types import SandboxBackgroundCommand
from agents.kernel.capabilities.tools.context import ToolRuntimeContext


PROMPT_STALL_AFTER_SECONDS = 45.0
PROMPT_STALL_INTERVAL_SECONDS = 5.0
PROMPT_STALL_OUTPUT_BYTES = 4096
PROMPT_PATTERNS = (
    re.compile(r"\(y/n\)", re.IGNORECASE),
    re.compile(r"\[y/n\]", re.IGNORECASE),
    re.compile(r"\(yes/no\)", re.IGNORECASE),
    re.compile(r"\b(?:Do you|Would you|Shall I|Are you sure|Ready to)\b.*\? *$", re.IGNORECASE),
    re.compile(r"Press (any key|Enter)", re.IGNORECASE),
    re.compile(r"Continue\?", re.IGNORECASE),
    re.compile(r"Overwrite\?", re.IGNORECASE),
)


def start_shell_prompt_stall_watcher(
    context: ToolRuntimeContext,
    handle: SandboxBackgroundCommand,
    metadata: dict[str, Any],
) -> asyncio.Task | None:
    if metadata.get("prompt_stall_watcher_started") or context.async_message_enqueue is None:
        return None
    threshold = _prompt_stall_after_seconds(context)
    if threshold <= 0:
        return None
    metadata["prompt_stall_watcher_started"] = True
    watcher = asyncio.create_task(
        _watch_shell_prompt_stall(
            context,
            handle,
            metadata=metadata,
            threshold_seconds=threshold,
        )
    )
    metadata["prompt_stall_watcher"] = watcher
    return watcher


def looks_like_shell_prompt(content: str) -> bool:
    last_line = str(content or "").rstrip().split("\n")[-1] if str(content or "").strip() else ""
    return any(pattern.search(last_line) for pattern in PROMPT_PATTERNS)


async def _watch_shell_prompt_stall(
    context: ToolRuntimeContext,
    handle: SandboxBackgroundCommand,
    *,
    metadata: dict[str, Any],
    threshold_seconds: float,
) -> None:
    interval = _prompt_stall_interval_seconds(context, threshold_seconds)
    last_output_bytes = int(handle.output_bytes or 0)
    last_growth_at = time.monotonic()
    while not handle.done():
        await asyncio.sleep(interval)
        output_bytes = int(handle.output_bytes or 0)
        if output_bytes > last_output_bytes:
            last_output_bytes = output_bytes
            last_growth_at = time.monotonic()
            continue
        if time.monotonic() - last_growth_at < threshold_seconds:
            continue
        output = _read_prompt_stall_output(context, handle)
        if not looks_like_shell_prompt(output.get("content", "")):
            last_growth_at = time.monotonic()
            continue
        if _enqueue_shell_prompt_stall(context, handle, output=output, metadata=metadata):
            return


def _enqueue_shell_prompt_stall(
    context: ToolRuntimeContext,
    handle: SandboxBackgroundCommand,
    *,
    output: dict[str, Any],
    metadata: dict[str, Any],
) -> bool:
    if metadata.get("prompt_stall_enqueued") or handle.done():
        return False
    enqueue = context.async_message_enqueue
    if enqueue is None:
        return False
    metadata["prompt_stall_enqueued"] = True
    enqueue(
        {
            "type": "user",
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": _shell_prompt_stall_notification_text(handle, output=output, metadata=metadata),
                    }
                ],
            },
            "priority": "next",
            "isReplay": False,
            "isSynthetic": True,
        }
    )
    return True


def _shell_prompt_stall_notification_text(
    handle: SandboxBackgroundCommand,
    *,
    output: dict[str, Any],
    metadata: dict[str, Any],
) -> str:
    description = str(metadata.get("description") or handle.command or handle.task_id)
    summary = 'Background Bash command "%s" appears to be waiting for interactive input' % description
    parts = [
        "<task_notification>",
        "<task_id>%s</task_id>" % html.escape(handle.task_id),
        "<output_file>%s</output_file>" % html.escape(str(metadata.get("output_file") or handle.output_path)),
        "<summary>%s</summary>" % html.escape(summary),
        "</task_notification>",
    ]
    content = str(output.get("content") or "").strip()
    if content:
        parts.extend(["", "Last output:", _truncate_summary(content)])
    parts.extend(
        [
            "",
            "The command is likely blocked on an interactive prompt. Kill this task and re-run with piped input or a non-interactive flag if one exists.",
        ]
    )
    return "\n".join(parts)


def _read_prompt_stall_output(context: ToolRuntimeContext, handle: SandboxBackgroundCommand) -> dict[str, Any]:
    try:
        result = context.sandbox_client.read_text(handle.output_path, max_bytes=PROMPT_STALL_OUTPUT_BYTES)
    except Exception:  # noqa: BLE001 - prompt stall delivery must not fail the running task.
        return {"content": "", "bytes": 0, "truncated": False}
    return {"content": result.content, "bytes": result.bytes, "truncated": result.truncated}


def _prompt_stall_after_seconds(context: ToolRuntimeContext) -> float:
    metadata = dict(getattr(getattr(context, "agent_spec", None), "metadata", None) or {})
    return _metadata_seconds(
        metadata,
        "shellPromptStallAfterSeconds",
        "shell_prompt_stall_after_seconds",
        default=PROMPT_STALL_AFTER_SECONDS,
    )


def _prompt_stall_interval_seconds(context: ToolRuntimeContext, threshold_seconds: float) -> float:
    metadata = dict(getattr(getattr(context, "agent_spec", None), "metadata", None) or {})
    configured = _metadata_seconds(
        metadata,
        "shellPromptStallIntervalSeconds",
        "shell_prompt_stall_interval_seconds",
        default=PROMPT_STALL_INTERVAL_SECONDS,
    )
    return max(0.05, min(configured, max(0.05, threshold_seconds / 2.0)))


def _metadata_seconds(metadata: dict[str, Any], camel_key: str, snake_key: str, *, default: float) -> float:
    value = metadata.get(camel_key, metadata.get(snake_key, default))
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(seconds) or seconds < 0:
        return default
    return seconds


def _truncate_summary(value: str, limit: int = 2000) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)] + "..."
