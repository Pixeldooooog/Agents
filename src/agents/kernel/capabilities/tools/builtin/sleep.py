from __future__ import annotations

import asyncio
import time
from typing import Any

from agents.kernel.capabilities.tools.context import ToolRuntimeContext


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
    del context
    requested = max(0.0, min(float(duration_seconds or 0.0), 600.0))
    started = time.perf_counter()
    await asyncio.sleep(requested)
    elapsed = time.perf_counter() - started
    return {
        "requested_seconds": requested,
        "slept_seconds": elapsed,
        "reason": str(reason or ""),
    }
