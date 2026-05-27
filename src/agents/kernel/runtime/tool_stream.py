from __future__ import annotations

import asyncio
from typing import AsyncIterable, Awaitable, Callable, TypeVar

from agents.kernel.schema import RuntimeEvent

OutcomeT = TypeVar("OutcomeT")


async def stream_tool_execution(
    execute: Callable[[Callable[[RuntimeEvent], None]], Awaitable[OutcomeT]],
    outcome_holder: dict[str, OutcomeT],
) -> AsyncIterable[RuntimeEvent]:
    queue: asyncio.Queue[RuntimeEvent] = asyncio.Queue()

    def enqueue(event: RuntimeEvent) -> None:
        queue.put_nowait(event)

    task = asyncio.create_task(execute(enqueue))
    next_event: asyncio.Task[RuntimeEvent] | None = None
    try:
        while True:
            next_event = asyncio.create_task(queue.get())
            done, _ = await asyncio.wait({task, next_event}, return_when=asyncio.FIRST_COMPLETED)
            if next_event in done:
                yield next_event.result()
            else:
                next_event.cancel()
            if task in done:
                break
    except asyncio.CancelledError:
        if next_event is not None and not next_event.done():
            next_event.cancel()
        if not task.done():
            task.cancel()
        outcome_holder["outcome"] = await task
        while not queue.empty():
            yield queue.get_nowait()
        return
    while not queue.empty():
        yield queue.get_nowait()
    outcome_holder["outcome"] = await task
