from __future__ import annotations

import json
import shlex
from typing import Any

from agents.kernel.capabilities.tools.mcp import MCPSSEClient, MCPServerConfig, MCPStdioClient, MCPStreamableHTTPClient, MCPToolProvider
from agents.kernel.capabilities.tools.registry import ToolRegistry


class _UnavailableMCPClient:
    async def list_tools(self):
        return []

    async def call_tool(self, name, arguments):
        raise RuntimeError("MCP transport client is not available")

    async def list_resources(self):
        return []

    async def read_resource(self, uri):
        raise RuntimeError("MCP transport client is not available")

    async def list_prompts(self):
        return []

    async def get_prompt(self, name, arguments=None):
        raise RuntimeError("MCP transport client is not available")

    async def close(self):
        return None


async def load_configured_mcp(settings: Any, registry: ToolRegistry) -> list[MCPToolProvider]:
    command = str(settings.mcp.SERVER_COMMAND or "").strip()
    transport = str(getattr(settings.mcp, "SERVER_TRANSPORT", "stdio") or "stdio")
    url = str(getattr(settings.mcp, "SERVER_URL", "") or "").strip()
    auth_required = bool(getattr(settings.mcp, "AUTH_REQUIRED", False))
    headers = _headers_from_settings(settings.mcp)
    if transport == "stdio" and not command:
        return []
    if transport != "stdio" and not url:
        return []
    command_parts = shlex.split(command) if command else []
    server = MCPServerConfig(
        name=settings.mcp.SERVER_NAME or "default",
        command=command_parts[0] if command_parts else "",
        args=command_parts[1:],
        headers=headers,
        timeout_seconds=getattr(settings.mcp, "CLIENT_TIMEOUT", 30.0),
        sse_read_timeout_seconds=getattr(settings.mcp, "SSE_READ_TIMEOUT", 300.0),
        transport=transport,
        url=url,
        execution_mode=getattr(settings.mcp, "EXECUTION_MODE", "trusted_control_plane") or "trusted_control_plane",
        sandbox_profile=getattr(settings.mcp, "SANDBOX_PROFILE", "") or "",
        auth_required=auth_required,
        auth_url=getattr(settings.mcp, "AUTH_URL", "") or "",
        auth_status=getattr(settings.mcp, "AUTH_STATUS", "") or "",
        auth_message=getattr(settings.mcp, "AUTH_MESSAGE", "") or "",
    )
    if transport == "stdio":
        client = MCPStdioClient(server)
    elif transport == "http":
        client = MCPStreamableHTTPClient(server)
    elif transport == "sse":
        client = MCPSSEClient(server)
    else:
        client = _UnavailableMCPClient()
        if not auth_required:
            raise RuntimeError("MCP %s transport is not implemented yet" % transport)
    provider = MCPToolProvider(client=client, server=server)
    await provider.load_tools(registry)
    return [provider]


def _headers_from_settings(mcp_settings: Any) -> dict[str, str]:
    raw = getattr(mcp_settings, "SERVER_HEADERS", None)
    if isinstance(raw, dict):
        return {str(key): str(value) for key, value in raw.items()}
    raw_json = getattr(mcp_settings, "SERVER_HEADERS_JSON", "")
    if not raw_json:
        return {}
    try:
        parsed = json.loads(str(raw_json))
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {str(key): str(value) for key, value in parsed.items()}
