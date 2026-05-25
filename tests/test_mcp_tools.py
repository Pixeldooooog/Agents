import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from agents.kernel.capabilities.mcp_loading import load_configured_mcp
from agents.kernel.capabilities.sandbox.local import LocalSandboxProvider
from agents.kernel.capabilities.tools import ToolRuntimeContext, register_builtin_tools
from agents.kernel.capabilities.tools.builtin.mcp_management import mcp_reconnect
from agents.kernel.capabilities.tools.mcp import (
    MCPAuthenticationRequired,
    MCPPromptArgumentDefinition,
    MCPPromptDefinition,
    MCPResourceDefinition,
    MCPServerConfig,
    MCPStreamableHTTPClient,
    MCPToolDefinition,
    MCPToolProvider,
    MCPWebSocketClient,
    build_mcp_tool_name,
    mcp_info_from_name,
    normalize_mcp_name,
)
from agents.kernel.capabilities.tools.mcp_websocket import websocket_client_with_headers
from agents.kernel.capabilities.tools.registry import ToolRegistry
from agents.kernel.context.workspace import WorkspaceContext
from agents.kernel.governance import SandboxPolicy, describe_tool_impact
from agents.kernel.mcp_config import InMemoryMCPConfigStore, MCPServerRecord
from agents.kernel.mcp_elicitation_runtime import build_mcp_elicitation_complete_handler
from agents.kernel.mcp_list_changed_runtime import build_mcp_list_changed_handler
from agents.kernel.schema import ToolCall


class FakeMCPClient:
    def __init__(self):
        self.called = []
        self.closed = False

    async def list_tools(self):
        return [
            MCPToolDefinition(
                name="search",
                description="Search docs",
                parameters={"type": "object", "properties": {"query": {"type": "string"}}},
            )
        ]

    async def call_tool(self, name, arguments):
        self.called.append((name, arguments))
        return {"answer": arguments["query"]}

    async def list_resources(self):
        return [
            MCPResourceDefinition(
                uri="docs://intro",
                name="Intro",
                description="Intro docs",
                mime_type="text/markdown",
            )
        ]

    async def read_resource(self, uri):
        return {"contents": [{"uri": uri, "mimeType": "text/markdown", "text": "Hello docs"}]}

    async def list_prompts(self):
        return [
            MCPPromptDefinition(
                name="review",
                description="Review code",
                arguments=[MCPPromptArgumentDefinition(name="path", description="Path to review", required=True)],
            )
        ]

    async def get_prompt(self, name, arguments=None):
        return {
            "description": "Review code",
            "messages": [{"role": "user", "content": {"type": "text", "text": "Review %s" % arguments["path"]}}],
        }

    async def close(self):
        self.closed = True


def test_mcp_provider_loads_tools_with_src_origin_dynamic_name_and_legacy_alias():
    registry = ToolRegistry()
    client = FakeMCPClient()
    provider = MCPToolProvider(
        client=client,
        server=MCPServerConfig(name="docs", execution_mode="trusted_control_plane"),
    )

    asyncio.run(provider.load_tools(registry))
    result = asyncio.run(registry.execute("mcp__docs__search", {"query": "agents"}))
    legacy_result = asyncio.run(registry.execute("mcp_docs_search", {"query": "legacy"}))

    canonical_spec = registry.specs(["mcp__docs__search"])[0]
    legacy_spec = registry.specs(["mcp_docs_search"])[0]
    assert canonical_spec.name == "mcp__docs__search"
    assert canonical_spec.raw["metadata"]["execution_mode"] == "trusted_control_plane"
    assert canonical_spec.raw["metadata"]["mcp_info"] == {
        "server": "docs",
        "remote_name": "search",
        "normalized_server": "docs",
        "normalized_tool": "search",
    }
    assert legacy_spec.raw["metadata"]["alias_of"] == "mcp__docs__search"
    assert legacy_spec.raw["metadata"]["legacy_name"] is True
    assert json.loads(result.content)["answer"] == "agents"
    assert json.loads(legacy_result.content)["answer"] == "legacy"
    assert client.called == [("search", {"query": "agents"}), ("search", {"query": "legacy"})]


def test_mcp_provider_matches_src_origin_name_normalization():
    assert normalize_mcp_name("search docs") == "search_docs"
    assert normalize_mcp_name("claude.ai Docs Server") == "claude_ai_Docs_Server"
    assert build_mcp_tool_name("claude.ai Docs Server", "search docs") == "mcp__claude_ai_Docs_Server__search_docs"
    assert mcp_info_from_name("mcp__claude_ai_Docs_Server__search_docs") == {
        "server": "claude_ai_Docs_Server",
        "tool": "search_docs",
    }


def test_mcp_provider_registers_auth_pseudo_tool_for_auth_required_server():
    registry = ToolRegistry()
    client = FakeMCPClient()
    provider = MCPToolProvider(
        client=client,
        server=MCPServerConfig(
            name="docs",
            transport="http",
            url="https://mcp.example.test",
            auth_required=True,
            auth_url="https://mcp.example.test/oauth",
            auth_status="required",
        ),
    )

    asyncio.run(provider.load_tools(registry))
    result = asyncio.run(registry.execute("mcp__docs__authenticate", {}))
    payload = json.loads(result.content)
    spec = registry.specs(["mcp__docs__authenticate"])[0]

    assert "mcp__docs__authenticate" in registry.names()
    assert "mcp__docs__search" not in registry.names()
    assert payload["status"] == "auth_url"
    assert payload["authUrl"] == "https://mcp.example.test/oauth"
    assert payload["server"] == "docs"
    assert spec.raw["metadata"]["auth_tool"] is True
    assert spec.raw["metadata"]["requires_auth"] is True
    assert spec.raw["metadata"]["mcp_info"]["remote_name"] == "authenticate"
    assert client.called == []


