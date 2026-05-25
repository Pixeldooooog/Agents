import asyncio
import json
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import httpx

from agents.kernel.mcp_auth import InMemoryMCPAuthTokenStore
from agents.kernel.mcp_oauth_flow import (
    MCPOAuthPendingAuthorization,
    complete_mcp_oauth_authorization,
    discover_mcp_oauth_server_metadata,
    start_mcp_oauth_authorization,
)
from agents.kernel.mcp_oauth_runtime import authenticate_mcp_oauth_server, close_mcp_oauth_waiters
from agents.kernel.mcp_oauth import parse_mcp_oauth_callback_url


def test_start_mcp_oauth_authorization_discovers_prm_registers_client_and_builds_url():
    requests = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, str(request.url), request.content))
        if str(request.url) == "https://mcp.example.test/.well-known/oauth-protected-resource/mcp":
            return httpx.Response(
                200,
                json={
                    "resource": "https://mcp.example.test/mcp",
                    "authorization_servers": ["https://auth.example.test"],
                },
            )
        if str(request.url) == "https://auth.example.test/.well-known/oauth-authorization-server":
            return httpx.Response(
                200,
                json={
                    "issuer": "https://auth.example.test",
                    "authorization_endpoint": "https://auth.example.test/authorize",
                    "token_endpoint": "https://auth.example.test/token",
                    "registration_endpoint": "https://auth.example.test/register",
                    "scopes_supported": ["read", "write"],
                },
            )
        if str(request.url) == "https://auth.example.test/register":
            body = json.loads(request.content.decode())
            assert body["client_name"] == "Agents (docs)"
            assert body["redirect_uris"] == ["http://localhost:3118/callback"]
            assert body["grant_types"] == ["authorization_code", "refresh_token"]
            assert body["response_types"] == ["code"]
            assert body["token_endpoint_auth_method"] == "none"
            assert body["scope"] == "read write"
            return httpx.Response(201, json={"client_id": "client-1", "client_secret": "secret"})
        return httpx.Response(404, json={})

    async def exercise():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await start_mcp_oauth_authorization(
                "docs",
                "https://mcp.example.test/mcp",
                redirect_uri="http://localhost:3118/callback",
                state="state-1",
                code_verifier="verifier",
                now=1000,
                http_client=client,
            )

    pending = asyncio.run(exercise())
    parsed = urlparse(pending.authorization_url)
    query = parse_qs(parsed.query)

    assert pending.client_id == "client-1"
    assert pending.client_secret == "secret"
    assert pending.token_endpoint == "https://auth.example.test/token"
    assert pending.resource == "https://mcp.example.test/mcp"
    assert pending.expires_at == 1300
    assert parsed.scheme == "https"
    assert parsed.netloc == "auth.example.test"
    assert parsed.path == "/authorize"
    assert query["client_id"] == ["client-1"]
    assert query["redirect_uri"] == ["http://localhost:3118/callback"]
    assert query["state"] == ["state-1"]
    assert query["scope"] == ["read write"]
    assert query["resource"] == ["https://mcp.example.test/mcp"]
    assert [method for method, _url, _content in requests] == ["GET", "GET", "POST"]


def test_discovers_path_aware_authorization_metadata_when_prm_is_absent():
    requested = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        if str(request.url) == "https://mcp.example.test/.well-known/oauth-authorization-server/sse":
            return httpx.Response(
                200,
                json={
                    "authorization_endpoint": "https://mcp.example.test/authorize",
                    "token_endpoint": "https://mcp.example.test/token",
                    "registration_endpoint": "https://mcp.example.test/register",
                    "default_scope": "tools",
                },
            )
        return httpx.Response(404, json={})

    async def exercise():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await discover_mcp_oauth_server_metadata(
                "https://mcp.example.test/sse",
                http_client=client,
            )

    metadata = asyncio.run(exercise())

    assert metadata.authorization_endpoint == "https://mcp.example.test/authorize"
    assert metadata.scope == "tools"
    assert "https://mcp.example.test/.well-known/oauth-authorization-server" in requested
    assert "https://mcp.example.test/.well-known/oauth-authorization-server/sse" in requested


