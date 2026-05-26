from __future__ import annotations

import json
import time
from typing import Any

from agents.kernel.capabilities.tools.context import ToolRuntimeContext
from agents.kernel.capabilities.web import (
    WebExtractRequest,
    WebMapRequest,
    WebSearchProvider,
    WebSearchRequest,
)


WEB_SEARCH_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "Search query."},
        "topic": {"type": "string", "enum": ["general", "news", "finance"]},
        "search_depth": {"type": "string", "enum": ["basic", "advanced", "fast", "ultra_fast"]},
        "max_results": {"type": "integer", "minimum": 1, "maximum": 10},
        "time_range": {"type": "string", "description": "Optional recency range such as day, week, month, or year."},
        "include_domains": {"type": "array", "items": {"type": "string"}},
        "exclude_domains": {"type": "array", "items": {"type": "string"}},
        "country": {"type": "string"},
        "include_answer": {"type": "boolean"},
        "include_raw_content": {"type": "boolean"},
        "chunks_per_source": {"type": "integer", "minimum": 1, "maximum": 10},
    },
    "required": ["query"],
}

SRC_ORIGIN_WEB_SEARCH_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "The search query to use."},
        "allowed_domains": {"type": "array", "items": {"type": "string"}},
        "blocked_domains": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["query"],
    "additionalProperties": False,
}

SRC_ORIGIN_WEB_FETCH_SCHEMA = {
    "type": "object",
    "properties": {
        "url": {"type": "string", "description": "The URL to fetch content from."},
        "prompt": {"type": "string", "description": "The prompt to run on the fetched content."},
    },
    "required": ["url", "prompt"],
    "additionalProperties": False,
}

WEB_EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "urls": {"type": "array", "items": {"type": "string"}},
        "query": {"type": "string", "description": "Optional extraction intent used for reranking chunks."},
        "extract_depth": {"type": "string", "enum": ["basic", "advanced"]},
        "format": {"type": "string", "enum": ["markdown", "text"]},
        "chunks_per_source": {"type": "integer", "minimum": 1, "maximum": 10},
    },
    "required": ["urls"],
}