def test_mcp_provider_auth_pseudo_tool_uses_dynamic_oauth_authenticator():
    registry = ToolRegistry()
    captured = {}

    async def authenticate(server, arguments):
        captured["server"] = server
        captured["arguments"] = dict(arguments)
        return {
            "status": "auth_url",
            "server": server.name,
            "authUrl": "https://auth.example.test/authorize",
            "auth_url": "https://auth.example.test/authorize",
            "message": "Open authorization URL.",
        }

    provider = MCPToolProvider(
        client=FakeMCPClient(),
        server=MCPServerConfig(
            name="docs",
            transport="http",
            url="https://mcp.example.test/mcp",
            auth_required=True,
        ),
        oauth_authenticator=authenticate,
    )

    asyncio.run(provider.load_tools(registry))
    result = asyncio.run(
        registry.execute(
            "mcp__docs__authenticate",
            {"callback_url": "http://localhost:3118/callback?code=code&state=state"},
        )
    )
    payload = json.loads(result.content)
    spec = registry.specs(["mcp__docs__authenticate"])[0]

    assert payload["status"] == "auth_url"
    assert payload["authUrl"] == "https://auth.example.test/authorize"
    assert captured["server"].name == "docs"
    assert captured["arguments"]["callback_url"] == "http://localhost:3118/callback?code=code&state=state"
    assert "callback_url" in spec.parameters["properties"]


def test_mcp_provider_auth_pseudo_tool_reports_unsupported_transport():
    registry = ToolRegistry()
    provider = MCPToolProvider(
        client=FakeMCPClient(),
        server=MCPServerConfig(name="docs", transport="stdio", auth_required=True),
    )

    asyncio.run(provider.load_tools(registry))
    result = asyncio.run(registry.execute("mcp__docs__authenticate", {}))
    payload = json.loads(result.content)

    assert payload["status"] == "unsupported"
    assert payload["transport"] == "stdio"
    assert "does not support OAuth" in payload["message"]


class AuthErrorMCPClient(FakeMCPClient):
    async def list_tools(self):
        raise MCPAuthenticationRequired(
            "needs OAuth",
            auth_url="https://mcp.example.test/oauth",
            transport="sse",
            url="https://mcp.example.test/sse",
        )


def test_mcp_provider_converts_auth_error_to_auth_pseudo_tool():
    registry = ToolRegistry()
    provider = MCPToolProvider(
        client=AuthErrorMCPClient(),
        server=MCPServerConfig(name="docs", transport="sse", url="https://mcp.example.test/sse"),
    )

    asyncio.run(provider.load_tools(registry))
    result = asyncio.run(registry.execute("mcp__docs__authenticate", {}))
    payload = json.loads(result.content)

    assert registry.names() == ["mcp__docs__authenticate"]
    assert payload["status"] == "auth_url"
    assert payload["auth_url"] == "https://mcp.example.test/oauth"
    assert "needs OAuth" in payload["message"]


class AnsweringMCPClient(FakeMCPClient):
    def __init__(self, prefix: str, server=None):
        super().__init__()
        self.prefix = prefix
        self.server = server

    async def call_tool(self, name, arguments):
        self.called.append((name, arguments))
        return {"answer": "%s:%s" % (self.prefix, arguments["query"])}


class MutableToolsMCPClient(FakeMCPClient):
    def __init__(self, tool_names: list[str]):
        super().__init__()
        self.tool_names = list(tool_names)

    async def list_tools(self):
        return [
            MCPToolDefinition(
                name=name,
                description="%s docs" % name,
                parameters={"type": "object", "properties": {"query": {"type": "string"}}},
            )
            for name in self.tool_names
        ]

    async def call_tool(self, name, arguments):
        self.called.append((name, arguments))
        return {"answer": "%s:%s" % (name, arguments["query"])}


def test_builtin_mcp_resource_tools_list_and_read_resources(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path, allow_file_write=True)
    client = FakeMCPClient()
    provider = MCPToolProvider(
        client=client,
        server=MCPServerConfig(name="docs", execution_mode="trusted_control_plane"),
    )
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
        mcp_providers=[provider],
        settings=SimpleNamespace(
            mcp=SimpleNamespace(
                SERVER_NAME="docs",
                SERVER_COMMAND="python docs_mcp.py",
                EXECUTION_MODE="trusted_control_plane",
                SANDBOX_PROFILE="",
            )
        ),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    servers = asyncio.run(registry.execute("mcp.servers", {}))
    resources = asyncio.run(registry.execute("mcp.resources", {"server": "docs"}))
    content = asyncio.run(registry.execute("mcp.read_resource", {"server": "docs", "uri": "docs://intro"}))
    configured = asyncio.run(registry.execute("mcp.configure", {"name": "local", "command": "python local_mcp.py"}))
    cleared = asyncio.run(registry.execute("mcp.clear", {}))

    assert servers.raw["configured"]["name"] == "docs"
    assert servers.raw["providers"][0]["name"] == "docs"
    assert resources.raw["resources"][0]["uri"] == "docs://intro"
    assert resources.raw["resources"][0]["server"] == "docs"
    assert content.raw["server"] == "docs"
    assert content.raw["content"]["contents"][0]["text"] == "Hello docs"
    assert configured.raw["configured"]["name"] == "local"
    assert configured.raw["configured"]["command"] == "python local_mcp.py"
    assert cleared.raw["removed_providers"] == 1
    assert context.mcp_providers == []
    assert client.closed is True

    impact = describe_tool_impact(ToolCall(id="call-mcp", name="mcp.configure", arguments={"command": "python local_mcp.py"}))
    assert impact.risk == "medium"
    assert impact.operations == ["mcp_server_write"]


