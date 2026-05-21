from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterable, AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any, Optional, Protocol, Union
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from agents.sdk.structured_io import ndjson_safe_dumps


HYBRID_BATCH_FLUSH_INTERVAL_SECONDS = 0.1
HYBRID_CLOSE_GRACE_SECONDS = 3.0
HYBRID_POST_BASE_DELAY_SECONDS = 0.5
HYBRID_POST_MAX_DELAY_SECONDS = 8.0
HYBRID_POST_MAX_BATCH_SIZE = 500
HYBRID_POST_MAX_QUEUE_SIZE = 100_000
WEBSOCKET_MAX_BUFFER_SIZE = 1000
WEBSOCKET_RECONNECT_BASE_DELAY_SECONDS = 1.0
WEBSOCKET_RECONNECT_MAX_DELAY_SECONDS = 30.0
WEBSOCKET_RECONNECT_GIVE_UP_SECONDS = 600.0
WEBSOCKET_PERMANENT_CLOSE_CODES = {1002, 4001, 4003}
SSE_POST_MAX_RETRIES = 10
SSE_POST_BASE_DELAY_SECONDS = 0.5
SSE_POST_MAX_DELAY_SECONDS = 8.0
SSE_RECONNECT_BASE_DELAY_SECONDS = 1.0
SSE_RECONNECT_MAX_DELAY_SECONDS = 30.0
SSE_RECONNECT_GIVE_UP_SECONDS = 600.0
SSE_LIVENESS_TIMEOUT_SECONDS = 45.0
SSE_PERMANENT_HTTP_STATUS_CODES = {401, 403, 404}
SSE_POST_SUCCESS_STATUS_CODES = {200, 201}


SDKSSEPostHandler = Callable[[str, Mapping[str, str], dict[str, Any]], Awaitable[int]]
SDKSSEReadChunksFactory = Callable[
    [str, Mapping[str, str]],
    AsyncIterable[Union[str, bytes]],
]
SDKSSECloseHandler = Callable[[Optional[int]], Any]
SDKHybridPostHandler = Callable[[str, Mapping[str, str], dict[str, Any]], Awaitable[int]]
SDKBatchDropHandler = Callable[[int, int], Any]
SDKBatchSendHandler = Callable[[list[dict[str, Any]]], Awaitable[None]]
SDKWebSocketConnector = Callable[[str, Mapping[str, str]], Awaitable[Any]]
SDKWebSocketCloseHandler = Callable[[Optional[int]], Any]


class SDKJsonlTransport(Protocol):
    """Bidirectional JSONL transport for SDK structured IO."""

    async def read(self) -> str | bytes | None:
        """Return the next inbound JSONL chunk, or None when input closes."""

    async def write(self, data: str) -> None:
        """Write one or more outbound JSONL lines."""

    async def close(self) -> None:
        """Close the transport."""


@dataclass
class SDKSSEFrame:
    event: str | None = None
    id: str | None = None
    data: str | None = None


class SDKSSELivenessTimeoutError(TimeoutError):
    """Raised internally when an SSE read connection stops producing frames."""


