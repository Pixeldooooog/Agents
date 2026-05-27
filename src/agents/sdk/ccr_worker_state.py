from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from agents.sdk.ccr_types import CCR_WORKER_STATE_BASE_DELAY_SECONDS, CCR_WORKER_STATE_MAX_DELAY_SECONDS


class SDKWorkerStateUploader:
    """Coalescing uploader for CCR worker state patches."""

    def __init__(
        self,
        send: Callable[[dict[str, Any]], Awaitable[bool]],
        *,
        base_delay_seconds: float = CCR_WORKER_STATE_BASE_DELAY_SECONDS,
        max_delay_seconds: float = CCR_WORKER_STATE_MAX_DELAY_SECONDS,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._send = send
        self._base_delay_seconds = base_delay_seconds
        self._max_delay_seconds = max_delay_seconds
        self._sleep = sleep
        self._pending: dict[str, Any] | None = None
        self._drain_task: asyncio.Task[None] | None = None
        self._closed = False

    @property
    def pending_count(self) -> int:
        return 0 if self._pending is None else 1

    def enqueue(self, patch: dict[str, Any]) -> None:
        if self._closed:
            return
        self._pending = coalesce_worker_state_patches(self._pending or {}, patch)
        if self._drain_task is None or self._drain_task.done():
            self._drain_task = asyncio.create_task(self._drain())

    async def flush(self) -> None:
        if self._drain_task is not None:
            await self._drain_task

    def close(self) -> None:
        self._closed = True
        self._pending = None
        if self._drain_task is not None and not self._drain_task.done():
            self._drain_task.cancel()

    async def _drain(self) -> None:
        try:
            while self._pending is not None and not self._closed:
                current = self._pending
                self._pending = None
                failures = 0
                while not self._closed:
                    if await self._send(current):
                        break
                    failures += 1
                    await self._sleep(
                        min(
                            self._base_delay_seconds * (2 ** (failures - 1)),
                            self._max_delay_seconds,
                        )
                    )
                    if self._pending is not None:
                        current = coalesce_worker_state_patches(current, self._pending)
                        self._pending = None
        except asyncio.CancelledError:
            pass


def coalesce_worker_state_patches(
    base: dict[str, Any],
    overlay: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overlay.items():
        if (
            key in {"external_metadata", "internal_metadata"}
            and isinstance(merged.get(key), dict)
            and isinstance(value, dict)
        ):
            merged[key] = {**merged[key], **value}
        else:
            merged[key] = value
    return merged
