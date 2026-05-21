from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Protocol


class SDKJsonlTransport(Protocol):
    """Bidirectional JSONL transport for SDK structured IO."""

    async def read(self) -> str | bytes | None:
        """Return the next inbound JSONL chunk, or None when input closes."""

    async def write(self, data: str) -> None:
        """Write one or more outbound JSONL lines."""

    async def close(self) -> None:
        """Close the transport."""


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


class SDKWebSocketJsonlTransport:
    """WebSocket JSONL transport adapter for SDK remote IO.

    The websocket package is imported lazily so the SDK core remains usable in
    environments that only need local stdio or in-memory transports.
    """

    def __init__(self, url: str, *, headers: Mapping[str, str] | None = None) -> None:
        self.url = url
        self.headers = dict(headers or {})
        self._connection = None
        self.closed = False

    async def connect(self) -> None:
        if self._connection is not None:
            return
        try:
            import websockets
        except ImportError as exc:
            raise RuntimeError("SDKWebSocketJsonlTransport requires the websockets package") from exc
        try:
            self._connection = await websockets.connect(
                self.url,
                additional_headers=self.headers or None,
            )
        except TypeError:
            self._connection = await websockets.connect(
                self.url,
                extra_headers=self.headers or None,
            )

    async def read(self) -> str | bytes | None:
        await self.connect()
        try:
            return await self._connection.recv()
        except Exception as exc:
            if exc.__class__.__name__.startswith("ConnectionClosed"):
                return None
            raise

    async def write(self, data: str) -> None:
        await self.connect()
        await self._connection.send(data)

    async def close(self) -> None:
        self.closed = True
        if self._connection is not None:
            await self._connection.close()
            self._connection = None