class SDKRetryableBatchError(RuntimeError):
    """Raised by batch senders to retry the current batch."""

    def __init__(self, message: str, *, retry_after_seconds: float | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


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


class SDKSSEJsonlTransport:
    """SSE-read/HTTP-POST JSONL transport for SDK remote IO.

    SSE delivers src-origin-style ``event: client_event`` frames whose JSON
    ``payload`` is the SDK stdin envelope. Outbound SDK stdout JSONL is decoded
    back to JSON objects before posting, matching the remote SSE transport
    shape instead of leaking one-line framing into the HTTP boundary.
    """

    def __init__(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        session_id: str | None = None,
        refresh_headers: Callable[[], Mapping[str, str]] | None = None,
        initial_sequence_num: int | None = None,
        post_url: str | None = None,
        read_chunks: AsyncIterable[str | bytes] | None = None,
        read_chunks_factory: SDKSSEReadChunksFactory | None = None,
        post_message: SDKSSEPostHandler | None = None,
        post_max_retries: int = SSE_POST_MAX_RETRIES,
        post_base_delay_seconds: float = SSE_POST_BASE_DELAY_SECONDS,
        post_max_delay_seconds: float = SSE_POST_MAX_DELAY_SECONDS,
        reconnect: bool | None = None,
        reconnect_base_delay_seconds: float = SSE_RECONNECT_BASE_DELAY_SECONDS,
        reconnect_max_delay_seconds: float = SSE_RECONNECT_MAX_DELAY_SECONDS,
        reconnect_give_up_seconds: float = SSE_RECONNECT_GIVE_UP_SECONDS,
        liveness_timeout_seconds: float | None = SSE_LIVENESS_TIMEOUT_SECONDS,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.url = url
        self.headers = dict(headers or {})
        self.session_id = session_id
        self.refresh_headers = refresh_headers
        self.post_url = post_url or derive_sse_post_url(url)
        self.post_max_retries = post_max_retries
        self.post_base_delay_seconds = post_base_delay_seconds
        self.post_max_delay_seconds = post_max_delay_seconds
        self._read_chunks = read_chunks
        self._read_chunks_factory = read_chunks_factory
        self._post_message = post_message
        self._http_client = None
        self._reader_task: asyncio.Task[None] | None = None
        self._inbound: asyncio.Queue[str | None] = asyncio.Queue()
        self._buffer = ""
        self._seen_sequence_nums: set[int] = set()
        self._last_sequence_num = max(initial_sequence_num or 0, 0)
        self._on_event: Callable[[dict[str, Any]], Any] | None = None
        self._on_close: SDKSSECloseHandler | None = None
        self._reconnect_enabled = (
            reconnect
            if reconnect is not None
            else read_chunks is None or read_chunks_factory is not None
        )
        self._reconnect_base_delay_seconds = reconnect_base_delay_seconds
        self._reconnect_max_delay_seconds = reconnect_max_delay_seconds
        self._reconnect_give_up_seconds = reconnect_give_up_seconds
        self._liveness_timeout_seconds = liveness_timeout_seconds
        self._sleep = sleep
        self._monotonic = monotonic
        self._reconnect_attempts = 0
        self._reconnect_started_at: float | None = None
        self.state = "idle"
        self.closed = False

    @property
    def last_sequence_num(self) -> int:
        return self._last_sequence_num

    def get_last_sequence_num(self) -> int:
        return self._last_sequence_num

    def set_on_event(self, handler: Callable[[dict[str, Any]], Any] | None) -> None:
        self._on_event = handler

    def set_on_close(self, handler: SDKSSECloseHandler | None) -> None:
        self._on_close = handler

    def is_connected_status(self) -> bool:
        return self.state == "connected"

    def is_closed_status(self) -> bool:
        return self.state == "closed"

    async def read(self) -> str | None:
        if self.closed and self._inbound.empty():
            return None
        self._start_reader()
        return await self._inbound.get()

    async def write(self, data: str) -> None:
        for line in data.splitlines():
            if not line.strip():
                continue
            message = json.loads(line)
            if isinstance(message, dict):
                await self._post_with_retry(message)

    async def close(self) -> None:
        self.closed = True
        self.state = "closing"
        if self._reader_task is not None:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
            self._reader_task = None
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    def _start_reader(self) -> None:
        if self._reader_task is None and not self.closed:
            self._reader_task = asyncio.create_task(self._pump_read_connections())

    async def _pump_read_connections(self) -> None:
        try:
            while not self.closed:
                try:
                    await self._read_one_connection()
                except asyncio.CancelledError:
                    raise
                except SDKSSELivenessTimeoutError:
                    if not await self._prepare_reconnect():
                        break
                    continue
                except Exception:
                    if not await self._prepare_reconnect():
                        break
                    continue

                if self.closed or not await self._prepare_reconnect():
                    break
        finally:
            self.closed = True
            if self.state != "closing":
                self.state = "closed"
            await self._inbound.put(None)

    async def _read_one_connection(self) -> None:
        self.state = "reconnecting"
        self._buffer = ""
        self.state = "connected"
        saw_chunk = False
        async for chunk in self._iter_read_chunks():
            if not saw_chunk:
                self._reconnect_attempts = 0
                self._reconnect_started_at = None
                saw_chunk = True
            if isinstance(chunk, bytes):
                self._buffer += chunk.decode("utf-8")
            else:
                self._buffer += chunk
            frames, self._buffer = parse_sse_frames(self._buffer)
            for frame in frames:
                self._track_frame_id(frame)
                payload = self._client_event_payload(frame)
                if payload is not None:
                    await self._inbound.put(ndjson_safe_dumps(payload) + "\n")

    async def _iter_read_chunks(self) -> AsyncIterator[str | bytes]:
        if self._read_chunks_factory is not None:
            chunks = self._read_chunks_factory(self._stream_url(), self._sse_headers())
        elif self._read_chunks is not None:
            chunks = self._read_chunks
            self._read_chunks = None
        else:
            chunks = self._iter_http_read_chunks()
        async for chunk in self._iter_chunks_with_liveness(chunks):
            yield chunk

    async def _iter_http_read_chunks(self) -> AsyncIterator[bytes]:
        client = await self._ensure_http_client()
        async with client.stream("GET", self._stream_url(), headers=self._sse_headers()) as response:
            if response.status_code in SSE_PERMANENT_HTTP_STATUS_CODES:
                self.closed = True
                self._notify_close(response.status_code)
                return
            response.raise_for_status()
            async for chunk in response.aiter_bytes():
                yield chunk

    async def _iter_chunks_with_liveness(
        self,
        chunks: AsyncIterable[str | bytes],
    ) -> AsyncIterator[str | bytes]:
        iterator = chunks.__aiter__()
        while not self.closed:
            try:
                if self._liveness_timeout_seconds is None or self._liveness_timeout_seconds <= 0:
                    chunk = await iterator.__anext__()
                else:
                    chunk = await asyncio.wait_for(
                        iterator.__anext__(),
                        timeout=self._liveness_timeout_seconds,
                    )
            except StopAsyncIteration:
                return
            except asyncio.TimeoutError as exc:
                raise SDKSSELivenessTimeoutError("SSE liveness timeout") from exc
            yield chunk

    async def _prepare_reconnect(self) -> bool:
        if self.closed or not self._reconnect_enabled:
            return False

        self.state = "reconnecting"
        now = self._monotonic()
        if self._reconnect_started_at is None:
            self._reconnect_started_at = now
        elapsed = now - self._reconnect_started_at
        if elapsed >= self._reconnect_give_up_seconds:
            self.closed = True
            self.state = "closed"
            self._notify_close(None)
            return False

        self._reconnect_attempts += 1
        if self.refresh_headers is not None:
            self.headers.update(dict(self.refresh_headers()))
        backoff = self._reconnect_base_delay_seconds * (
            2 ** (self._reconnect_attempts - 1)
        )
        delay = min(backoff, self._reconnect_max_delay_seconds)
        if delay > 0:
            await self._sleep(delay)
        return not self.closed

    def _track_frame_id(self, frame: SDKSSEFrame) -> None:
        if not frame.id:
            return
        try:
            sequence_num = int(frame.id)
        except ValueError:
            return
        self._seen_sequence_nums.add(sequence_num)
        if len(self._seen_sequence_nums) > 1000:
            threshold = self._last_sequence_num - 200
            self._seen_sequence_nums = {
                seq for seq in self._seen_sequence_nums if seq >= threshold
            }
        if sequence_num > self._last_sequence_num:
            self._last_sequence_num = sequence_num

    def _client_event_payload(self, frame: SDKSSEFrame) -> dict[str, Any] | None:
        if frame.event != "client_event" or not frame.data:
            return None
        try:
            event = json.loads(frame.data)
        except json.JSONDecodeError:
            return None
        if not isinstance(event, dict):
            return None
        payload = event.get("payload")
        if not isinstance(payload, dict) or "type" not in payload:
            return None
        if self._on_event is not None:
            self._on_event(event)
        return payload

    async def _post_with_retry(self, message: dict[str, Any]) -> None:
        headers = self._post_headers()
        for attempt in range(1, self.post_max_retries + 1):
            try:
                status = await self._send_post(self.post_url, headers, message)
            except Exception:
                status = None

            if status in SSE_POST_SUCCESS_STATUS_CODES:
                return
            if status is not None and 400 <= status < 500 and status != 429:
                return
            if attempt == self.post_max_retries:
                return

            delay = min(
                self.post_base_delay_seconds * (2 ** (attempt - 1)),
                self.post_max_delay_seconds,
            )
            if delay > 0:
                await asyncio.sleep(delay)

    async def _send_post(self, url: str, headers: Mapping[str, str], message: dict[str, Any]) -> int:
        if self._post_message is not None:
            return await self._post_message(url, headers, message)
        client = await self._ensure_http_client()
        response = await client.post(url, headers=dict(headers), json=message)
        return int(response.status_code)

    async def _ensure_http_client(self) -> Any:
        if self._http_client is None:
            try:
                import httpx
            except ImportError as exc:
                raise RuntimeError("SDKSSEJsonlTransport requires the httpx package") from exc
            self._http_client = httpx.AsyncClient(timeout=None)
        return self._http_client

    def _sse_headers(self) -> dict[str, str]:
        headers = self._fresh_headers()
        headers.setdefault("Accept", "text/event-stream")
        headers.setdefault("anthropic-version", "2023-06-01")
        headers.setdefault("User-Agent", "agents-sdk")
        if self._last_sequence_num > 0:
            headers["Last-Event-ID"] = str(self._last_sequence_num)
        return headers

    def _post_headers(self) -> dict[str, str]:
        headers = self._fresh_headers()
        headers.setdefault("Content-Type", "application/json")
        headers.setdefault("anthropic-version", "2023-06-01")
        headers.setdefault("User-Agent", "agents-sdk")
        return headers

    def _fresh_headers(self) -> dict[str, str]:
        headers = dict(self.headers)
        if self.refresh_headers is not None:
            headers.update(dict(self.refresh_headers()))
        return headers

    def _stream_url(self) -> str:
        if self._last_sequence_num <= 0:
            return self.url
        parts = urlsplit(self.url)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        query["from_sequence_num"] = str(self._last_sequence_num)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))

    def _notify_close(self, close_code: int | None) -> None:
        if self._on_close is not None:
            self._on_close(close_code)


