from __future__ import annotations

from agents.kernel.capabilities.tools.builtin.registration_helpers import register_builtin_tool as _register_builtin_tool
from agents.kernel.capabilities.tools.builtin.web import (
    WEB_EXTRACT_SCHEMA,
    WEB_MAP_SCHEMA,
    WEB_SEARCH_SCHEMA,
    web_extract,
    web_map,
    web_search,
)
from agents.kernel.capabilities.tools.context import ToolRuntimeContext
from agents.kernel.capabilities.tools.registry import ToolRegistry
from agents.kernel.capabilities.web import WebSearchProvider


def register_web_tools(registry: ToolRegistry, context: ToolRuntimeContext, active_web_provider: WebSearchProvider) -> None:
    _register_builtin_tool(
        registry,
        name="web.search",
        description="Search the web through the configured control-plane search provider and return cited sources.",
        parameters=WEB_SEARCH_SCHEMA,
        handler=lambda query,
        topic="general",
        search_depth="basic",
        max_results=5,
        time_range="",
        include_domains=None,
        exclude_domains=None,
        country="",
        include_answer=False,
        include_raw_content=False,
        chunks_per_source=3: web_search(
            context,
            active_web_provider,
            query=query,
            topic=topic,
            search_depth=search_depth,
            max_results=max_results,
            time_range=time_range,
            include_domains=include_domains,
            exclude_domains=exclude_domains,
            country=country,
            include_answer=include_answer,
            include_raw_content=include_raw_content,
            chunks_per_source=chunks_per_source,
        ),
        metadata={
            "risk": "medium",
            "requires_network": True,
            "external_disclosure": True,
            "provider": getattr(active_web_provider, "name", "none"),
        },
        read_only=True,
        activity_kind="web",
        activity_title="Search web",
        activity_target_argument="query",
    )
    _register_builtin_tool(
        registry,
        name="web.extract",
        description="Extract clean content from specific URLs through the configured control-plane search provider.",
        parameters=WEB_EXTRACT_SCHEMA,
        handler=lambda urls, query="", extract_depth="basic", format="markdown", chunks_per_source=3: web_extract(
            context,
            active_web_provider,
            urls=urls,
            query=query,
            extract_depth=extract_depth,
            format=format,
            chunks_per_source=chunks_per_source,
        ),
        metadata={
            "risk": "medium",
            "requires_network": True,
            "external_disclosure": True,
            "provider": getattr(active_web_provider, "name", "none"),
        },
        read_only=True,
        activity_kind="web",
        activity_title="Extract web content",
        activity_target_argument="urls",
    )
    _register_builtin_tool(
        registry,
        name="web.map",
        description="Discover URLs under a site through the configured control-plane search provider.",
        parameters=WEB_MAP_SCHEMA,
        handler=lambda url, instructions="", max_depth=1, limit=50, include_domains=None, exclude_domains=None: web_map(
            context,
            active_web_provider,
            url=url,
            instructions=instructions,
            max_depth=max_depth,
            limit=limit,
            include_domains=include_domains,
            exclude_domains=exclude_domains,
        ),
        metadata={
            "risk": "high",
            "requires_network": True,
            "external_disclosure": True,
            "provider": getattr(active_web_provider, "name", "none"),
        },
        read_only=True,
        activity_kind="web",
        activity_title="Map site",
        activity_target_argument="url",
    )