def test_builtin_mcp_management_tools_use_shared_config_store(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path)
    store = InMemoryMCPConfigStore()

    def make_registry():
        context = ToolRuntimeContext(
            workspace=workspace,
            sandbox=policy,
            sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
            settings=SimpleNamespace(
                mcp=SimpleNamespace(SERVER_NAME="", SERVER_COMMAND="", EXECUTION_MODE="", SANDBOX_PROFILE="")
            ),
            mcp_config_store=store,
        )
        registry = ToolRegistry()
        register_builtin_tools(registry, context)
        return registry

    first = make_registry()
    second = make_registry()

    async def execute():
        configured = await first.execute("mcp.configure", {"name": "docs", "command": "python server.py"})
        configured_search = await first.execute("mcp.configure", {"name": "search", "command": "python search.py"})
        listed = await second.execute("mcp.servers", {})
        disabled = await second.execute("mcp.disable", {"name": "search"})
        after_disable = await second.execute("mcp.servers", {})
        enabled = await second.execute("mcp.enable", {"name": "docs"})
        removed = await second.execute("mcp.remove", {"name": "docs"})
        cleared = await second.execute("mcp.clear", {})
        after_clear = await make_registry().execute("mcp.servers", {})
        return configured, configured_search, listed, disabled, after_disable, enabled, removed, cleared, after_clear

    configured, configured_search, listed, disabled, after_disable, enabled, removed, cleared, after_clear = asyncio.run(execute())

    assert configured.raw["configured"]["name"] == "docs"
    assert configured_search.raw["configured"]["name"] == "search"
    assert listed.raw["configured"]["command"] in {"python search.py", "python server.py"}
    assert {record["name"]: record["enabled"] for record in listed.raw["servers"]} == {"search": True, "docs": True}
    assert disabled.raw["disabled"] == "search"
    assert {record["name"]: record["enabled"] for record in after_disable.raw["servers"]} == {"search": False, "docs": True}
    assert enabled.raw["enabled"] == "docs"
    assert enabled.raw["configured"]["command"] == "python server.py"
    assert removed.raw["removed"] == "docs"
    assert cleared.raw["cleared"] is True
    assert cleared.raw["configured"]["enabled"] is False
    assert cleared.raw["removed_providers"] == 0
    assert cleared.raw["configured"]["command"] == ""
    assert cleared.raw["configured"]["name"] == ""
    assert after_clear.raw["servers"] == []
    assert after_clear.raw["configured"]["enabled"] is False


def test_builtin_mcp_management_prunes_matching_provider_for_multi_server_changes(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path)
    store = InMemoryMCPConfigStore()
    docs_client = FakeMCPClient()
    search_client = FakeMCPClient()
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
        settings=SimpleNamespace(
            mcp=SimpleNamespace(
                SERVER_NAME="docs",
                SERVER_COMMAND="python docs.py",
                SERVER_TRANSPORT="stdio",
                SERVER_URL="",
                SERVER_HEADERS={},
                SERVER_HEADERS_JSON="",
                EXECUTION_MODE="trusted_control_plane",
                SANDBOX_PROFILE="",
                AUTH_REQUIRED=False,
                AUTH_URL="",
                AUTH_STATUS="",
                AUTH_MESSAGE="",
            )
        ),
        mcp_config_store=store,
        mcp_providers=[
            MCPToolProvider(client=docs_client, server=MCPServerConfig(name="docs")),
            MCPToolProvider(client=search_client, server=MCPServerConfig(name="search")),
        ],
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    async def execute():
        await store.save(
            MCPServerRecord(
                name="docs",
                command="python docs.py",
                tenant_id="tenant",
                user_id="user",
                agent_id="agent",
                workspace_id="workspace",
            )
        )
        await store.save(
            MCPServerRecord(
                name="search",
                command="python search.py",
                tenant_id="tenant",
                user_id="user",
                agent_id="agent",
                workspace_id="workspace",
            )
        )
        disabled = await registry.execute("mcp.disable", {"name": "search"})
        after_disable = [provider.server.name for provider in context.mcp_providers]
        closed_after_disable = {"docs": docs_client.closed, "search": search_client.closed}
        removed = await registry.execute("mcp.remove", {"name": "docs"})
        after_remove = [provider.server.name for provider in context.mcp_providers]
        closed_after_remove = {"docs": docs_client.closed, "search": search_client.closed}
        return disabled, after_disable, closed_after_disable, removed, after_remove, closed_after_remove

    disabled, after_disable, closed_after_disable, removed, after_remove, closed_after_remove = asyncio.run(execute())

    assert disabled.raw["disabled"] == "search"
    assert after_disable == ["docs"]
    assert closed_after_disable == {"docs": False, "search": True}
    assert removed.raw["removed"] == "docs"
    assert after_remove == []
    assert closed_after_remove == {"docs": True, "search": True}


def test_builtin_mcp_reload_closes_old_providers_and_swaps_tool_handlers(monkeypatch, tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path)
    store = InMemoryMCPConfigStore()
    old_client = AnsweringMCPClient("old")
    new_clients = []

    class FakeStdioMCPClient(AnsweringMCPClient):
        def __init__(self, server):
            super().__init__("new", server=server)
            new_clients.append(self)

    monkeypatch.setattr("agents.kernel.capabilities.mcp_loading.MCPStdioClient", FakeStdioMCPClient)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
        settings=SimpleNamespace(mcp=SimpleNamespace(CLIENT_TIMEOUT=30.0, SSE_READ_TIMEOUT=120.0)),
        mcp_config_store=store,
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)
    old_provider = MCPToolProvider(client=old_client, server=MCPServerConfig(name="docs"))

    async def execute():
        await store.save(
            MCPServerRecord(
                name="docs",
                command="python docs.py",
                tenant_id="tenant",
                user_id="user",
                agent_id="agent",
                workspace_id="workspace",
            )
        )
        await old_provider.load_tools(registry)
        context.mcp_providers = [old_provider]
        before = await registry.execute("mcp__docs__search", {"query": "before"})
        reloaded = await registry.execute("mcp.reload", {})
        after = await registry.execute("mcp__docs__search", {"query": "after"})
        return before, reloaded, after

    before, reloaded, after = asyncio.run(execute())

    assert json.loads(before.content)["answer"] == "old:before"
    assert json.loads(after.content)["answer"] == "new:after"
    assert old_client.closed is True
    assert [provider.server.name for provider in context.mcp_providers] == ["docs"]
    assert new_clients and new_clients[0].called == [("search", {"query": "after"})]
    assert reloaded.raw["closed_providers"] == ["docs"]
    assert sorted(reloaded.raw["removed_tools"]) == ["mcp__docs__search", "mcp_docs_search"]
    assert reloaded.raw["loaded_tools"] == ["mcp__docs__search"]
    assert "mcp_docs_search" in registry.names()