class SDKWebSocketJsonlTransport:
    """WebSocket JSONL transport adapter for SDK remote IO.

    The websocket package is imported lazily so the SDK core remains usable in
    environments that only need local stdio or in-memory transports.
    """

    def __init__(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        refresh_headers: Callable[[], Mapping[str, str]] | None = None,
        connector: SDKWebSocketConnector | None = None,
        auto_reconnect: bool = True,
        max_buffer_size: int = WEBSOCKET_MAX_BUFFER_SIZE,
        reconnect_base_delay_seconds: float = WEBSOCKET_RECONNECT_BASE_DELAY_SECONDS,
        reconnect_max_delay_seconds: float = WEBSOCKET_RECONNECT_MAX_DELAY_SECONDS,
        reconnect_give_up_seconds: float = WEBSOCKET_RECONNECT_GIVE_UP_SECONDS,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.url = url
        self.headers = dict(headers or {})
        self.refresh_headers = refresh_headers
        self._connector = connector
        self._connection = None
        self._message_buffer: list[dict[str, Any]] = []
        self._last_sent_id: str | None = None
        self._on_close: SDKWebSocketCloseHandler | None = None
        self._on_connect: Callable[[], Any] | None = None
        self._auto_reconnect = auto_reconnect
        self._max_buffer_size = max_buffer_size
        self._reconnect_base_delay_seconds = reconnect_base_delay_seconds
        self._reconnect_max_delay_seconds = reconnect_max_delay_seconds
        self._reconnect_give_up_seconds = reconnect_give_up_seconds
        self._sleep = sleep
        self._monotonic = monotonic
        self._reconnect_attempts = 0
        self._reconnect_started_at: float | None = None
        self.state = "idle"
        self.closed = False

    def set_on_close(self, handler: SDKWebSocketCloseHandler | None) -> None:
        self._on_close = handler

    def set_on_connect(self, handler: Callable[[], Any] | None) -> None:
        self._on_connect = handler

    def is_connected_status(self) -> bool:
        return self.state == "connected"

    def is_closed_status(self) -> bool:
        return self.state == "closed"

    def get_state_label(self) -> str:
        return self.state

    async def connect(self) -> None:
        if self._connection is not None or self.closed:
            return
        if self.state not in {"idle", "reconnecting"}:
            return
        self.state = "reconnecting"
        headers = self._connect_headers()
        self._connection = await self._open_connection(headers)
        self.state = "connected"
        self._reconnect_attempts = 0
        self._reconnect_started_at = None
        if self._on_connect is not None:
            self._on_connect()
        await self._replay_buffered_messages(self._server_last_request_id(self._connection))

    async def _open_connection(self, headers: Mapping[str, str]) -> Any:
        if self._connector is not None:
            return await self._connector(self.url, headers)
        try:
            import websockets
        except ImportError as exc:
            raise RuntimeError("SDKWebSocketJsonlTransport requires the websockets package") from exc
        try:
            return await websockets.connect(
                self.url,
                additional_headers=dict(headers) or None,
            )
        except TypeError:
            return await websockets.connect(
                self.url,
                extra_headers=dict(headers) or None,
            )

    async def read(self) -> str | bytes | None:
        while not self.closed:
            await self.connect()
            if self._connection is None:
                return None
            try:
                return await self._connection.recv()
            except Exception as exc:
                close_code = _websocket_close_code(exc)
                if close_code is None and not _is_websocket_closed_error(exc):
                    raise
                if not await self._handle_connection_error(close_code):
                    return None
        return None

    async def write(self, data: str) -> None:
        for line in data.splitlines():
            if not line.strip():
                continue
            message = json.loads(line)
            buffered = self._buffer_message(message)
            if self.state != "connected":
                await self.connect()
                if buffered:
                    continue
            if self.state == "connected":
                sent = await self._send_line(ndjson_safe_dumps(message) + "\n")
                if not sent:
                    await self._handle_connection_error(None)

    async def close(self) -> None:
        self.closed = True
        self.state = "closing"
        if self._connection is not None:
            await _maybe_await(self._connection.close())
            self._connection = None

    def _connect_headers(self) -> dict[str, str]:
        headers = dict(self.headers)
        if self._last_sent_id:
            headers["X-Last-Request-Id"] = self._last_sent_id
        return headers

    def _buffer_message(self, message: Any) -> bool:
        if not isinstance(message, dict):
            return False
        uuid_value = message.get("uuid")
        if not isinstance(uuid_value, str):
            return False
        self._message_buffer.append(message)
        if len(self._message_buffer) > self._max_buffer_size:
            overflow = len(self._message_buffer) - self._max_buffer_size
            del self._message_buffer[:overflow]
        self._last_sent_id = uuid_value
        return True

    async def _send_line(self, line: str) -> bool:
        if self._connection is None or self.state != "connected":
            return False
        try:
            await self._connection.send(line)
            return True
        except Exception:
            return False

    async def _handle_connection_error(self, close_code: int | None = None) -> bool:
        await self._disconnect()
        if self.state in {"closing", "closed"} or self.closed:
            return False

        headers_refreshed = False
        if close_code == 4003 and self.refresh_headers is not None:
            fresh_headers = dict(self.refresh_headers())
            if fresh_headers.get("Authorization") != self.headers.get("Authorization"):
                self.headers.update(fresh_headers)
                headers_refreshed = True

        if (
            close_code is not None
            and close_code in WEBSOCKET_PERMANENT_CLOSE_CODES
            and not headers_refreshed
        ):
            self.closed = True
            self.state = "closed"
            self._notify_close(close_code)
            return False

        if not self._auto_reconnect:
            self.closed = True
            self.state = "closed"
            self._notify_close(close_code)
            return False

        now = self._monotonic()
        if self._reconnect_started_at is None:
            self._reconnect_started_at = now
        elapsed = now - self._reconnect_started_at
        if elapsed >= self._reconnect_give_up_seconds:
            self.closed = True
            self.state = "closed"
            self._notify_close(close_code)
            return False

        if not headers_refreshed and self.refresh_headers is not None:
            self.headers.update(dict(self.refresh_headers()))
        self._reconnect_attempts += 1
        self.state = "reconnecting"
        backoff = self._reconnect_base_delay_seconds * (
            2 ** (self._reconnect_attempts - 1)
        )
        delay = min(backoff, self._reconnect_max_delay_seconds)
        if delay > 0:
            await self._sleep(delay)
        return True

    async def _disconnect(self) -> None:
        if self._connection is not None:
            connection = self._connection
            self._connection = None
            close = getattr(connection, "close", None)
            if close is not None:
                await _maybe_await(close())

    async def _replay_buffered_messages(self, last_request_id: str | None) -> None:
        if not self._message_buffer:
            return
        start_index = 0
        if last_request_id:
            for index, message in enumerate(self._message_buffer):
                if message.get("uuid") == last_request_id:
                    start_index = index + 1
                    self._message_buffer = self._message_buffer[start_index:]
                    if not self._message_buffer:
                        self._last_sent_id = None
                    break
        for message in list(self._message_buffer):
            if not await self._send_line(ndjson_safe_dumps(message) + "\n"):
                break

    def _server_last_request_id(self, connection: Any) -> str | None:
        headers = (
            getattr(connection, "response_headers", None)
            or getattr(connection, "headers", None)
            or getattr(getattr(connection, "response", None), "headers", None)
        )
        if not headers:
            return None
        for key in ("x-last-request-id", "X-Last-Request-Id"):
            try:
                value = headers.get(key)
            except AttributeError:
                value = None
            if isinstance(value, str):
                return value
        return None

    def _notify_close(self, close_code: int | None) -> None:
        if self._on_close is not None:
            self._on_close(close_code)


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


def parse_sse_frames(buffer: str) -> tuple[list[SDKSSEFrame], str]:
    """Incrementally parse Server-Sent Events frames from a text buffer."""

    frames: list[SDKSSEFrame] = []
    pos = 0

    while True:
        delimiter = _find_sse_frame_delimiter(buffer, pos)
        if delimiter is None:
            break
        idx, delimiter_length = delimiter
        raw_frame = buffer[pos:idx]
        pos = idx + delimiter_length
        if not raw_frame.strip():
            continue

        frame = SDKSSEFrame()
        is_comment = False
        for line in raw_frame.splitlines():
            if line.startswith(":"):
                is_comment = True
                continue

            colon_idx = line.find(":")
            if colon_idx == -1:
                continue
            field = line[:colon_idx]
            value = line[colon_idx + 1 :]
            if value.startswith(" "):
                value = value[1:]

            if field == "event":
                frame.event = value
            elif field == "id":
                frame.id = value
            elif field == "data":
                frame.data = f"{frame.data}\n{value}" if frame.data else value

        if frame.data or is_comment:
            frames.append(frame)

    return frames, buffer[pos:]


def derive_sse_stream_url(url: str) -> str:
    """Derive the CCR-style SSE stream URL from a websocket/session URL."""

    parts = urlsplit(url)
    scheme = parts.scheme
    if scheme == "wss":
        scheme = "https"
    elif scheme == "ws":
        scheme = "http"
    path = parts.path.rstrip("/") + "/worker/events/stream"
    return urlunsplit((scheme, parts.netloc, path, parts.query, parts.fragment))


def derive_sse_post_url(sse_url: str) -> str:
    """Derive the HTTP POST event endpoint from an SSE stream URL."""

    parts = urlsplit(sse_url)
    path = parts.path
    if path.endswith("/stream"):
        path = path[: -len("/stream")]
    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))


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


def _find_sse_frame_delimiter(buffer: str, start: int) -> tuple[int, int] | None:
    candidates = []
    for delimiter in ("\r\n\r\n", "\n\n", "\r\r"):
        idx = buffer.find(delimiter, start)
        if idx != -1:
            candidates.append((idx, len(delimiter)))
    return min(candidates, key=lambda item: item[0]) if candidates else None


def _websocket_close_code(exc: Exception) -> int | None:
    code = getattr(exc, "code", None)
    if isinstance(code, int):
        return code
    rcvd = getattr(exc, "rcvd", None)
    rcvd_code = getattr(rcvd, "code", None)
    return rcvd_code if isinstance(rcvd_code, int) else None


def _is_websocket_closed_error(exc: Exception) -> bool:
    return (
        exc.__class__.__name__.startswith("ConnectionClosed")
        or _websocket_close_code(exc) is not None
    )


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value
