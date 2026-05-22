from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import Any

from agents.kernel.capabilities.tools.context import ToolRuntimeContext


SLEEP_WAKE_POLL_SECONDS = 1.0

SLEEP_WAIT_SCHEMA = {
    "type": "object",
    "properties": {
        "duration_seconds": {
            "type": "number",
            "minimum": 0,
            "maximum": 600,
            "description": "How long to wait, in seconds.",
        },
        "reason": {"type": "string", "description": "Optional reason for waiting."},
    },
    "required": ["duration_seconds"],
}


async def sleep_wait(
    context: ToolRuntimeContext,
    duration_seconds: float,
    reason: str = "",
) -> dict[str, Any]:
    requested = max(0.0, min(float(duration_seconds or 0.0), 600.0))
    started = time.perf_counter()
    woke_for_notification = await _sleep_until_elapsed_or_woken(context, requested)
    elapsed = time.perf_counter() - started
    return {
        "requested_seconds": requested,
        "slept_seconds": elapsed,
        "reason": str(reason or ""),
        "woke_for_notification": woke_for_notification,
    }


async def _sleep_until_elapsed_or_woken(context: ToolRuntimeContext, requested: float) -> bool:
    if requested <= 0:
        return False
    loop = asyncio.get_running_loop()
    deadline = loop.time() + requested
    event = getattr(context, "sleep_wake_event", None)
    check = getattr(context, "sleep_wake_check", None)
    while True:
        if _wake_requested(check):
            return True
        remaining = deadline - loop.time()
        if remaining <= 0:
            return False
        timeout = min(SLEEP_WAKE_POLL_SECONDS, remaining)
        if event is None:
            await asyncio.sleep(timeout)
            continue
        if _event_is_set(event):
            _clear_event(event)
            if check is None or _wake_requested(check):
                return True
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            continue
        _clear_event(event)
        if check is None or _wake_requested(check):
            return True


def _wake_requested(check: Callable[[], bool] | None) -> bool:
    if check is None:
        return False
    try:
        return bool(check())
    except Exception:
        return False


def _event_is_set(event: Any) -> bool:
    is_set = getattr(event, "is_set", None)
    return bool(is_set()) if callable(is_set) else False


def _clear_event(event: Any) -> None:
    clear = getattr(event, "clear", None)
    if callable(clear):
        clear()