WEB_MAP_SCHEMA = {
    "type": "object",
    "properties": {
        "url": {"type": "string", "description": "Root URL to map."},
        "instructions": {"type": "string"},
        "max_depth": {"type": "integer", "minimum": 1, "maximum": 5},
        "limit": {"type": "integer", "minimum": 1, "maximum": 500},
        "include_domains": {"type": "array", "items": {"type": "string"}},
        "exclude_domains": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["url"],
}


async def web_search(
    context: ToolRuntimeContext,
    provider: WebSearchProvider,
    query: str,
    topic: str = "general",
    search_depth: str = "basic",
    max_results: int = 5,
    time_range: str = "",
    include_domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
    country: str = "",
    include_answer: bool = False,
    include_raw_content: bool = False,
    chunks_per_source: int = 3,
) -> dict[str, Any]:
    result = await provider.search(
        WebSearchRequest(
            query=query,
            topic=topic,
            search_depth=search_depth,
            max_results=max_results,
            time_range=time_range,
            include_domains=tuple(include_domains or ()),
            exclude_domains=tuple(exclude_domains or ()),
            country=country,
            include_answer=include_answer,
            include_raw_content=include_raw_content,
            chunks_per_source=chunks_per_source,
        ),
        run_id=context.current_run_id,
    )
    return result.to_dict()


async def web_extract(
    context: ToolRuntimeContext,
    provider: WebSearchProvider,
    urls: list[str],
    query: str = "",
    extract_depth: str = "basic",
    format: str = "markdown",
    chunks_per_source: int = 3,
) -> dict[str, Any]:
    result = await provider.extract(
        WebExtractRequest(
            urls=tuple(urls or ()),
            query=query,
            extract_depth=extract_depth,
            format=format,
            chunks_per_source=chunks_per_source,
        ),
        run_id=context.current_run_id,
    )
    return result.to_dict()


async def web_map(
    context: ToolRuntimeContext,
    provider: WebSearchProvider,
    url: str,
    instructions: str = "",
    max_depth: int = 1,
    limit: int = 50,
    include_domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
) -> dict[str, Any]:
    result = await provider.map(
        WebMapRequest(
            url=url,
            instructions=instructions,
            max_depth=max_depth,
            limit=limit,
            include_domains=tuple(include_domains or ()),
            exclude_domains=tuple(exclude_domains or ()),
        ),
        run_id=context.current_run_id,
    )
    return result.to_dict()


async def src_origin_web_search(
    context: ToolRuntimeContext,
    provider: WebSearchProvider,
    *,
    query: str,
    allowed_domains: list[str] | None = None,
    blocked_domains: list[str] | None = None,
) -> dict[str, Any]:
    if allowed_domains and blocked_domains:
        raise ValueError("Cannot specify both allowed_domains and blocked_domains")
    started_at = time.perf_counter()
    payload = await web_search(
        context,
        provider,
        query=query,
        include_domains=allowed_domains,
        exclude_domains=blocked_domains,
    )
    payload["results"] = _src_origin_search_results(payload)
    payload["durationSeconds"] = _duration_seconds(payload, started_at)
    return payload


async def src_origin_web_fetch(
    context: ToolRuntimeContext,
    provider: WebSearchProvider,
    *,
    url: str,
    prompt: str,
) -> dict[str, Any]:
    started_at = time.perf_counter()
    payload = await web_extract(
        context,
        provider,
        urls=[url],
        query=prompt,
        extract_depth="basic",
        format="markdown",
    )
    result = _src_origin_fetch_result(payload)
    payload.update(
        {
            "bytes": len(result.encode("utf-8")),
            "code": 200 if result else 204,
            "codeText": "OK" if result else "No Content",
            "result": result,
            "durationMs": int(_duration_seconds(payload, started_at) * 1000),
            "url": url,
        }
    )
    return payload


def format_src_origin_web_search_result(result: Any) -> str:
    payload = result if isinstance(result, dict) else {}
    query = str(payload.get("query") or "")
    parts = ['Web search results for query: "%s"' % query, ""]
    for item in payload.get("results") or []:
        if item is None:
            continue
        if isinstance(item, str):
            if item:
                parts.extend([item, ""])
            continue
        if isinstance(item, dict):
            content = item.get("content")
            if content:
                parts.extend(["Links: %s" % json.dumps(content, ensure_ascii=False), ""])
            else:
                parts.extend(["No links found.", ""])
    parts.append("REMINDER: You MUST include the sources above in your response to the user using markdown hyperlinks.")
    return "\n".join(parts).strip()


def format_src_origin_web_fetch_result(result: Any) -> str:
    payload = result if isinstance(result, dict) else {}
    if "result" in payload:
        return str(payload.get("result") or "")
    return _src_origin_fetch_result(payload)


def _src_origin_search_results(payload: dict[str, Any]) -> list[Any]:
    results: list[Any] = []
    answer = str(payload.get("provider_answer") or "").strip()
    if answer:
        results.append(answer)
    links = []
    for source in payload.get("sources") or []:
        if not isinstance(source, dict):
            continue
        title = str(source.get("title") or source.get("url") or "")
        url = str(source.get("url") or "")
        if title and url:
            links.append({"title": title, "url": url})
    if links:
        results.append({"tool_use_id": str(payload.get("request_id") or "web_search"), "content": links})
    return results


def _src_origin_fetch_result(payload: dict[str, Any]) -> str:
    chunks = []
    for source in payload.get("sources") or []:
        if not isinstance(source, dict):
            continue
        content = str(source.get("content") or source.get("raw_content") or "").strip()
        if content:
            chunks.append(content)
    if chunks:
        return "\n\n".join(chunks)
    failed = payload.get("failed_results") or []
    if failed:
        return json.dumps(failed, ensure_ascii=False)
    return ""


def _duration_seconds(payload: dict[str, Any], started_at: float) -> float:
    response_time = payload.get("response_time")
    if isinstance(response_time, (int, float)) and response_time >= 0:
        return float(response_time)
    return max(0.0, time.perf_counter() - started_at)
