from __future__ import annotations

from agents.kernel.capabilities.tools.context import ToolRuntimeContext


def validate_src_origin_required_mcp_servers(
    context: ToolRuntimeContext,
    *,
    agent_id: str,
    required_servers: tuple[str, ...],
) -> None:
    required = tuple(server.strip() for server in required_servers if server.strip())
    if not required:
        return
    available = _mcp_servers_with_tools(context)
    missing = [
        server
        for server in required
        if not any(server.lower() in available_server.lower() for available_server in available)
    ]
    if not missing:
        return
    suffix = ", ".join(available) if available else "none"
    raise ValueError(
        "Agent '%s' requires MCP servers matching: %s. MCP servers with tools: %s. "
        "Use /mcp to configure and authenticate the required MCP servers."
        % (agent_id, ", ".join(missing), suffix)
    )


def _mcp_servers_with_tools(context: ToolRuntimeContext) -> list[str]:
    servers: set[str] = set()
    for tool_name in getattr(context, "enabled_tools", []) or []:
        parts = str(tool_name or "").split("__")
        if len(parts) >= 3 and parts[0] == "mcp" and parts[1]:
            servers.add(parts[1])
    return sorted(servers)
