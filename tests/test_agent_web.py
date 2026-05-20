import asyncio
import json
from pathlib import Path

import httpx
import pytest

from agents.kernel.capabilities.tools import ToolRegistry, ToolRuntimeContext, register_builtin_tools
from agents.kernel.capabilities.web import (
    TavilyWebSearchProvider,
    WebSearchPolicy,
    WebSearchRequest,
    WebSource,
)
from agents.kernel.capabilities.web.factory import create_web_search_provider
from agents.kernel.capabilities.web.providers.tavily import TavilyConfig
from agents.kernel.capabilities.web.types import WebExtractResult, WebSearchResult, WebUsage
from agents.kernel.context.workspace import WorkspaceContext
from agents.kernel.governance import SandboxPolicy, describe_tool_impact
from agents.kernel.schema import ToolCall


def test_tavily_search_provider_normalizes_results_and_usage():
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["auth"] = request.headers.get("authorization")
        captured["payload"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={
                "request_id": "req-1",
                "response_time": 0.42,
                "usage": {"credits": 1},
                "answer": "Provider answer.",
                "results": [
                    {
                        "title": "Agents",
                        "url": "https://example.com/agents",
                        "content": "Agent systems need cited sources.",
                        "score": 0.9,
                        "published_date": "2026-04-01",
                    }
                ],
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = TavilyWebSearchProvider(
        TavilyConfig(api_key="key", base_url="https://api.tavily.test"),
        WebSearchPolicy(max_results=5),
        client=client,
    )

    async def execute():
        result = await provider.search(WebSearchRequest(query="agent search", max_results=3), run_id="run-1")
        await client.aclose()
        return result

    result = asyncio.run(execute())

    assert captured["path"] == "/search"
    assert captured["auth"] == "Bearer key"
    assert captured["payload"]["include_usage"] is True
    assert captured["payload"]["max_results"] == 3
    assert result.request_id == "req-1"
    assert result.usage.credits == 1
    assert result.sources[0].source_id == "S1"
    assert result.sources[0].domain == "example.com"
    assert result.provider_answer == "Provider answer."


def test_web_policy_blocks_raw_content_and_denied_domains():
    policy = WebSearchPolicy(deny_domains=("blocked.example",))

    with pytest.raises(PermissionError):
        policy.validate_raw_content(True)
    with pytest.raises(PermissionError):
        policy.validate_urls(("https://blocked.example/post",))


class FakeWebProvider:
    name = "fake"

    def __init__(self):
        self.run_ids = []
        self.extract_requests = []

    async def search(self, request, *, run_id=""):
        self.run_ids.append(run_id)
        return WebSearchResult(
            query=request.query,
            provider=self.name,
            request_id="fake-1",
            usage=WebUsage(credits=1),
            sources=[
                WebSource(
                    source_id="S1",
                    title="Result",
                    url="https://example.com/result",
                    domain="example.com",
                    content="ok",
                    score=0.8,
                )
            ],
        )

    async def extract(self, request, *, run_id=""):
        self.extract_requests.append((request, run_id))
        return WebExtractResult(
            provider=self.name,
            request_id="extract-1",
            usage=WebUsage(credits=1),
            sources=[
                WebSource(
                    source_id="S1",
                    title="Fetched",
                    url=request.urls[0],
                    domain="example.com",
                    content="fetched content",
                    score=1.0,
                )
            ],
        )

    async def map(self, request, *, run_id=""):
        raise RuntimeError("not used")


def test_builtin_web_search_uses_control_plane_provider_and_run_scope(tmp_path: Path):
    workspace = WorkspaceContext("tenant", "user", "agent", "workspace", tmp_path, tmp_path)
    context = ToolRuntimeContext(workspace=workspace, sandbox=SandboxPolicy.for_workspace(tmp_path))
    context.current_run_id = "run-1"
    provider = FakeWebProvider()
    registry = ToolRegistry()
    register_builtin_tools(registry, context, web_provider=provider)

    result = asyncio.run(registry.execute("web.search", {"query": "agents"}))

    assert result.is_error is False
    assert result.raw["provider"] == "fake"
    assert result.raw["sources"][0]["source_id"] == "S1"
    assert provider.run_ids == ["run-1"]
    assert registry.specs(["web.search"])[0].raw["metadata"]["provider"] == "fake"


def test_src_origin_web_aliases_route_to_control_plane_provider(tmp_path: Path):
    workspace = WorkspaceContext("tenant", "user", "agent", "workspace", tmp_path, tmp_path)
    context = ToolRuntimeContext(workspace=workspace, sandbox=SandboxPolicy.for_workspace(tmp_path))
    context.current_run_id = "run-web-alias"
    provider = FakeWebProvider()
    registry = ToolRegistry()
    register_builtin_tools(registry, context, web_provider=provider)

    search = asyncio.run(
        registry.execute("WebSearch", {"query": "agents", "allowed_domains": ["example.com"]})
    )
    fetch = asyncio.run(
        registry.execute(
            "WebFetch",
            {"url": "https://example.com/doc", "prompt": "summarize the page"},
        )
    )

    assert search.is_error is False
    assert search.raw["sources"][0]["url"] == "https://example.com/result"
    assert provider.run_ids == ["run-web-alias"]
    assert fetch.is_error is False
    assert fetch.raw["sources"][0]["content"] == "fetched content"
    request, run_id = provider.extract_requests[0]
    assert request.urls == ("https://example.com/doc",)
    assert request.query == "summarize the page"
    assert run_id == "run-web-alias"
    specs = {item.name: item.raw["metadata"] for item in registry.specs(["WebSearch", "WebFetch"])}
    assert specs["WebSearch"]["alias_of"] == "web.search"
    assert specs["WebFetch"]["alias_of"] == "web.extract"


def test_src_origin_web_alias_impact_maps_domains_and_urls():
    search_impact = describe_tool_impact(
        ToolCall(
            id="call-1",
            name="WebSearch",
            arguments={"query": "agents", "allowed_domains": ["example.com"]},
        )
    ).to_dict()
    fetch_impact = describe_tool_impact(
        ToolCall(
            id="call-2",
            name="WebFetch",
            arguments={"url": "https://example.com/doc", "prompt": "summarize"},
        )
    ).to_dict()

    assert search_impact["tool_name"] == "web.search"
    assert search_impact["domains"] == ["example.com"]
    assert search_impact["query"] == "agents"
    assert fetch_impact["tool_name"] == "web.extract"
    assert fetch_impact["domains"] == ["example.com"]
    assert fetch_impact["query"] == "summarize"


def test_web_search_impact_describes_external_disclosure_and_cost():
    impact = describe_tool_impact(
        ToolCall(
            id="call-1",
            name="web.search",
            arguments={
                "query": "latest agent search",
                "search_depth": "advanced",
                "include_domains": ["example.com"],
            },
        )
    ).to_dict()

    assert impact["external_disclosure"] is True
    assert impact["requires_network"] is True
    assert impact["query"] == "latest agent search"
    assert impact["domains"] == ["example.com"]
    assert impact["cost_estimate"]["estimated_credits"] == 2


def test_web_search_factory_returns_null_or_tavily_provider():
    class EmptySettings:
        web_search = type("Web", (), {"PROVIDER": "none"})()

    class TavilySettings:
        web_search = type(
            "Web",
            (),
            {
                "PROVIDER": "tavily",
                "TAVILY_API_KEY": "key",
                "TAVILY_BASE_URL": "https://api.tavily.test",
                "TIMEOUT": 10,
                "MAX_RESULTS": 5,
                "MAX_CREDITS_PER_RUN": 10,
                "ALLOW_DOMAINS": "example.com",
                "DENY_DOMAINS": "",
                "ALLOW_ADVANCED": False,
                "ALLOW_RAW_CONTENT": False,
            },
        )()

    assert create_web_search_provider(EmptySettings()).name == "none"
    assert create_web_search_provider(TavilySettings()).name == "tavily"
