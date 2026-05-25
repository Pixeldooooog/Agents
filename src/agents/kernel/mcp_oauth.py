from __future__ import annotations

import asyncio
import html
import os
import random
import socket
import sys
from dataclasses import dataclass
from typing import Callable, Mapping
from urllib.parse import parse_qs, urlparse


MCP_OAUTH_CALLBACK_PATH = "/callback"
MCP_OAUTH_CALLBACK_FALLBACK_PORT = 3118
MCP_OAUTH_CALLBACK_TIMEOUT_SECONDS = 5 * 60


@dataclass(frozen=True)
class MCPOAuthCallback:
    code: str = ""
    state: str = ""
    error: str = ""
    error_description: str = ""
    error_uri: str = ""
    callback_url: str = ""


class MCPOAuthCallbackError(Exception):
    pass


class MCPOAuthStateMismatchError(MCPOAuthCallbackError):
    pass


class MCPOAuthProviderError(MCPOAuthCallbackError):
    pass


def build_mcp_oauth_redirect_uri(port: int = MCP_OAUTH_CALLBACK_FALLBACK_PORT) -> str:
    return "http://localhost:%d%s" % (int(port), MCP_OAUTH_CALLBACK_PATH)


def configured_mcp_oauth_callback_port(env: Mapping[str, str] | None = None) -> int | None:
    value = str((env or os.environ).get("MCP_OAUTH_CALLBACK_PORT", "") or "").strip()
    try:
        port = int(value)
    except ValueError:
        return None
    return port if port > 0 else None


def find_available_mcp_oauth_callback_port(
    *,
    env: Mapping[str, str] | None = None,
    is_port_available: Callable[[int], bool] | None = None,
    rng: random.Random | None = None,
) -> int:
    configured = configured_mcp_oauth_callback_port(env)
    if configured is not None:
        return configured

    available = is_port_available or _is_port_available
    low, high = _redirect_port_range()
    picker = rng or random.SystemRandom()
    attempts = min(high - low + 1, 100)
    for _ in range(attempts):
        port = picker.randint(low, high)
        if available(port):
            return port
    if available(MCP_OAUTH_CALLBACK_FALLBACK_PORT):
        return MCP_OAUTH_CALLBACK_FALLBACK_PORT
    raise RuntimeError("No available ports for OAuth redirect")


