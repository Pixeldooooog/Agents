import asyncio
import random
import socket

import pytest

from agents.kernel.mcp.oauth import (
    MCP_OAUTH_CALLBACK_FALLBACK_PORT,
    MCPOAuthCallbackListener,
    MCPOAuthProviderError,
    MCPOAuthStateMismatchError,
    build_mcp_oauth_redirect_uri,
    configured_mcp_oauth_callback_port,
    find_available_mcp_oauth_callback_port,
)


def test_builds_mcp_oauth_redirect_uri():
    assert build_mcp_oauth_redirect_uri() == "http://localhost:3118/callback"
    assert build_mcp_oauth_redirect_uri(54321) == "http://localhost:54321/callback"


def test_configured_mcp_oauth_callback_port_from_env():
    assert configured_mcp_oauth_callback_port({"MCP_OAUTH_CALLBACK_PORT": "45678"}) == 45678
    assert configured_mcp_oauth_callback_port({"MCP_OAUTH_CALLBACK_PORT": "0"}) is None
    assert configured_mcp_oauth_callback_port({"MCP_OAUTH_CALLBACK_PORT": "not-a-port"}) is None


def test_find_available_mcp_oauth_callback_port_prefers_env():
    assert find_available_mcp_oauth_callback_port(
        env={"MCP_OAUTH_CALLBACK_PORT": "45678"},
        is_port_available=lambda port: False,
    ) == 45678


def test_find_available_mcp_oauth_callback_port_uses_fallback_after_random_attempts():
    class FixedRandom(random.Random):
        def randint(self, low, high):
            return low

    assert find_available_mcp_oauth_callback_port(
        env={},
        rng=FixedRandom(),
        is_port_available=lambda port: port == MCP_OAUTH_CALLBACK_FALLBACK_PORT,
    ) == MCP_OAUTH_CALLBACK_FALLBACK_PORT


def test_mcp_oauth_callback_listener_receives_code():
    if not _can_bind_loopback():
        pytest.skip("loopback binding is unavailable in this sandbox")

    async def exercise():
        async with MCPOAuthCallbackListener(port=0, expected_state="state-1") as listener:
            response = await _http_get(listener.port, "/callback?code=abc123&state=state-1")
            callback = await listener.wait(timeout_seconds=1)
            return listener.redirect_uri, response, callback

    redirect_uri, response, callback = asyncio.run(exercise())

    assert redirect_uri.endswith("/callback")
    assert "200 OK" in response
    assert callback.code == "abc123"
    assert callback.state == "state-1"


def test_mcp_oauth_callback_listener_rejects_state_mismatch():
    if not _can_bind_loopback():
        pytest.skip("loopback binding is unavailable in this sandbox")

    async def exercise():
        async with MCPOAuthCallbackListener(port=0, expected_state="expected") as listener:
            response = await _http_get(listener.port, "/callback?code=abc123&state=wrong")
            with pytest.raises(MCPOAuthStateMismatchError):
                await listener.wait(timeout_seconds=1)
            return response

    response = asyncio.run(exercise())

    assert "400 Bad Request" in response
    assert "state mismatch" in response


def test_mcp_oauth_callback_listener_accepts_manual_callback_url():
    async def exercise():
        listener = MCPOAuthCallbackListener(port=0, expected_state="manual-state")
        submitted = listener.submit_callback_url("http://localhost:3118/callback?code=manual&state=manual-state")
        callback = await listener.wait(timeout_seconds=1)
        return submitted, callback

    submitted, callback = asyncio.run(exercise())

    assert submitted is True
    assert callback.code == "manual"
    assert callback.state == "manual-state"


def test_mcp_oauth_callback_listener_surfaces_provider_error():
    async def exercise():
        listener = MCPOAuthCallbackListener(port=0)
        listener.submit_callback_url(
            "http://localhost:3118/callback?error=access_denied&error_description=Nope"
        )
        with pytest.raises(MCPOAuthProviderError) as exc_info:
            await listener.wait(timeout_seconds=1)
        return str(exc_info.value)

    assert asyncio.run(exercise()) == "OAuth error: access_denied - Nope"


async def _http_get(port: int, target: str) -> str:
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(("GET %s HTTP/1.1\r\nHost: localhost\r\n\r\n" % target).encode("ascii"))
    await writer.drain()
    response = await reader.read()
    writer.close()
    await writer.wait_closed()
    return response.decode("utf-8", errors="replace")


def _can_bind_loopback() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("127.0.0.1", 0))
        except OSError:
            return False
    return True