def test_complete_mcp_oauth_authorization_exchanges_code_and_saves_token():
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["form"] = parse_qs(request.content.decode())
        return httpx.Response(
            200,
            json={
                "access_token": "access",
                "refresh_token": "refresh",
                "expires_in": 60,
                "scope": "read write",
            },
        )

    pending = MCPOAuthPendingAuthorization(
        server_name="docs",
        server_url="https://mcp.example.test/mcp",
        authorization_url="https://auth.example.test/authorize",
        redirect_uri="http://localhost:3118/callback",
        state="state-1",
        code_verifier="verifier",
        token_endpoint="https://auth.example.test/token",
        client_id="client-1",
        client_secret="secret",
        scope="read write",
        resource="https://mcp.example.test/mcp",
        expires_at=9999999999,
    )

    async def exercise():
        store = InMemoryMCPAuthTokenStore()
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            payload = await complete_mcp_oauth_authorization(
                pending,
                "http://localhost:3118/callback?code=code-1&state=state-1",
                auth_store=store,
                tenant_id="tenant",
                user_id="user",
                agent_id="agent",
                workspace_id="workspace",
                http_client=client,
            )
        token = await store.get(
            "docs",
            tenant_id="tenant",
            user_id="user",
            agent_id="agent",
            workspace_id="workspace",
        )
        return payload, token

    payload, token = asyncio.run(exercise())

    assert payload["status"] == "authenticated"
    assert payload["scopes"] == ["read", "write"]
    assert token is not None
    assert token.authorization_header() == "Bearer access"
    assert token.refresh_token == "refresh"
    assert captured["form"] == {
        "grant_type": ["authorization_code"],
        "client_id": ["client-1"],
        "client_secret": ["secret"],
        "code": ["code-1"],
        "redirect_uri": ["http://localhost:3118/callback"],
        "code_verifier": ["verifier"],
        "resource": ["https://mcp.example.test/mcp"],
    }


def test_authenticate_mcp_oauth_server_starts_and_completes_flow(monkeypatch):
    monkeypatch.setattr("agents.kernel.mcp_oauth_runtime.find_available_mcp_oauth_callback_port", lambda: 3118)
    registry = object()
    reload_calls = []

    async def fake_reload(context, active_registry):
        reload_calls.append((context, active_registry))
        return {
            "loaded_tools": ["mcp__docs__search"],
            "providers": [{"name": "docs"}],
            "removed_tools": [],
        }

    monkeypatch.setattr("agents.kernel.capabilities.tools.builtin.mcp_management.mcp_reload", fake_reload)

    async def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == "https://mcp.example.test/.well-known/oauth-protected-resource/mcp":
            return httpx.Response(
                200,
                json={"authorization_servers": ["https://auth.example.test"]},
            )
        if url == "https://auth.example.test/.well-known/oauth-authorization-server":
            return httpx.Response(
                200,
                json={
                    "authorization_endpoint": "https://auth.example.test/authorize",
                    "token_endpoint": "https://auth.example.test/token",
                    "registration_endpoint": "https://auth.example.test/register",
                    "scope": "read",
                },
            )
        if url == "https://auth.example.test/register":
            return httpx.Response(201, json={"client_id": "client-1"})
        if url == "https://auth.example.test/token":
            return httpx.Response(200, json={"access_token": "access", "scope": "read"})
        return httpx.Response(404, json={})

    async def exercise():
        store = InMemoryMCPAuthTokenStore()
        context = SimpleNamespace(
            workspace=SimpleNamespace(
                tenant_id="tenant",
                user_id="user",
                agent_id="agent",
                workspace_id="workspace",
            ),
            mcp_auth_store=store,
            mcp_oauth_flows={},
            session=SimpleNamespace(runtime=SimpleNamespace(tools=registry)),
        )
        server = SimpleNamespace(name="docs", transport="http", url="https://mcp.example.test/mcp")
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            started = await authenticate_mcp_oauth_server(
                context,
                server,
                {"wait_for_callback": False},
                http_client=client,
            )
            state = parse_qs(urlparse(started["authUrl"]).query)["state"][0]
            completed = await authenticate_mcp_oauth_server(
                context,
                server,
                {"callback_url": "http://localhost:3118/callback?code=code-1&state=%s" % state},
                http_client=client,
            )
        token = await store.get(
            "docs",
            tenant_id="tenant",
            user_id="user",
            agent_id="agent",
            workspace_id="workspace",
        )
        return started, completed, token, context.mcp_oauth_flows, context

    started, completed, token, flows, context = asyncio.run(exercise())

    assert started["status"] == "auth_url"
    assert started["redirect_uri"] == "http://localhost:3118/callback"
    assert completed["status"] == "authenticated"
    assert completed["reload"] == {
        "status": "reloaded",
        "loaded_tools": ["mcp__docs__search"],
        "providers": [{"name": "docs"}],
        "removed_tools": [],
    }
    assert "MCP tools were reloaded" in completed["message"]
    assert token is not None
    assert token.authorization_header() == "Bearer access"
    assert flows == {}
    assert len(reload_calls) == 1
    assert reload_calls[0][0] is context
    assert reload_calls[0][1] is registry


