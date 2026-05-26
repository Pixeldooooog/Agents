from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable, Mapping
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from agents.sdk.transport_types import (
    SDKBatchDropHandler,
    SDKBatchSendHandler,
    SDKHybridPostHandler,
    SDKJsonlTransport,
    SDKRetryableBatchError,
)
from agents.sdk.transport_websocket import SDKWebSocketJsonlTransport


HYBRID_BATCH_FLUSH_INTERVAL_SECONDS = 0.1
HYBRID_CLOSE_GRACE_SECONDS = 3.0
HYBRID_POST_BASE_DELAY_SECONDS = 0.5
HYBRID_POST_MAX_DELAY_SECONDS = 8.0
HYBRID_POST_MAX_BATCH_SIZE = 500
HYBRID_POST_MAX_QUEUE_SIZE = 100_000


class SDKHybridJsonlTransport:
    """WebSocket-read/HTTP-POST-write JSONL transport for SDK remote IO."""

    def __init__(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        refresh_headers: Callable[[], Mapping[str, str]] | None = None,
        reader: SDKJsonlTransport | None = None,
        post_url: str | None = None,
        post_message: SDKHybridPostHandler | None = None,
        stream_event_flush_interval_seconds: float = HYBRID_BATCH_FLUSH_INTERVAL_SECONDS,
        max_batch_size: int = HYBRID_POST_MAX_BATCH_SIZE,
        max_queue_size: int = HYBRID_POST_MAX_QUEUE_SIZE,
        post_base_delay_seconds: float = HYBRID_POST_BASE_DELAY_SECONDS,
        post_max_delay_seconds: float = HYBRID_POST_MAX_DELAY_SECONDS,
        max_consecutive_failures: int | None = None,
        on_batch_dropped: SDKBatchDropHandler | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        close_grace_seconds: float = HYBRID_CLOSE_GRACE_SECONDS,
    ) -> None:
        self.url = url
        self.headers = dict(headers or {})
        self.refresh_headers = refresh_headers
        self.post_url = post_url or derive_hybrid_post_url(url)
        self.stream_event_flush_interval_seconds = stream_event_flush_interval_seconds
        self.close_grace_seconds = close_grace_seconds
        self._reader = reader or SDKWebSocketJsonlTransport(url, headers=self.headers)
        self._post_message = post_message
        self._http_client = None
        self._sleep = sleep
        self._stream_event_buffer: list[dict[str, Any]] = []
        self._stream_event_task: asyncio.Task[None] | None = None
        self._uploader = SDKSerialBatchUploader(
            max_batch_size=max_batch_size,
            max_queue_size=max_queue_size,
            base_delay_seconds=post_base_delay_seconds,
            max_delay_seconds=post_max_delay_seconds,
            send=self._post_once,
            max_consecutive_failures=max_consecutive_failures,
            on_batch_dropped=on_batch_dropped,
            sleep=sleep,
        )
        self.closed = False

    @property
    def dropped_batch_count(self) -> int:
        return self._uploader.dropped_batch_count

    async def read(self) -> str | bytes | None:
        return await self._reader.read()

    async def write(self, data: str) -> None:
        for line in data.splitlines():
            if not line.strip():
                continue
            message = json.loads(line)
            if isinstance(message, dict):
                await self._write_message(message)

    async def write_batch(self, messages: list[dict[str, Any]]) -> None:
        await self._uploader.enqueue([*self._take_stream_events(), *messages])
        await self._uploader.flush()

    async def flush(self) -> None:
        await self._uploader.enqueue(self._take_stream_events())
        await self._uploader.flush()

    async def close(self) -> None:
        self.closed = True
        self._take_stream_events()
        try:
            if self.close_grace_seconds > 0:
                await asyncio.wait_for(self._uploader.flush(), timeout=self.close_grace_seconds)
            else:
                await self._uploader.flush()
        except asyncio.TimeoutError:
            pass
        self._uploader.close()
        close = getattr(self._reader, "close", None)
        if close is not None:
            await close()
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    async def _write_message(self, message: dict[str, Any]) -> None:
        if message.get("type") == "stream_event":
            self._stream_event_buffer.append(message)
            if self._stream_event_task is None:
                self._stream_event_task = asyncio.create_task(self._flush_stream_events_later())
            return
        await self._uploader.enqueue([*self._take_stream_events(), message])
        await self._uploader.flush()

    async def _flush_stream_events_later(self) -> None:
        try:
            if self.stream_event_flush_interval_seconds > 0:
                await self._sleep(self.stream_event_flush_interval_seconds)
            self._stream_event_task = None
            await self._uploader.enqueue(self._take_stream_events(cancel_timer=False))
        except asyncio.CancelledError:
            pass

    def _take_stream_events(self, *, cancel_timer: bool = True) -> list[dict[str, Any]]:
        if cancel_timer and self._stream_event_task is not None:
            self._stream_event_task.cancel()
            self._stream_event_task = None
        buffered = self._stream_event_buffer
        self._stream_event_buffer = []
        return buffered

    async def _post_once(self, events: list[dict[str, Any]]) -> None:
        if not events:
            return
        headers = self._post_headers()
        status = await self._send_post(
            self.post_url,
            headers,
            {"events": events},
        )
        if 200 <= status < 300:
            return
        if 400 <= status < 500 and status != 429:
            return
        raise SDKRetryableBatchError(f"Hybrid POST failed with {status}")

    async def _send_post(self, url: str, headers: Mapping[str, str], body: dict[str, Any]) -> int:
        if self._post_message is not None:
            return await self._post_message(url, headers, body)
        client = await self._ensure_http_client()
        response = await client.post(url, headers=dict(headers), json=body)
        return int(response.status_code)

    async def _ensure_http_client(self) -> Any:
        if self._http_client is None:
            try:
                import httpx
            except ImportError as exc:
                raise RuntimeError("SDKHybridJsonlTransport requires the httpx package") from exc
            self._http_client = httpx.AsyncClient(timeout=15.0)
        return self._http_client

    def _post_headers(self) -> dict[str, str]:
        headers = dict(self.headers)
        if self.refresh_headers is not None:
            headers.update(dict(self.refresh_headers()))
        headers.setdefault("Content-Type", "application/json")
        return headers


