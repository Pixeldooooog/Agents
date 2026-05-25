import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from agents.kernel.capabilities.mcp_loading import load_configured_mcp
from agents.kernel.capabilities.sandbox.local import LocalSandboxProvider
from agents.kernel.capabilities.tools import ToolRuntimeContext, register_builtin_tools
from agents.kernel.capabilities.tools.mcp import (
    MCPAuthenticationRequired,
    MCPPromptArgumentDefinition,
    MCPPromptDefinition,
    MCPResourceDefinition,
    MCPServerConfig,
    MCPStreamableHTTPClient,
    MCPToolDefinition,
    MCPToolProvider,
    build_mcp_tool_name,
    mcp_info_from_name,
    normalize_mcp_name,
)
from agents.kernel.capabilities.tools.registry import ToolRegistry
from agents.kernel.context.workspace import WorkspaceContext
from agents.kernel.governance import SandboxPolicy, describe_tool_impact
from agents.kernel.mcp_config import InMemoryMCPConfigStore
from agents.kernel.schema import ToolCall


class FakeMCPClient:
    def __init__(self):
        self.called = []

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
    provider = MCPToolProvider(
        client=FakeMCPClient(),
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
        enabled = await second.execute("mcp.enable", {"name": "docs"})
        removed = await second.execute("mcp.remove", {"name": "docs"})
        cleared = await second.execute("mcp.clear", {})
        after_clear = await make_registry().execute("mcp.servers", {})
        return configured, configured_search, listed, disabled, enabled, removed, cleared, after_clear

    configured, configured_search, listed, disabled, enabled, removed, cleared, after_clear = asyncio.run(execute())

    assert configured.raw["configured"]["name"] == "docs"
    assert configured_search.raw["configured"]["name"] == "search"
    assert listed.raw["configured"]["command"] == "python search.py"
    assert {record["name"]: record["enabled"] for record in listed.raw["servers"]} == {"search": True, "docs": False}
    assert disabled.raw["disabled"] == "search"
    assert disabled.raw["configured"]["enabled"] is False
    assert enabled.raw["enabled"] == "docs"
    assert enabled.raw["configured"]["command"] == "python server.py"
    assert removed.raw["removed"] == "docs"
    assert cleared.raw["cleared"] is True
    assert after_clear.raw["configured"]["enabled"] is False


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
    assert json.loads(result.content)["answer"] == "agents"
    assert created[0].called == [("search", {"query": "agents"})]


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