def test_builtin_mcp_reconnect_swaps_only_target_provider(monkeypatch, tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path)
    store = InMemoryMCPConfigStore()
    old_docs_client = AnsweringMCPClient("old-docs")
    old_search_client = AnsweringMCPClient("old-search")
    new_clients = []

    class FakeStdioMCPClient(AnsweringMCPClient):
        def __init__(self, server):
            super().__init__("new-%s" % server.name, server=server)
            new_clients.append(self)

    monkeypatch.setattr("agents.kernel.capabilities.mcp_loading.MCPStdioClient", FakeStdioMCPClient)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
        settings=SimpleNamespace(mcp=SimpleNamespace(CLIENT_TIMEOUT=30.0, SSE_READ_TIMEOUT=120.0)),
        mcp_config_store=store,
        enabled_tools=["mcp__docs__search", "mcp__search__search"],
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)
    old_docs_provider = MCPToolProvider(client=old_docs_client, server=MCPServerConfig(name="docs"))
    old_search_provider = MCPToolProvider(client=old_search_client, server=MCPServerConfig(name="search"))

    async def execute():
        await store.save(
            MCPServerRecord(
                name="docs",
                command="python docs.py",
                tenant_id="tenant",
                user_id="user",
                agent_id="agent",
                workspace_id="workspace",
            )
        )
        await store.save(
            MCPServerRecord(
                name="search",
                command="python search.py",
                tenant_id="tenant",
                user_id="user",
                agent_id="agent",
                workspace_id="workspace",
            )
        )
        await old_docs_provider.load_tools(registry)
        await old_search_provider.load_tools(registry)
        context.mcp_providers = [old_docs_provider, old_search_provider]
        before_docs = await registry.execute("mcp__docs__search", {"query": "before-docs"})
        before_search = await registry.execute("mcp__search__search", {"query": "before-search"})
        reconnected = await mcp_reconnect(context, registry, name="docs")
        after_docs = await registry.execute("mcp__docs__search", {"query": "after-docs"})
        after_search = await registry.execute("mcp__search__search", {"query": "after-search"})
        return before_docs, before_search, reconnected, after_docs, after_search

    before_docs, before_search, reconnected, after_docs, after_search = asyncio.run(execute())

    assert json.loads(before_docs.content)["answer"] == "old-docs:before-docs"
    assert json.loads(before_search.content)["answer"] == "old-search:before-search"
    assert json.loads(after_docs.content)["answer"] == "new-docs:after-docs"
    assert json.loads(after_search.content)["answer"] == "old-search:after-search"
    assert old_docs_client.closed is True
    assert old_search_client.closed is False
    assert [provider.server.name for provider in context.mcp_providers] == ["docs", "search"]
    assert [client.server.name for client in new_clients] == ["docs"]
    assert reconnected["serverName"] == "docs"
    assert reconnected["closed_providers"] == ["docs"]
    assert sorted(reconnected["removed_tools"]) == ["mcp__docs__search", "mcp_docs_search"]
    assert reconnected["loaded_tools"] == ["mcp__docs__search"]
    assert context.enabled_tools == ["mcp__search__search", "mcp__docs__search"]


def test_builtin_mcp_reload_preserves_existing_provider_when_reconnect_fails(monkeypatch, tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path)
    store = InMemoryMCPConfigStore()
    old_client = AnsweringMCPClient("old")
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
        settings=SimpleNamespace(mcp=SimpleNamespace(CLIENT_TIMEOUT=30.0, SSE_READ_TIMEOUT=120.0)),
        mcp_config_store=store,
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)
    old_provider = MCPToolProvider(client=old_client, server=MCPServerConfig(name="docs"))

    async def failing_load(settings, registry, roots=None, records=None, oauth_authenticator=None, list_changed_handler=None):
        raise RuntimeError("reconnect failed")

    monkeypatch.setattr("agents.kernel.capabilities.mcp_loading.load_configured_mcp", failing_load)

    async def execute():
        await store.save(
            MCPServerRecord(
                name="docs",
                command="python docs.py",
                tenant_id="tenant",
                user_id="user",
                agent_id="agent",
                workspace_id="workspace",
            )
        )
        await old_provider.load_tools(registry)
        context.mcp_providers = [old_provider]
        failed = await registry.execute("mcp.reload", {})
        after = await registry.execute("mcp__docs__search", {"query": "after"})
        return failed, after

    failed, after = asyncio.run(execute())

    assert failed.is_error is True
    assert "reconnect failed" in failed.content
    assert old_client.closed is False
    assert context.mcp_providers == [old_provider]
    assert json.loads(after.content)["answer"] == "old:after"


def test_builtin_mcp_management_persists_auth_transport_fields(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path)
    store = InMemoryMCPConfigStore()

    def make_registry():
        context = ToolRuntimeContext(
            workspace=workspace,
            sandbox=policy,
            sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
            settings=SimpleNamespace(mcp=SimpleNamespace(SERVER_NAME="", SERVER_COMMAND="")),
            mcp_config_store=store,
        )
        registry = ToolRegistry()
        register_builtin_tools(registry, context)
        return registry

    first = make_registry()
    second = make_registry()

    asyncio.run(
        first.execute(
            "mcp.configure",
            {
                "name": "docs",
                "transport": "http",
                "url": "https://mcp.example.test",
                "headers": {"Authorization": "Bearer token"},
                "auth_required": True,
                "auth_url": "https://mcp.example.test/oauth",
                "auth_status": "required",
                "auth_message": "needs OAuth",
            },
        )
    )
    listed = asyncio.run(second.execute("mcp.servers", {}))

    assert listed.raw["configured"]["name"] == "docs"
    assert listed.raw["configured"]["transport"] == "http"
    assert listed.raw["configured"]["url"] == "https://mcp.example.test"
    assert listed.raw["configured"]["headers"] == {"Authorization": "Bearer token"}
    assert listed.raw["configured"]["auth_required"] is True
    assert listed.raw["configured"]["auth_url"] == "https://mcp.example.test/oauth"
    assert listed.raw["servers"][0]["headers"] == {"Authorization": "Bearer token"}
    assert listed.raw["servers"][0]["auth_status"] == "required"
    assert listed.raw["servers"][0]["auth_message"] == "needs OAuth"


