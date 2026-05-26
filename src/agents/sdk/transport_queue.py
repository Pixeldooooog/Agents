from __future__ import annotations

import asyncio


class SDKQueueJsonlTransport:
    """In-memory JSONL transport useful for embedding and tests."""

    def __init__(self) -> None:
        self._inbound: asyncio.Queue[str | bytes | None] = asyncio.Queue()
        self._outbound: asyncio.Queue[str] = asyncio.Queue()
        self.closed = False

    async def send(self, data: str | bytes) -> None:
        await self._inbound.put(data)

    async def close_input(self) -> None:
        await self._inbound.put(None)

    async def read(self) -> str | bytes | None:
        return await self._inbound.get()

    async def write(self, data: str) -> None:
        await self._outbound.put(data)

    async def receive(self) -> str:
        return await self._outbound.get()

    def drain_output(self) -> list[str]:
        lines: list[str] = []
        while True:
            try:
                lines.append(self._outbound.get_nowait())
            except asyncio.QueueEmpty:
                return lines

    async def close(self) -> None:
        self.closed = True