def test_authenticate_mcp_oauth_server_waits_for_loopback_callback_and_opens_browser(monkeypatch):
    monkeypatch.setattr("agents.kernel.mcp_oauth_runtime.find_available_mcp_oauth_callback_port", lambda: 0)
    opened = []

    async def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == "https://mcp.example.test/.well-known/oauth-protected-resource/mcp":
            return httpx.Response(
                200,
                json={"authorization_servers": ["https://auth.example.test"]},
            )
        if url == "https://auth.example.test/.well-known/oauth-authorization-server":
            return httpx.Response(
                200,
                json={
                    "authorization_endpoint": "https://auth.example.test/authorize",
                    "token_endpoint": "https://auth.example.test/token",
                    "registration_endpoint": "https://auth.example.test/register",
                    "scope": "read",
                },
            )
        if url == "https://auth.example.test/register":
            return httpx.Response(201, json={"client_id": "client-1"})
        if url == "https://auth.example.test/token":
            return httpx.Response(200, json={"access_token": "access", "scope": "read"})
        return httpx.Response(404, json={})

    async def exercise():
        store = InMemoryMCPAuthTokenStore()
        context = SimpleNamespace(
            workspace=SimpleNamespace(
                tenant_id="tenant",
                user_id="user",
                agent_id="agent",
                workspace_id="workspace",
            ),
            mcp_auth_store=store,
            mcp_oauth_flows={},
            mcp_oauth_waiters={},
            mcp_oauth_results={},
            mcp_oauth_listener_factory=lambda port, expected_state: FakeOAuthListener(port, expected_state),
            mcp_oauth_browser_opener=opened.append,
        )
        server = SimpleNamespace(name="docs", transport="http", url="https://mcp.example.test/mcp")
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            started = await authenticate_mcp_oauth_server(context, server, {}, http_client=client)
            waiter = context.mcp_oauth_waiters["docs"]
            state = parse_qs(urlparse(started["authUrl"]).query)["state"][0]
            waiter.listener.submit_callback_url("http://localhost:3118/callback?code=code-1&state=%s" % state)
            await waiter.task
        token = await store.get(
            "docs",
            tenant_id="tenant",
            user_id="user",
            agent_id="agent",
            workspace_id="workspace",
        )
        return started, token, context

    started, token, context = asyncio.run(exercise())

    assert started["status"] == "auth_url"
    assert started["callbackListening"] is True
    assert started["browserOpened"] is True
    assert opened == [started["authUrl"]]
    assert token is not None
    assert token.authorization_header() == "Bearer access"
    assert context.mcp_oauth_flows == {}
    assert context.mcp_oauth_waiters == {}
    assert context.mcp_oauth_results["docs"]["status"] == "authenticated"
    assert context.mcp_oauth_results["docs"]["reload"] == {
        "status": "skipped",
        "reason": "no_active_registry",
    }