def test_builtin_mcp_management_accepts_websocket_transport(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=SandboxPolicy.for_workspace(workspace.path),
        settings=SimpleNamespace(mcp=SimpleNamespace(SERVER_NAME="", SERVER_COMMAND="")),
        mcp_config_store=InMemoryMCPConfigStore(),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    configured = asyncio.run(
        registry.execute(
            "mcp.configure",
            {
                "name": "socket",
                "transport": "ws",
                "url": "wss://mcp.example.test/socket",
            },
        )
    )

    assert configured.raw["configured"]["name"] == "socket"
    assert configured.raw["configured"]["transport"] == "ws"
    assert configured.raw["configured"]["url"] == "wss://mcp.example.test/socket"
    assert configured.raw["servers"][0]["transport"] == "ws"


def test_load_configured_mcp_registers_auth_tool_for_auth_required_http_settings():
    registry = ToolRegistry()
    settings = SimpleNamespace(
        mcp=SimpleNamespace(
            SERVER_NAME="docs",
            SERVER_COMMAND="",
            SERVER_TRANSPORT="http",
            SERVER_URL="https://mcp.example.test",
            CLIENT_TIMEOUT=30.0,
            EXECUTION_MODE="trusted_control_plane",
            SANDBOX_PROFILE="",
            AUTH_REQUIRED=True,
            AUTH_URL="https://mcp.example.test/oauth",
            AUTH_STATUS="required",
            AUTH_MESSAGE="needs OAuth",
        )
    )

    providers = asyncio.run(load_configured_mcp(settings, registry))
    result = asyncio.run(registry.execute("mcp__docs__authenticate", {}))
    payload = json.loads(result.content)

    assert len(providers) == 1
    assert registry.names() == ["mcp__docs__authenticate"]
    assert providers[0].server.transport == "http"
    assert providers[0].server.auth_required is True
    assert payload["status"] == "auth_url"
    assert payload["authUrl"] == "https://mcp.example.test/oauth"


def test_load_configured_mcp_uses_streamable_http_transport(monkeypatch, tmp_path: Path):
    created = []

    class FakeHTTPMCPClient(FakeMCPClient):
        def __init__(self, server):
            super().__init__()
            self.server = server
            created.append(self)

    def elicitation_handler(server_name, params):
        return {"action": "decline"}

    def elicitation_complete_handler(server_name, elicitation_id):
        return None

    monkeypatch.setattr("agents.kernel.capabilities.mcp_loading.MCPStreamableHTTPClient", FakeHTTPMCPClient)
    registry = ToolRegistry()
    settings = SimpleNamespace(
        mcp=SimpleNamespace(
            SERVER_NAME="docs",
            SERVER_COMMAND="",
            SERVER_TRANSPORT="http",
            SERVER_URL="https://mcp.example.test/mcp",
            SERVER_HEADERS={"Authorization": "Bearer token"},
            CLIENT_TIMEOUT=30.0,
            SSE_READ_TIMEOUT=120.0,
            EXECUTION_MODE="trusted_control_plane",
            SANDBOX_PROFILE="",
            AUTH_REQUIRED=False,
        )
    )

    providers = asyncio.run(
        load_configured_mcp(
            settings,
            registry,
            roots=[str(tmp_path), str(tmp_path)],
            elicitation_handler=elicitation_handler,
            elicitation_complete_handler=elicitation_complete_handler,
        )
    )
    result = asyncio.run(registry.execute("mcp__docs__search", {"query": "agents"}))

    assert len(providers) == 1
    assert providers[0].server.transport == "http"
    assert providers[0].server.url == "https://mcp.example.test/mcp"
    assert providers[0].server.headers == {"Authorization": "Bearer token"}
    assert providers[0].server.sse_read_timeout_seconds == 120.0
    assert providers[0].server.roots == [str(tmp_path.resolve())]
    assert providers[0].server.elicitation_handler is elicitation_handler
    assert providers[0].server.elicitation_complete_handler is elicitation_complete_handler
    assert json.loads(result.content)["answer"] == "agents"
    assert created[0].called == [("search", {"query": "agents"})]


def test_load_configured_mcp_loads_multiple_enabled_records(monkeypatch, tmp_path: Path):
    created = []

    class FakeStdioMCPClient(FakeMCPClient):
        def __init__(self, server):
            super().__init__()
            self.server = server
            created.append(self)

    monkeypatch.setattr("agents.kernel.capabilities.mcp_loading.MCPStdioClient", FakeStdioMCPClient)
    registry = ToolRegistry()
    settings = SimpleNamespace(mcp=SimpleNamespace(CLIENT_TIMEOUT=30.0, SSE_READ_TIMEOUT=120.0))
    records = [
        MCPServerRecord(name="docs", command="python docs_server.py", enabled=True),
        MCPServerRecord(name="search", command="python search_server.py", enabled=True),
        MCPServerRecord(name="disabled", command="python disabled_server.py", enabled=False),
    ]

    providers = asyncio.run(
        load_configured_mcp(
            settings,
            registry,
            roots=[str(tmp_path)],
            records=records,
        )
    )
    docs_result = asyncio.run(registry.execute("mcp__docs__search", {"query": "docs"}))
    search_result = asyncio.run(registry.execute("mcp__search__search", {"query": "search"}))

    assert [provider.server.name for provider in providers] == ["docs", "search"]
    assert [provider.server.command for provider in providers] == ["python", "python"]
    assert [provider.server.args for provider in providers] == [["docs_server.py"], ["search_server.py"]]
    assert [provider.server.roots for provider in providers] == [[str(tmp_path.resolve())], [str(tmp_path.resolve())]]
    assert "mcp__disabled__search" not in registry.names()
    assert json.loads(docs_result.content)["answer"] == "docs"
    assert json.loads(search_result.content)["answer"] == "search"
    assert [client.called for client in created] == [[("search", {"query": "docs"})], [("search", {"query": "search"})]]


def test_mcp_session_client_lists_workspace_roots(tmp_path: Path):
    client = MCPStreamableHTTPClient(
        MCPServerConfig(
            name="docs",
            transport="http",
            url="https://mcp.example.test/mcp",
            roots=[str(tmp_path)],
        )
    )

    result = asyncio.run(client._list_roots(None))

    assert [str(root.uri).rstrip("/") for root in result.roots] == [tmp_path.resolve().as_uri()]
    assert [root.name for root in result.roots] == [tmp_path.name]


def test_mcp_session_client_routes_elicitation_handler_response(tmp_path: Path):
    captured = {}

    async def elicitation_handler(server_name, params):
        captured["server_name"] = server_name
        captured["params"] = params
        return {"action": "accept", "content": {"choice": "yes"}}

    request_params = SimpleNamespace(message="Need input", mode="form")
    client = MCPStreamableHTTPClient(
        MCPServerConfig(
            name="docs",
            transport="http",
            url="https://mcp.example.test/mcp",
            roots=[str(tmp_path)],
            elicitation_handler=elicitation_handler,
        )
    )

    result = asyncio.run(client._handle_elicitation(None, request_params))

    assert captured == {"server_name": "docs", "params": request_params}
    assert result.action == "accept"
    assert result.content == {"choice": "yes"}


def test_mcp_session_client_routes_elicitation_complete_notification():
    from mcp import types

    captured = []

    async def complete_handler(server_name, elicitation_id):
        captured.append((server_name, elicitation_id))

    client = MCPStreamableHTTPClient(
        MCPServerConfig(
            name="docs",
            transport="http",
            url="https://mcp.example.test/mcp",
            elicitation_complete_handler=complete_handler,
        )
    )
    notification = types.ServerNotification(
        root=types.ElicitCompleteNotification(
            params=types.ElicitCompleteNotificationParams(elicitationId="elicit_123")
        )
    )

    asyncio.run(client._handle_message(notification))

    assert captured == [("docs", "elicit_123")]


def test_mcp_session_client_routes_list_changed_notifications():
    from mcp import types

    captured = []

    async def list_changed_handler(server_name, kind):
        captured.append((server_name, kind))

    client = MCPStreamableHTTPClient(
        MCPServerConfig(
            name="docs",
            transport="http",
            url="https://mcp.example.test/mcp",
            list_changed_handler=list_changed_handler,
        )
    )

    asyncio.run(client._handle_message(types.ServerNotification(root=types.ToolListChangedNotification())))
    asyncio.run(client._handle_message(types.ServerNotification(root=types.PromptListChangedNotification())))
    asyncio.run(client._handle_message(types.ServerNotification(root=types.ResourceListChangedNotification())))

    assert captured == [("docs", "tools"), ("docs", "prompts"), ("docs", "resources")]


def test_mcp_list_changed_handler_refreshes_target_tools(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path)
    client = MutableToolsMCPClient(["search"])
    provider = MCPToolProvider(client=client, server=MCPServerConfig(name="docs"))
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
        enabled_tools=["mcp__docs__search"],
    )
    registry = ToolRegistry()

    async def execute():
        await provider.load_tools(registry)
        context.mcp_providers = [provider]
        before = await registry.execute("mcp__docs__search", {"query": "before"})
        client.tool_names = ["lookup"]
        handler = build_mcp_list_changed_handler(context, registry)
        await handler("docs", "tools")
        after = await registry.execute("mcp__docs__lookup", {"query": "after"})
        return before, after

    before, after = asyncio.run(execute())

    assert json.loads(before.content)["answer"] == "search:before"
    assert json.loads(after.content)["answer"] == "lookup:after"
    assert "mcp__docs__search" not in registry.names()
    assert "mcp_docs_search" not in registry.names()
    assert "mcp__docs__lookup" in registry.names()
    assert "mcp_docs_lookup" in registry.names()
    assert context.enabled_tools == ["mcp__docs__lookup"]
    assert context.mcp_list_changed_notifications == [
        {
            "mcp_server_name": "docs",
            "kind": "tools",
            "refreshed": True,
            "removed_tools": ["mcp__docs__search", "mcp_docs_search"],
            "loaded_tools": ["mcp__docs__lookup"],
        }
    ]


