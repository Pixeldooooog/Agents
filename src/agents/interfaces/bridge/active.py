from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any


BridgeWriter = Callable[[dict[str, Any]], None]


def start_active_task(state: Any, run_id: str, coroutine: Awaitable[Any], write: BridgeWriter) -> None:
    state.active_run_id = run_id
    state.active_task = asyncio.create_task(_run_active_task(state, coroutine, write))


async def _run_active_task(state: Any, coroutine: Awaitable[Any], write: BridgeWriter) -> None:
    try:
        await coroutine
    except asyncio.CancelledError:
        pass
    except Exception as exc:  # noqa: BLE001 - background tasks must not leak unobserved exceptions.
        run_id = str(getattr(state, "active_run_id", "") or "")
        write({"type": "error", "message": str(exc)})
        if run_id:
            write({"type": "turn_finished", "status": "error", "run_id": run_id})
    finally:
        task = asyncio.current_task()
        if state.active_task is task:
            state.active_task = None
            state.active_run_id = ""


def active_task_running(state: Any) -> bool:
    return state.active_task is not None and not state.active_task.done()


async def cancel_active_run(state: Any, write: BridgeWriter, quiet: bool = False, reason: str = "") -> None:
    task = state.active_task
    if task is None or task.done():
        state.active_task = None
        state.active_run_id = ""
        if not quiet:
            write({"type": "notice", "message": "nothing to cancel"})
        return
    if reason:
        task.cancel(reason)
    else:
        task.cancel()
    await task
