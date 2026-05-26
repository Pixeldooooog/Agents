import asyncio
import time
from types import SimpleNamespace

from agents.kernel.mcp.loading import load_configured_mcp
from agents.kernel.capabilities.tools.registry import ToolRegistry
from agents.kernel.mcp.auth import (
    InMemoryMCPAuthTokenStore,
    MCPAuthTokenRecord,
    SQLiteMCPAuthTokenStore,
    mcp_authorization_headers_for_scope,
    merge_cached_authorization_header,
)
from agents.kernel.mcp.config import MCPServerRecord
from agents.kernel.persistence import SQLiteDatabase


def test_mcp_auth_token_record_builds_authorization_header_and_expiry():
    fresh = MCPAuthTokenRecord(name="docs", access_token="token", expires_at=time.time() + 3600)
    expired = MCPAuthTokenRecord(name="docs", access_token="token", token_type="DPoP", expires_at=time.time() - 1)

    assert fresh.authorization_header() == "Bearer token"
    assert fresh.is_expired(leeway_seconds=300) is False
    assert expired.authorization_header() == "DPoP token"
    assert expired.is_expired() is True


def test_mcp_authorization_headers_use_most_specific_nonexpired_token():
    async def exercise():
        store = InMemoryMCPAuthTokenStore()
        await store.save(
            MCPAuthTokenRecord(
                name="docs",
                access_token="global",
                tenant_id="tenant",
            )
        )
        await store.save(
            MCPAuthTokenRecord(
                name="docs",
                access_token="workspace",
                tenant_id="tenant",
                user_id="user",
                agent_id="agent",
                workspace_id="workspace",
            )
        )
        await store.save(
            MCPAuthTokenRecord(
                name="expired",
                access_token="old",
                expires_at=time.time() - 1,
                tenant_id="tenant",
            )
        )
        return await mcp_authorization_headers_for_scope(
            store,
            names=["docs", "expired"],
            tenant_id="tenant",
            user_id="user",
            agent_id="agent",
            workspace_id="workspace",
        )

    assert asyncio.run(exercise()) == {"docs": "Bearer workspace"}


def test_sqlite_mcp_auth_token_store_roundtrips_and_deletes(tmp_path):
    async def exercise():
        store = SQLiteMCPAuthTokenStore(SQLiteDatabase(tmp_path / "agents.db"))
        await store.save(
            MCPAuthTokenRecord(
                name="docs",
                access_token="stored",
                refresh_token="refresh",
                scopes=["read", "write"],
                tenant_id="tenant",
                user_id="user",
                agent_id="agent",
                workspace_id="workspace",
            )
        )
        loaded = await store.get(
            "docs",
            tenant_id="tenant",
            user_id="user",
            agent_id="agent",
            workspace_id="workspace",
        )
        await store.delete(
            "docs",
            tenant_id="tenant",
            user_id="user",
            agent_id="agent",
            workspace_id="workspace",
        )
        deleted = await store.get(
            "docs",
            tenant_id="tenant",
            user_id="user",
            agent_id="agent",
            workspace_id="workspace",
        )
        return loaded, deleted

    loaded, deleted = asyncio.run(exercise())

    assert loaded is not None
    assert loaded.authorization_header() == "Bearer stored"
    assert loaded.refresh_token == "refresh"
    assert loaded.scopes == ["read", "write"]
    assert deleted is None


def test_load_configured_mcp_injects_cached_authorization_header(monkeypatch):
    created = []

    class FakeHTTPMCPClient:
        def __init__(self, server):
            self.server = server
            created.append(self)

        async def list_tools(self):
            return []

        async def close(self):
            return None

    monkeypatch.setattr("agents.kernel.mcp.loading.MCPStreamableHTTPClient", FakeHTTPMCPClient)
    settings = SimpleNamespace(mcp=SimpleNamespace(CLIENT_TIMEOUT=30.0, SSE_READ_TIMEOUT=120.0))
    registry = ToolRegistry()

    providers = asyncio.run(
        load_configured_mcp(
            settings,
            registry,
            records=[MCPServerRecord(name="docs", command="", transport="http", url="https://mcp.example.test")],
            auth_headers={"docs": "Bearer cached"},
        )
    )

    assert len(providers) == 1
    assert created[0].server.headers["Authorization"] == "Bearer cached"


def test_cached_authorization_header_does_not_override_configured_header():
    assert merge_cached_authorization_header(
        {"authorization": "Bearer configured"},
        "Bearer cached",
    ) == {"authorization": "Bearer configured"}