def test_mcp_list_changed_handler_preserves_tools_when_refresh_fails(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path)
    client = MutableToolsMCPClient(["search"])
    provider = MCPToolProvider(client=client, server=MCPServerConfig(name="docs"))
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
        enabled_tools=["mcp__docs__search"],
    )
    registry = ToolRegistry()

    async def execute():
        await provider.load_tools(registry)
        context.mcp_providers = [provider]

        async def fail_list_tools():
            raise RuntimeError("list failed")

        client.list_tools = fail_list_tools
        handler = build_mcp_list_changed_handler(context, registry)
        await handler("docs", "tools")
        return await registry.execute("mcp__docs__search", {"query": "after"})

    after = asyncio.run(execute())

    assert json.loads(after.content)["answer"] == "search:after"
    assert "mcp__docs__search" in registry.names()
    assert context.enabled_tools == ["mcp__docs__search"]
    assert context.mcp_list_changed_notifications[0]["refreshed"] is False
    assert context.mcp_list_changed_notifications[0]["error"] == "list failed"


def test_mcp_list_changed_handler_emits_runtime_event_for_non_tool_changes():
    events = []
    enqueued = []
    context = SimpleNamespace(
        mcp_list_changed_notifications=[],
        has_runtime_event_sink=lambda: True,
        emit_runtime_event=lambda event_type, name="", payload=None: events.append((event_type, name, payload)),
        async_message_enqueue=enqueued.append,
    )
    handler = build_mcp_list_changed_handler(context, ToolRegistry())

    asyncio.run(handler("docs", "prompts"))

    payload = {
        "mcp_server_name": "docs",
        "kind": "prompts",
        "refreshed": False,
        "reason": "not_tool_registry_cached",
    }
    assert context.mcp_list_changed_notifications == [payload]
    assert events == [("mcp_list_changed", "mcp", payload)]
    assert enqueued == []