class SDKSerialBatchUploader:
    """Ordered batch uploader with one in-flight send and retry backoff."""

    def __init__(
        self,
        *,
        max_batch_size: int,
        max_queue_size: int,
        base_delay_seconds: float,
        max_delay_seconds: float,
        send: SDKBatchSendHandler,
        max_consecutive_failures: int | None = None,
        on_batch_dropped: SDKBatchDropHandler | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.max_batch_size = max_batch_size
        self.max_queue_size = max_queue_size
        self.base_delay_seconds = base_delay_seconds
        self.max_delay_seconds = max_delay_seconds
        self.send = send
        self.max_consecutive_failures = max_consecutive_failures
        self.on_batch_dropped = on_batch_dropped
        self._sleep = sleep
        self._pending: list[dict[str, Any]] = []
        self._draining = False
        self._closed = False
        self._backpressure_waiters: list[asyncio.Future[None]] = []
        self._flush_waiters: list[asyncio.Future[None]] = []
        self._dropped_batches = 0

    @property
    def dropped_batch_count(self) -> int:
        return self._dropped_batches

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    async def enqueue(self, events: list[dict[str, Any]]) -> None:
        if self._closed or not events:
            return
        while len(self._pending) + len(events) > self.max_queue_size and not self._closed:
            waiter = asyncio.get_running_loop().create_future()
            self._backpressure_waiters.append(waiter)
            await waiter
        if self._closed:
            return
        self._pending.extend(events)
        self._start_drain()

    async def flush(self) -> None:
        if not self._pending and not self._draining:
            return
        self._start_drain()
        waiter = asyncio.get_running_loop().create_future()
        self._flush_waiters.append(waiter)
        await waiter

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._pending = []
        self._release_waiters(self._backpressure_waiters)
        self._release_waiters(self._flush_waiters)

    def _start_drain(self) -> None:
        if not self._draining and not self._closed:
            asyncio.create_task(self._drain())

    async def _drain(self) -> None:
        if self._draining or self._closed:
            return
        self._draining = True
        failures = 0
        try:
            while self._pending and not self._closed:
                batch = self._take_batch()
                if not batch:
                    continue
                try:
                    await self.send(batch)
                    failures = 0
                except Exception as exc:
                    failures += 1
                    if (
                        self.max_consecutive_failures is not None
                        and failures >= self.max_consecutive_failures
                    ):
                        self._dropped_batches += 1
                        if self.on_batch_dropped is not None:
                            self.on_batch_dropped(len(batch), failures)
                        failures = 0
                        self._release_waiters(self._backpressure_waiters)
                        continue
                    self._pending = [*batch, *self._pending]
                    await self._sleep(self._retry_delay(failures, exc))
                    continue
                self._release_waiters(self._backpressure_waiters)
        finally:
            self._draining = False
            if not self._pending:
                self._release_waiters(self._flush_waiters)

    def _take_batch(self) -> list[dict[str, Any]]:
        batch = self._pending[: self.max_batch_size]
        del self._pending[: len(batch)]
        return batch

    def _retry_delay(self, failures: int, exc: Exception) -> float:
        retry_after = (
            exc.retry_after_seconds
            if isinstance(exc, SDKRetryableBatchError)
            else None
        )
        if retry_after is not None:
            return max(
                self.base_delay_seconds,
                min(retry_after, self.max_delay_seconds),
            )
        return min(
            self.base_delay_seconds * (2 ** (failures - 1)),
            self.max_delay_seconds,
        )

    @staticmethod
    def _release_waiters(waiters: list[asyncio.Future[None]]) -> None:
        pending = list(waiters)
        waiters.clear()
        for waiter in pending:
            if not waiter.done():
                waiter.set_result(None)


def derive_hybrid_post_url(ws_url: str) -> str:
    """Derive the HTTP POST event endpoint from a hybrid websocket URL."""

    parts = urlsplit(ws_url)
    scheme = (
        "https"
        if parts.scheme == "wss"
        else "http"
        if parts.scheme == "ws"
        else parts.scheme
    )
    path = parts.path.replace("/ws/", "/session/", 1)
    if not path.endswith("/events"):
        path = f"{path.rstrip('/')}/events"
    return urlunsplit((scheme, parts.netloc, path, parts.query, parts.fragment))
