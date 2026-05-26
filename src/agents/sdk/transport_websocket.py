from __future__ import annotations

import asyncio
import inspect
import json
import os
import ssl
import time
from collections.abc import Awaitable, Callable, Mapping
from typing import Any
from urllib.parse import urlsplit

from agents.sdk.structured_io import ndjson_safe_dumps
from agents.sdk.transport_types import (
    SDKWebSocketCloseHandler,
    SDKWebSocketConnectOptions,
    SDKWebSocketConnector,
)


WEBSOCKET_MAX_BUFFER_SIZE = 1000
WEBSOCKET_RECONNECT_BASE_DELAY_SECONDS = 1.0
WEBSOCKET_RECONNECT_MAX_DELAY_SECONDS = 30.0
WEBSOCKET_RECONNECT_GIVE_UP_SECONDS = 600.0
WEBSOCKET_PERMANENT_CLOSE_CODES = {1002, 4001, 4003}
WEBSOCKET_PING_INTERVAL_SECONDS = 10.0
WEBSOCKET_PING_TIMEOUT_SECONDS = 10.0
WEBSOCKET_KEEPALIVE_INTERVAL_SECONDS = 300.0
WEBSOCKET_SLEEP_DETECTION_THRESHOLD_SECONDS = WEBSOCKET_RECONNECT_MAX_DELAY_SECONDS * 2
WEBSOCKET_KEEP_ALIVE_FRAME = '{"type":"keep_alive"}\n'


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
        proxy_url: str | None = None,
        no_proxy: str | None = None,
        trust_env_proxy: bool = True,
        ssl_context: Any | None = None,
        tls_ca_file: str | None = None,
        tls_cert_file: str | None = None,
        tls_key_file: str | None = None,
        tls_key_password: str | None = None,
        connect_options: Mapping[str, Any] | None = None,
        env: Mapping[str, str | None] | None = None,
        auto_reconnect: bool = True,
        max_buffer_size: int = WEBSOCKET_MAX_BUFFER_SIZE,
        reconnect_base_delay_seconds: float = WEBSOCKET_RECONNECT_BASE_DELAY_SECONDS,
        reconnect_max_delay_seconds: float = WEBSOCKET_RECONNECT_MAX_DELAY_SECONDS,
        reconnect_give_up_seconds: float = WEBSOCKET_RECONNECT_GIVE_UP_SECONDS,
        ping_interval_seconds: float | None = WEBSOCKET_PING_INTERVAL_SECONDS,
        ping_timeout_seconds: float = WEBSOCKET_PING_TIMEOUT_SECONDS,
        keepalive_interval_seconds: float | None = WEBSOCKET_KEEPALIVE_INTERVAL_SECONDS,
        sleep_detection_threshold_seconds: float = WEBSOCKET_SLEEP_DETECTION_THRESHOLD_SECONDS,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.url = url
        self.headers = dict(headers or {})
        self.refresh_headers = refresh_headers
        self._connector = connector
        self._proxy_url = proxy_url
        self._no_proxy = no_proxy
        self._trust_env_proxy = trust_env_proxy
        self._ssl_context = ssl_context
        self._tls_ca_file = tls_ca_file
        self._tls_cert_file = tls_cert_file
        self._tls_key_file = tls_key_file
        self._tls_key_password = tls_key_password
        self._connect_options = dict(connect_options or {})
        self._env = env
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
        self._ping_interval_seconds = ping_interval_seconds
        self._ping_timeout_seconds = ping_timeout_seconds
        self._keepalive_interval_seconds = keepalive_interval_seconds
        self._sleep_detection_threshold_seconds = sleep_detection_threshold_seconds
        self._sleep = sleep
        self._monotonic = monotonic
        self._reconnect_attempts = 0
        self._reconnect_started_at: float | None = None
        self._ping_task: asyncio.Task[None] | None = None
        self._keepalive_task: asyncio.Task[None] | None = None
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
        self._start_health_tasks()

    async def _open_connection(self, headers: Mapping[str, str]) -> Any:
        options = self._connection_options(headers)
        if self._connector is not None:
            return await self._call_connector(headers, options)
        try:
            import websockets
        except ImportError as exc:
            raise RuntimeError("SDKWebSocketJsonlTransport requires the websockets package") from exc
        connect_kwargs = self._websocket_connect_kwargs(options)
        try:
            return await websockets.connect(
                self.url,
                additional_headers=dict(headers) or None,
                **connect_kwargs,
            )
        except TypeError:
            return await websockets.connect(
                self.url,
                extra_headers=dict(headers) or None,
                **connect_kwargs,
            )

    async def _call_connector(
        self,
        headers: Mapping[str, str],
        options: SDKWebSocketConnectOptions,
    ) -> Any:
        if _callable_accepts_options(self._connector):
            return await self._connector(self.url, headers, options)
        return await self._connector(self.url, headers)

    def _connection_options(self, headers: Mapping[str, str]) -> SDKWebSocketConnectOptions:
        return SDKWebSocketConnectOptions(
            headers=dict(headers),
            proxy=self._resolved_proxy_url(),
            ssl_context=self._resolved_ssl_context(),
            raw_options=dict(self._connect_options),
        )

    def _websocket_connect_kwargs(
        self,
        options: SDKWebSocketConnectOptions,
    ) -> dict[str, Any]:
        kwargs = dict(options.raw_options)
        if options.proxy is not None:
            kwargs.setdefault("proxy", options.proxy)
        if options.ssl_context is not None:
            kwargs.setdefault("ssl", options.ssl_context)
        return kwargs

    def _resolved_proxy_url(self) -> str | None:
        proxy = self._proxy_url
        if proxy is None and self._trust_env_proxy:
            proxy = _env_proxy_url(self._effective_env())
        if not proxy:
            return None
        no_proxy = self._no_proxy
        if no_proxy is None:
            no_proxy = _env_no_proxy(self._effective_env())
        if _should_bypass_proxy(self.url, no_proxy):
            return None
        return proxy

    def _resolved_ssl_context(self) -> Any | None:
        if self._ssl_context is not None:
            return self._ssl_context
        ca_file = self._tls_ca_file or _first_env(
            self._effective_env(),
            "AGENTS_SDK_CA_CERTS",
            "NODE_EXTRA_CA_CERTS",
        )
        cert_file = self._tls_cert_file or _first_env(
            self._effective_env(),
            "AGENTS_SDK_CLIENT_CERT",
            "CLAUDE_CODE_CLIENT_CERT",
        )
        key_file = self._tls_key_file or _first_env(
            self._effective_env(),
            "AGENTS_SDK_CLIENT_KEY",
            "CLAUDE_CODE_CLIENT_KEY",
        )
        password = self._tls_key_password or _first_env(
            self._effective_env(),
            "AGENTS_SDK_CLIENT_KEY_PASSPHRASE",
            "CLAUDE_CODE_CLIENT_KEY_PASSPHRASE",
        )
        if not ca_file and not cert_file and not key_file:
            return None
        context = ssl.create_default_context(cafile=ca_file)
        if cert_file or key_file:
            context.load_cert_chain(
                certfile=cert_file,
                keyfile=key_file,
                password=password,
            )
        return context

    def _effective_env(self) -> Mapping[str, str | None]:
        return self._env if self._env is not None else os.environ

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
        self._stop_health_tasks()
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
        self._stop_health_tasks()
        if self._connection is not None:
            connection = self._connection
            self._connection = None
            close = getattr(connection, "close", None)
            if close is not None:
                await _maybe_await(close())

    def _start_health_tasks(self) -> None:
        self._stop_health_tasks()
        if self._ping_interval_seconds is not None and self._ping_interval_seconds > 0:
            self._ping_task = asyncio.create_task(self._ping_loop())
        if (
            self._keepalive_interval_seconds is not None
            and self._keepalive_interval_seconds > 0
        ):
            self._keepalive_task = asyncio.create_task(self._keepalive_loop())

    def _stop_health_tasks(self) -> None:
        current = asyncio.current_task()
        for attr in ("_ping_task", "_keepalive_task"):
            task = getattr(self, attr)
            if task is None:
                continue
            if task is not current and not task.done():
                task.cancel()
            if task is not current:
                setattr(self, attr, None)

    async def _ping_loop(self) -> None:
        last_tick = self._monotonic()
        try:
            while not self.closed:
                await asyncio.sleep(self._ping_interval_seconds or 0)
                if self.state != "connected" or self._connection is None:
                    continue
                now = self._monotonic()
                gap = now - last_tick
                last_tick = now
                if gap > self._sleep_detection_threshold_seconds:
                    if await self._handle_connection_error(None):
                        await self.connect()
                    return
                try:
                    await self._ping_connection()
                except Exception:
                    if await self._handle_connection_error(None):
                        await self.connect()
                    return
        except asyncio.CancelledError:
            pass
        finally:
            if asyncio.current_task() is self._ping_task:
                self._ping_task = None

    async def _keepalive_loop(self) -> None:
        try:
            while not self.closed:
                await asyncio.sleep(self._keepalive_interval_seconds or 0)
                if self.state != "connected":
                    continue
                if not await self._send_line(WEBSOCKET_KEEP_ALIVE_FRAME):
                    if await self._handle_connection_error(None):
                        await self.connect()
                    return
        except asyncio.CancelledError:
            pass
        finally:
            if asyncio.current_task() is self._keepalive_task:
                self._keepalive_task = None

    async def _ping_connection(self) -> None:
        if self._connection is None:
            return
        ping = getattr(self._connection, "ping", None)
        if ping is None:
            return
        result = await _maybe_await(ping())
        if hasattr(result, "__await__"):
            await asyncio.wait_for(result, timeout=self._ping_timeout_seconds)

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