def test_mcp_elicitation_complete_handler_emits_runtime_event_when_active():
    events = []
    enqueued = []
    context = SimpleNamespace(
        mcp_elicitation_completions=[],
        has_runtime_event_sink=lambda: True,
        emit_runtime_event=lambda event_type, name="", payload=None: events.append((event_type, name, payload)),
        async_message_enqueue=enqueued.append,
    )
    handler = build_mcp_elicitation_complete_handler(context)

    asyncio.run(handler("docs", "elicit_123"))

    assert context.mcp_elicitation_completions == [
        {"mcp_server_name": "docs", "elicitation_id": "elicit_123"}
    ]
    assert events == [
        (
            "elicitation_complete",
            "mcp",
            {"mcp_server_name": "docs", "elicitation_id": "elicit_123"},
        )
    ]
    assert enqueued == []


def test_mcp_elicitation_complete_handler_enqueues_async_message_without_active_event_sink():
    enqueued = []
    context = SimpleNamespace(
        mcp_elicitation_completions=[],
        has_runtime_event_sink=lambda: False,
        async_message_enqueue=enqueued.append,
    )
    handler = build_mcp_elicitation_complete_handler(context)

    asyncio.run(handler("docs", "elicit_123"))

    assert context.mcp_elicitation_completions == [
        {"mcp_server_name": "docs", "elicitation_id": "elicit_123"}
    ]
    assert len(enqueued) == 1
    assert enqueued[0]["priority"] == "later"
    assert enqueued[0]["isSynthetic"] is True
    text = enqueued[0]["message"]["content"][0]["text"]
    assert "<mcp_elicitation_complete>" in text
    assert "<server>docs</server>" in text
    assert "<elicitation_id>elicit_123</elicitation_id>" in text


def test_mcp_session_client_registers_elicitation_cancel_fallback(monkeypatch, tmp_path: Path):
    captured = {}

    class FakeSessionContext:
        def __init__(self, read, write, **kwargs):
            captured["read"] = read
            captured["write"] = write
            captured["kwargs"] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def initialize(self):
            return None

    client = MCPStreamableHTTPClient(
        MCPServerConfig(
            name="docs",
            transport="http",
            url="https://mcp.example.test/mcp",
            roots=[str(tmp_path)],
        )
    )

    async def fake_open_transport():
        return "read-stream", "write-stream"

    monkeypatch.setattr("mcp.ClientSession", FakeSessionContext)
    monkeypatch.setattr(client, "_open_transport", fake_open_transport)

    asyncio.run(client.initialize())
    callback = captured["kwargs"]["elicitation_callback"]
    result = asyncio.run(callback(None, None))
    asyncio.run(client.close())

    assert captured["read"] == "read-stream"
    assert captured["write"] == "write-stream"
    assert captured["kwargs"]["list_roots_callback"] == client._list_roots
    assert captured["kwargs"]["message_handler"] == client._handle_message
    assert result.action == "cancel"
    assert result.content is None


def test_load_configured_mcp_uses_sse_transport(monkeypatch):
    created = []

    class FakeSSEMCPClient(FakeMCPClient):
        def __init__(self, server):
            super().__init__()
            self.server = server
            created.append(self)

    monkeypatch.setattr("agents.kernel.capabilities.mcp_loading.MCPSSEClient", FakeSSEMCPClient)
    registry = ToolRegistry()
    settings = SimpleNamespace(
        mcp=SimpleNamespace(
            SERVER_NAME="events",
            SERVER_COMMAND="",
            SERVER_TRANSPORT="sse",
            SERVER_URL="https://mcp.example.test/sse",
            SERVER_HEADERS_JSON='{"X-Test":"yes"}',
            CLIENT_TIMEOUT=30.0,
            EXECUTION_MODE="trusted_control_plane",
            SANDBOX_PROFILE="",
            AUTH_REQUIRED=False,
        )
    )

    providers = asyncio.run(load_configured_mcp(settings, registry))
    result = asyncio.run(registry.execute("mcp__events__search", {"query": "agents"}))

    assert len(providers) == 1
    assert providers[0].server.transport == "sse"
    assert providers[0].server.headers == {"X-Test": "yes"}
    assert json.loads(result.content)["answer"] == "agents"
    assert created[0].called == [("search", {"query": "agents"})]


def test_load_configured_mcp_uses_websocket_transport(monkeypatch):
    created = []

    class FakeWebSocketMCPClient(FakeMCPClient):
        def __init__(self, server):
            super().__init__()
            self.server = server
            created.append(self)

    monkeypatch.setattr("agents.kernel.capabilities.mcp_loading.MCPWebSocketClient", FakeWebSocketMCPClient)
    registry = ToolRegistry()
    settings = SimpleNamespace(
        mcp=SimpleNamespace(
            SERVER_NAME="socket",
            SERVER_COMMAND="",
            SERVER_TRANSPORT="ws",
            SERVER_URL="wss://mcp.example.test/socket",
            SERVER_HEADERS_JSON='{"X-Test":"ignored"}',
            CLIENT_TIMEOUT=30.0,
            SSE_READ_TIMEOUT=120.0,
            EXECUTION_MODE="trusted_control_plane",
            SANDBOX_PROFILE="",
            AUTH_REQUIRED=False,
        )
    )

    providers = asyncio.run(load_configured_mcp(settings, registry))
    result = asyncio.run(registry.execute("mcp__socket__search", {"query": "agents"}))

    assert len(providers) == 1
    assert providers[0].server.transport == "ws"
    assert providers[0].server.url == "wss://mcp.example.test/socket"
    assert providers[0].server.headers == {"X-Test": "ignored"}
    assert json.loads(result.content)["answer"] == "agents"
    assert created[0].called == [("search", {"query": "agents"})]


