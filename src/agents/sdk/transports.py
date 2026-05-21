from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterable, AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from agents.sdk.structured_io import ndjson_safe_dumps


SSE_POST_MAX_RETRIES = 10
SSE_POST_BASE_DELAY_SECONDS = 0.5
SSE_POST_MAX_DELAY_SECONDS = 8.0
SSE_PERMANENT_HTTP_STATUS_CODES = {401, 403, 404}
SSE_POST_SUCCESS_STATUS_CODES = {200, 201}


SDKSSEPostHandler = Callable[[str, Mapping[str, str], dict[str, Any]], Awaitable[int]]


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
        post_message: SDKSSEPostHandler | None = None,
        post_max_retries: int = SSE_POST_MAX_RETRIES,
        post_base_delay_seconds: float = SSE_POST_BASE_DELAY_SECONDS,
        post_max_delay_seconds: float = SSE_POST_MAX_DELAY_SECONDS,
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
        self._post_message = post_message
        self._http_client = None
        self._reader_task: asyncio.Task[None] | None = None
        self._inbound: asyncio.Queue[str | None] = asyncio.Queue()
        self._buffer = ""
        self._seen_sequence_nums: set[int] = set()
        self._last_sequence_num = max(initial_sequence_num or 0, 0)
        self._on_event: Callable[[dict[str, Any]], Any] | None = None
        self.closed = False

    @property
    def last_sequence_num(self) -> int:
        return self._last_sequence_num

    def get_last_sequence_num(self) -> int:
        return self._last_sequence_num

    def set_on_event(self, handler: Callable[[dict[str, Any]], Any] | None) -> None:
        self._on_event = handler

    async def read(self) -> str | None:
        if self.closed and self._reader_task is None:
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
            self._reader_task = asyncio.create_task(self._pump_read_chunks())

    async def _pump_read_chunks(self) -> None:
        try:
            async for chunk in self._iter_read_chunks():
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
        finally:
            await self._inbound.put(None)

    async def _iter_read_chunks(self) -> AsyncIterator[str | bytes]:
        if self._read_chunks is not None:
            async for chunk in self._read_chunks:
                yield chunk
            return
        async for chunk in self._iter_http_read_chunks():
            yield chunk

    async def _iter_http_read_chunks(self) -> AsyncIterator[bytes]:
        client = await self._ensure_http_client()
        async with client.stream("GET", self._stream_url(), headers=self._sse_headers()) as response:
            if response.status_code in SSE_PERMANENT_HTTP_STATUS_CODES:
                self.closed = True
                return
            response.raise_for_status()
            async for chunk in response.aiter_bytes():
                yield chunk

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


def _find_sse_frame_delimiter(buffer: str, start: int) -> tuple[int, int] | None:
    candidates = []
    for delimiter in ("\r\n\r\n", "\n\n", "\r\r"):
        idx = buffer.find(delimiter, start)
        if idx != -1:
            candidates.append((idx, len(delimiter)))
    return min(candidates, key=lambda item: item[0]) if candidates else None
