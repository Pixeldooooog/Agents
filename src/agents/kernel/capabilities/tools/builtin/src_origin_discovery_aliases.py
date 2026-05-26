from __future__ import annotations

from agents.kernel.capabilities.tools.builtin.mcp.resources import (
    MCP_READ_RESOURCE_SCHEMA,
    MCP_RESOURCES_SCHEMA,
    mcp_read_resource,
    mcp_resources,
)
from agents.kernel.capabilities.tools.builtin.meta import (
    SRC_ORIGIN_TOOL_SEARCH_SCHEMA,
    format_src_origin_tool_search_result,
    src_origin_tool_search,
)
from agents.kernel.capabilities.tools.builtin.registration_helpers import register_builtin_tool
from agents.kernel.capabilities.tools.builtin.web import (
    SRC_ORIGIN_WEB_FETCH_SCHEMA,
    SRC_ORIGIN_WEB_SEARCH_SCHEMA,
    format_src_origin_web_fetch_result,
    format_src_origin_web_search_result,
    src_origin_web_fetch,
    src_origin_web_search,
)
from agents.kernel.capabilities.tools.context import ToolRuntimeContext
from agents.kernel.capabilities.tools.registry import ToolRegistry
from agents.kernel.capabilities.web import WebSearchProvider


def register_src_origin_discovery_aliases(
    registry: ToolRegistry,
    context: ToolRuntimeContext,
    active_web_provider: WebSearchProvider,
) -> None:
    register_builtin_tool(
        registry,
        name="WebSearch",
        description="Search the web for current information. src-origin alias for web.search.",
        parameters=SRC_ORIGIN_WEB_SEARCH_SCHEMA,
        handler=lambda query, allowed_domains=None, blocked_domains=None: src_origin_web_search(
            context,
            active_web_provider,
            query=query,
            allowed_domains=allowed_domains,
            blocked_domains=blocked_domains,
        ),
        metadata={
            "risk": "medium",
            "requires_network": True,
            "external_disclosure": True,
            "provider": getattr(active_web_provider, "name", "none"),
            "alias_of": "web.search",
            "src_origin_tool": "WebSearch",
            "defer": True,
        },
        read_only=True,
        max_result_size_chars=100000,
        activity_kind="web",
        activity_title="Search web",
        activity_target_argument="query",
        result_formatter=format_src_origin_web_search_result,
    )
    register_builtin_tool(
        registry,
        name="WebFetch",
        description="Fetch and extract content from a URL. src-origin alias for web.extract.",
        parameters=SRC_ORIGIN_WEB_FETCH_SCHEMA,
        handler=lambda url, prompt: src_origin_web_fetch(
            context,
            active_web_provider,
            url=url,
            prompt=prompt,
        ),
        metadata={
            "risk": "medium",
            "requires_network": True,
            "external_disclosure": True,
            "provider": getattr(active_web_provider, "name", "none"),
            "alias_of": "web.extract",
            "src_origin_tool": "WebFetch",
            "defer": True,
        },
        read_only=True,
        max_result_size_chars=100000,
        activity_kind="web",
        activity_title="Extract web content",
        activity_target_argument="url",
        result_formatter=format_src_origin_web_fetch_result,
    )
    register_builtin_tool(
        registry,
        name="ListMcpResourcesTool",
        description="List resources from configured MCP servers. src-origin alias for mcp.resources.",
        parameters=MCP_RESOURCES_SCHEMA,
        handler=lambda server="", uri_prefix="", max_results=50: mcp_resources(
            context,
            server=server,
            uri_prefix=uri_prefix,
            max_results=max_results,
        ),
        metadata={"risk": "low", "alias_of": "mcp.resources", "src_origin_tool": "ListMcpResourcesTool"},
        read_only=True,
        activity_kind="mcp",
        activity_title="List MCP resources",
        activity_target_argument="server",
    )
    register_builtin_tool(
        registry,
        name="ReadMcpResourceTool",
        description="Read a resource from a configured MCP server. src-origin alias for mcp.read_resource.",
        parameters=MCP_READ_RESOURCE_SCHEMA,
        handler=lambda uri, server="": mcp_read_resource(context, uri=uri, server=server),
        metadata={"risk": "medium", "alias_of": "mcp.read_resource", "src_origin_tool": "ReadMcpResourceTool"},
        read_only=True,
        activity_kind="mcp",
        activity_title="Read MCP resource",
        activity_target_argument="uri",
    )
    register_builtin_tool(
        registry,
        name="ToolSearch",
        description="Search registered tools. src-origin alias for tool.search.",
        parameters=SRC_ORIGIN_TOOL_SEARCH_SCHEMA,
        handler=lambda query, max_results=5: src_origin_tool_search(
            context,
            registry,
            query=query,
            max_results=max_results,
        ),
        metadata={"risk": "low", "defer": True, "alias_of": "tool.search", "src_origin_tool": "ToolSearch"},
        read_only=True,
        max_result_size_chars=100000,
        activity_kind="state",
        activity_title="Search tools",
        activity_target_argument="query",
        result_formatter=format_src_origin_tool_search_result,
    )