class MCPOAuthCallbackListener:
    def __init__(
        self,
        *,
        port: int,
        expected_state: str = "",
        host: str = "127.0.0.1",
    ):
        self.port = int(port)
        self.expected_state = str(expected_state or "")
        self.host = str(host or "127.0.0.1")
        self._server: asyncio.AbstractServer | None = None
        self._future: asyncio.Future[MCPOAuthCallback] | None = None

    @property
    def redirect_uri(self) -> str:
        return build_mcp_oauth_redirect_uri(self.port)

    async def __aenter__(self) -> "MCPOAuthCallbackListener":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def start(self) -> None:
        if self._server is not None:
            return
        self._ensure_future()
        self._server = await asyncio.start_server(self._handle_client, self.host, self.port)
        sockets = self._server.sockets or []
        if sockets:
            self.port = int(sockets[0].getsockname()[1])

    async def close(self) -> None:
        if self._server is None:
            return
        self._server.close()
        await self._server.wait_closed()
        self._server = None

    async def wait(self, timeout_seconds: float = MCP_OAUTH_CALLBACK_TIMEOUT_SECONDS) -> MCPOAuthCallback:
        self._ensure_future()
        return await asyncio.wait_for(self._future, timeout=max(0.0, float(timeout_seconds)))

    def submit_callback_url(self, callback_url: str) -> bool:
        self._ensure_future()
        callback = _parse_callback_url(callback_url)
        if callback is None or not callback.code and not callback.error:
            return False
        self._resolve_callback(callback)
        return True

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            request = await reader.readuntil(b"\r\n\r\n")
        except (asyncio.IncompleteReadError, asyncio.LimitOverrunError):
            writer.close()
            await writer.wait_closed()
            return
        request_line = request.decode("iso-8859-1", errors="replace").splitlines()[0] if request else ""
        method, target = _request_target(request_line)
        if method != "GET" or not target:
            await _write_http_response(writer, 405, _html_page("Authentication Error", "Unsupported request."))
            return
        callback = _parse_callback_url("http://localhost%s" % target)
        if callback is None:
            await _write_http_response(writer, 404, _html_page("Authentication Error", "Unknown callback path."))
            return
        if callback.error:
            await _write_http_response(
                writer,
                200,
                _html_page(
                    "Authentication Error",
                    "%s%s" % (
                        callback.error,
                        ": %s" % callback.error_description if callback.error_description else "",
                    ),
                ),
            )
            self._resolve_callback(callback)
            return
        if not callback.code:
            await _write_http_response(writer, 400, _html_page("Authentication Error", "Missing authorization code."))
            return
        try:
            self._validate_state(callback)
        except MCPOAuthStateMismatchError as exc:
            await _write_http_response(writer, 400, _html_page("Authentication Error", str(exc)))
            self._set_exception(exc)
            return
        await _write_http_response(
            writer,
            200,
            _html_page("Authentication Successful", "You can close this window and return to Agents."),
        )
        self._set_result(callback)

    def _resolve_callback(self, callback: MCPOAuthCallback) -> None:
        if callback.error:
            message = "OAuth error: %s" % callback.error
            if callback.error_description:
                message += " - %s" % callback.error_description
            if callback.error_uri:
                message += " (See: %s)" % callback.error_uri
            self._set_exception(MCPOAuthProviderError(message))
            return
        try:
            self._validate_state(callback)
        except MCPOAuthStateMismatchError as exc:
            self._set_exception(exc)
            return
        self._set_result(callback)

    def _validate_state(self, callback: MCPOAuthCallback) -> None:
        if self.expected_state and callback.state != self.expected_state:
            raise MCPOAuthStateMismatchError("OAuth state mismatch - possible CSRF attack")

    def _set_result(self, callback: MCPOAuthCallback) -> None:
        if self._future is not None and not self._future.done():
            self._future.set_result(callback)

    def _set_exception(self, exc: Exception) -> None:
        if self._future is not None and not self._future.done():
            self._future.set_exception(exc)

    def _ensure_future(self) -> None:
        if self._future is None:
            self._future = asyncio.get_running_loop().create_future()


def _redirect_port_range() -> tuple[int, int]:
    if sys.platform.startswith("win"):
        return 39152, 49151
    return 49152, 65535


def _is_port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", int(port)))
        except OSError:
            return False
    return True


def _request_target(request_line: str) -> tuple[str, str]:
    parts = request_line.split()
    if len(parts) < 2:
        return "", ""
    return parts[0].upper(), parts[1]


def _parse_callback_url(callback_url: str) -> MCPOAuthCallback | None:
    parsed = urlparse(str(callback_url or ""))
    if parsed.path != MCP_OAUTH_CALLBACK_PATH:
        return None
    query = parse_qs(parsed.query, keep_blank_values=True)
    return MCPOAuthCallback(
        code=_first(query, "code"),
        state=_first(query, "state"),
        error=_first(query, "error"),
        error_description=_first(query, "error_description"),
        error_uri=_first(query, "error_uri"),
        callback_url=str(callback_url or ""),
    )


def _first(query: dict[str, list[str]], key: str) -> str:
    values = query.get(key) or []
    return str(values[0]) if values else ""


def _html_page(title: str, message: str) -> str:
    return (
        "<!doctype html><html><head><meta charset=\"utf-8\"><title>%s</title></head>"
        "<body><h1>%s</h1><p>%s</p></body></html>"
    ) % (html.escape(title), html.escape(title), html.escape(message))


async def _write_http_response(writer: asyncio.StreamWriter, status: int, body: str) -> None:
    reason = {
        200: "OK",
        400: "Bad Request",
        404: "Not Found",
        405: "Method Not Allowed",
    }.get(status, "OK")
    encoded = body.encode("utf-8")
    headers = (
        "HTTP/1.1 %d %s\r\n"
        "Content-Type: text/html; charset=utf-8\r\n"
        "Content-Length: %d\r\n"
        "Connection: close\r\n\r\n"
    ) % (status, reason, len(encoded))
    writer.write(headers.encode("ascii") + encoded)
    await writer.drain()
    writer.close()
    await writer.wait_closed()
