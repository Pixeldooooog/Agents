from __future__ import annotations

import shlex
from typing import Any

from agents.kernel.capabilities.tools.mcp import MCPServerConfig, MCPStdioClient, MCPToolProvider
from agents.kernel.capabilities.tools.registry import ToolRegistry


async def load_configured_mcp(settings: Any, registry: ToolRegistry) -> list[MCPToolProvider]:
    command = str(settings.mcp.SERVER_COMMAND or "").strip()
    if not command:
        return []
    command_parts = shlex.split(command)
    server = MCPServerConfig(
        name=settings.mcp.SERVER_NAME or "default",
        command=command_parts[0],
        args=command_parts[1:],
        timeout_seconds=settings.mcp.CLIENT_TIMEOUT,
        execution_mode=getattr(settings.mcp, "EXECUTION_MODE", "trusted_control_plane") or "trusted_control_plane",
        sandbox_profile=getattr(settings.mcp, "SANDBOX_PROFILE", "") or "",
    )
    provider = MCPToolProvider(client=MCPStdioClient(server), server=server)
    await provider.load_tools(registry)
    return [provider]