def test_authenticate_mcp_oauth_server_keeps_auth_success_when_reload_fails(monkeypatch):
    monkeypatch.setattr("agents.kernel.mcp_oauth_runtime.find_available_mcp_oauth_callback_port", lambda: 3118)

    async def fail_reload(_context, _registry):
        raise RuntimeError("reload failed")

    monkeypatch.setattr("agents.kernel.capabilities.tools.builtin.mcp_management.mcp_reload", fail_reload)

    async def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == "https://mcp.example.test/.well-known/oauth-protected-resource/mcp":
            return httpx.Response(200, json={"authorization_servers": ["https://auth.example.test"]})
        if url == "https://auth.example.test/.well-known/oauth-authorization-server":
            return httpx.Response(
                200,
                json={
                    "authorization_endpoint": "https://auth.example.test/authorize",
                    "token_endpoint": "https://auth.example.test/token",
                    "registration_endpoint": "https://auth.example.test/register",
                    "scope": "read",
                },
            )
        if url == "https://auth.example.test/register":
            return httpx.Response(201, json={"client_id": "client-1"})
        if url == "https://auth.example.test/token":
            return httpx.Response(200, json={"access_token": "access", "scope": "read"})
        return httpx.Response(404, json={})

    async def exercise():
        store = InMemoryMCPAuthTokenStore()
        context = SimpleNamespace(
            workspace=SimpleNamespace(
                tenant_id="tenant",
                user_id="user",
                agent_id="agent",
                workspace_id="workspace",
            ),
            mcp_auth_store=store,
            mcp_oauth_flows={},
            session=SimpleNamespace(runtime=SimpleNamespace(tools=object())),
        )
        server = SimpleNamespace(name="docs", transport="http", url="https://mcp.example.test/mcp")
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            started = await authenticate_mcp_oauth_server(
                context,
                server,
                {"wait_for_callback": False},
                http_client=client,
            )
            state = parse_qs(urlparse(started["authUrl"]).query)["state"][0]
            completed = await authenticate_mcp_oauth_server(
                context,
                server,
                {"callback_url": "http://localhost:3118/callback?code=code-1&state=%s" % state},
                http_client=client,
            )
        token = await store.get(
            "docs",
            tenant_id="tenant",
            user_id="user",
            agent_id="agent",
            workspace_id="workspace",
        )
        return completed, token, context.mcp_oauth_flows

    completed, token, flows = asyncio.run(exercise())

    assert completed["status"] == "authenticated"
    assert completed["reload"] == {"status": "error", "message": "reload failed"}
    assert "Token was cached" in completed["message"]
    assert token is not None
    assert token.authorization_header() == "Bearer access"
    assert flows == {}


def test_close_mcp_oauth_waiters_cancels_active_loopback_waiter():
    async def exercise():
        listener = FakeOAuthListener(port=3118, expected_state="state")
        await listener.start()
        task = asyncio.create_task(listener.wait(timeout_seconds=60))
        context = SimpleNamespace(
            mcp_oauth_waiters={
                "docs": SimpleNamespace(server_name="docs", listener=listener, task=task),
            }
        )
        await close_mcp_oauth_waiters(context)
        return task.cancelled(), listener.closed, context.mcp_oauth_waiters

    cancelled, closed, waiters = asyncio.run(exercise())

    assert cancelled is True
    assert closed is True
    assert waiters == {}


class FakeOAuthListener:
    def __init__(self, port: int, expected_state: str):
        self.port = int(port or 3118)
        self.expected_state = expected_state
        self.closed = False
        self._future = None

    @property
    def redirect_uri(self):
        return "http://localhost:%d/callback" % self.port

    async def start(self):
        self._future = asyncio.get_running_loop().create_future()

    async def close(self):
        self.closed = True

    async def wait(self, timeout_seconds: float = 300):
        return await asyncio.wait_for(self._future, timeout_seconds)

    def submit_callback_url(self, callback_url: str):
        callback = parse_mcp_oauth_callback_url(callback_url)
        if callback is None:
            return False
        if callback.state != self.expected_state:
            self._future.set_exception(RuntimeError("state mismatch"))
        else:
            self._future.set_result(callback)
        return True