def _callable_accepts_options(fn: Any) -> bool:
    try:
        signature = inspect.signature(fn)
    except (TypeError, ValueError):
        return False
    positional = 0
    for parameter in signature.parameters.values():
        if parameter.kind == inspect.Parameter.VAR_POSITIONAL:
            return True
        if parameter.kind in {
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        }:
            positional += 1
    return positional >= 3


def _env_proxy_url(env: Mapping[str, str | None]) -> str | None:
    return _first_env(env, "https_proxy", "HTTPS_PROXY", "http_proxy", "HTTP_PROXY")


def _env_no_proxy(env: Mapping[str, str | None]) -> str | None:
    return _first_env(env, "no_proxy", "NO_PROXY")


def _first_env(env: Mapping[str, str | None], *names: str) -> str | None:
    for name in names:
        value = env.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _should_bypass_proxy(url: str, no_proxy: str | None) -> bool:
    if not no_proxy:
        return False
    if no_proxy.strip() == "*":
        return True
    parts = urlsplit(url)
    hostname = (parts.hostname or "").lower()
    if not hostname:
        return False
    port = str(parts.port or (443 if parts.scheme in {"wss", "https"} else 80))
    host_with_port = f"{hostname}:{port}"
    for raw_pattern in no_proxy.replace(",", " ").split():
        pattern = raw_pattern.strip().lower()
        if not pattern:
            continue
        if ":" in pattern:
            if host_with_port == pattern:
                return True
            continue
        if pattern.startswith("."):
            if hostname == pattern[1:] or hostname.endswith(pattern):
                return True
            continue
        if hostname == pattern:
            return True
    return False


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
