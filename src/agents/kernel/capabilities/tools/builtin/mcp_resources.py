from __future__ import annotations

from typing import Any

from agents.kernel.capabilities.tools.context import ToolRuntimeContext


MCP_RESOURCES_SCHEMA = {
    "type": "object",
    "properties": {
        "server": {"type": "string", "description": "Optional MCP server name filter."},
        "uri_prefix": {"type": "string", "description": "Optional URI prefix filter."},
        "max_results": {"type": "integer", "minimum": 1, "maximum": 100},
    },
}

MCP_READ_RESOURCE_SCHEMA = {
    "type": "object",
    "properties": {
        "uri": {"type": "string", "description": "Resource URI to read."},
        "server": {"type": "string", "description": "Optional MCP server name."},
    },
    "required": ["uri"],
}


async def mcp_resources(
    context: ToolRuntimeContext,
    server: str = "",
    uri_prefix: str = "",
    max_results: int = 50,
) -> dict[str, Any]:
    resources: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for provider in _providers(context, server=server):
        try:
            for resource in await provider.list_resources():
                payload = _resource_payload(provider, resource)
                if uri_prefix and not str(payload.get("uri", "")).startswith(uri_prefix):
                    continue
                resources.append(payload)
        except Exception as exc:  # noqa: BLE001 - model should see unavailable resource servers.
            errors.append({"server": provider.server.name, "error": str(exc)})
    limit = max(1, min(int(max_results or 50), 100))
    return {
        "resources": resources[:limit],
        "count": min(len(resources), limit),
        "total": len(resources),
        "errors": errors,
    }


async def mcp_read_resource(context: ToolRuntimeContext, uri: str, server: str = "") -> dict[str, Any]:
    target_uri = _required_text(uri, "uri")
    errors: list[dict[str, str]] = []
    for provider in _providers(context, server=server):
        try:
            return {
                "server": provider.server.name,
                "uri": target_uri,
                "content": await provider.read_resource(target_uri),
            }
        except Exception as exc:  # noqa: BLE001 - try the next matching server when server is omitted.
            errors.append({"server": provider.server.name, "error": str(exc)})
            if server:
                break
    if not _providers(context, server=server):
        raise RuntimeError("no MCP server resources available")
    raise RuntimeError("failed to read MCP resource %s: %s" % (target_uri, errors))


def _providers(context: ToolRuntimeContext, server: str = "") -> list[Any]:
    wanted = str(server or "").strip()
    providers = list(getattr(context, "mcp_providers", []) or [])
    if wanted:
        providers = [provider for provider in providers if getattr(getattr(provider, "server", None), "name", "") == wanted]
    return providers


def _resource_payload(provider: Any, resource: Any) -> dict[str, Any]:
    return {
        "server": provider.server.name,
        "uri": str(getattr(resource, "uri", "") or ""),
        "name": str(getattr(resource, "name", "") or ""),
        "description": str(getattr(resource, "description", "") or ""),
        "mimeType": str(getattr(resource, "mime_type", "") or getattr(resource, "mimeType", "") or ""),
    }


def _required_text(value: Any, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError("%s is required" % name)
    return text