def test_load_configured_mcp_uses_sdk_transport_handler():
    messages = []

    async def sdk_mcp_handler(message):
        messages.append(message)
        method = message.get("method")
        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": message["id"],
                "result": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "sdk-tools", "version": "1.0.0"},
                },
            }
        if method == "notifications/initialized":
            return None
        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": message["id"],
                "result": {
                    "tools": [
                        {
                            "name": "search",
                            "description": "Search SDK tools",
                            "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}},
                        }
                    ]
                },
            }
        if method == "tools/call":
            arguments = dict(message.get("params", {}).get("arguments", {}) or {})
            return {
                "jsonrpc": "2.0",
                "id": message["id"],
                "result": {"content": [{"type": "text", "text": "sdk:%s" % arguments.get("query", "")}]},
            }
        raise AssertionError("unexpected SDK MCP method: %s" % method)

    registry = ToolRegistry()
    settings = SimpleNamespace(
        mcp=SimpleNamespace(
            CLIENT_TIMEOUT=30.0,
            SSE_READ_TIMEOUT=120.0,
        )
    )

    async def execute():
        providers = await load_configured_mcp(
            settings,
            registry,
            records=[
                MCPServerRecord(
                    name="sdk-tools",
                    command="",
                    transport="sdk",
                    enabled=True,
                )
            ],
            sdk_mcp_handlers={"sdk-tools": sdk_mcp_handler},
        )
        result = await registry.execute("mcp__sdk-tools__search", {"query": "agents"})
        for provider in providers:
            await provider.close()
        return providers, result

    providers, result = asyncio.run(execute())

    assert len(providers) == 1
    assert providers[0].server.transport == "sdk"
    assert result.content == "sdk:agents"
    assert [message.get("method") for message in messages] == [
        "initialize",
        "notifications/initialized",
        "tools/list",
        "tools/call",
    ]


def test_mcp_websocket_client_opens_sdk_transport(monkeypatch):
    captured = {}

    class FakeContext:
        async def __aenter__(self):
            return "read-stream", "write-stream"

        async def __aexit__(self, exc_type, exc, tb):
            captured["closed"] = True

    def fake_websocket_client(url):
        captured["url"] = url
        return FakeContext()

    monkeypatch.setattr("mcp.client.websocket.websocket_client", fake_websocket_client)
    client = MCPWebSocketClient(
        MCPServerConfig(
            name="socket",
            transport="ws",
            url="wss://mcp.example.test/socket",
        )
    )

    read, write = asyncio.run(client._open_transport())
    asyncio.run(client.close())

    assert (read, write) == ("read-stream", "write-stream")
    assert captured == {"url": "wss://mcp.example.test/socket", "closed": True}


def test_mcp_websocket_client_opens_header_transport(monkeypatch):
    captured = {}

    class FakeContext:
        async def __aenter__(self):
            return "read-stream", "write-stream"

        async def __aexit__(self, exc_type, exc, tb):
            captured["closed"] = True

    def fake_websocket_client_with_headers(url, *, headers=None):
        captured["url"] = url
        captured["headers"] = dict(headers or {})
        return FakeContext()

    monkeypatch.setattr(
        "agents.kernel.capabilities.tools.mcp_websocket.websocket_client_with_headers",
        fake_websocket_client_with_headers,
    )
    client = MCPWebSocketClient(
        MCPServerConfig(
            name="socket",
            transport="ws",
            url="wss://mcp.example.test/socket",
            headers={"Authorization": "Bearer token", "X-Test": "yes"},
        )
    )

    read, write = asyncio.run(client._open_transport())
    asyncio.run(client.close())

    assert (read, write) == ("read-stream", "write-stream")
    assert captured == {
        "url": "wss://mcp.example.test/socket",
        "headers": {"Authorization": "Bearer token", "X-Test": "yes"},
        "closed": True,
    }


def test_websocket_client_with_headers_passes_handshake_headers(monkeypatch):
    captured = {}

    class FakeWebSocketContext:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            captured["closed"] = True

        def __aiter__(self):
            return self

        async def __anext__(self):
            await asyncio.Event().wait()
            raise StopAsyncIteration

        async def send(self, message):
            captured.setdefault("sent", []).append(message)

    def fake_ws_connect(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return FakeWebSocketContext()

    monkeypatch.setattr("agents.kernel.capabilities.tools.mcp_websocket.ws_connect", fake_ws_connect)

    async def run_client():
        async with websocket_client_with_headers(
            "wss://mcp.example.test/socket",
            headers={"Authorization": "Bearer token", "X-Test": "yes"},
        ) as (read, write):
            assert read is not None
            assert write is not None

    asyncio.run(run_client())

    assert captured["url"] == "wss://mcp.example.test/socket"
    assert captured["kwargs"]["additional_headers"] == {"Authorization": "Bearer token", "X-Test": "yes"}
    assert captured["closed"] is True


def test_builtin_mcp_prompt_tools_list_and_get_prompt(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path, allow_file_write=True)
    provider = MCPToolProvider(
        client=FakeMCPClient(),
        server=MCPServerConfig(name="docs", execution_mode="trusted_control_plane"),
    )
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
        mcp_providers=[provider],
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    prompts = asyncio.run(registry.execute("mcp.prompts", {"server": "docs", "query": "review"}))
    rendered = asyncio.run(registry.execute("mcp.get_prompt", {"server": "docs", "name": "review", "arguments": {"path": "src"}}))

    assert prompts.raw["prompts"][0]["name"] == "review"
    assert prompts.raw["prompts"][0]["arguments"] == [{"name": "path", "description": "Path to review", "required": True}]
    assert rendered.raw["server"] == "docs"
    assert rendered.raw["content"]["messages"][0]["content"]["text"] == "Review src"
