from importlib import import_module
from typing import Any


_EXPORT_MODULES = {
    "MCPAuthenticationRequired": "agents.kernel.mcp.types",
    "MCPClient": "agents.kernel.mcp.types",
    "MCPPromptArgumentDefinition": "agents.kernel.mcp.types",
    "MCPPromptDefinition": "agents.kernel.mcp.types",
    "MCPResourceDefinition": "agents.kernel.mcp.types",
    "MCPElicitationCompleteHandler": "agents.kernel.mcp.types",
    "MCPElicitationHandler": "agents.kernel.mcp.types",
    "MCPListChangedHandler": "agents.kernel.mcp.types",
    "MCPOAuthAuthenticator": "agents.kernel.mcp.types",
    "MCPServerConfig": "agents.kernel.mcp.types",
    "MCPToolDefinition": "agents.kernel.mcp.types",
    "MCPSDKControlClient": "agents.kernel.mcp.clients",
    "MCPSSEClient": "agents.kernel.mcp.clients",
    "MCPStdioClient": "agents.kernel.mcp.clients",
    "MCPStreamableHTTPClient": "agents.kernel.mcp.clients",
    "MCPWebSocketClient": "agents.kernel.mcp.clients",
    "MCPToolProvider": "agents.kernel.mcp.provider",
    "build_mcp_tool_name": "agents.kernel.mcp.naming",
    "mcp_info_from_name": "agents.kernel.mcp.naming",
    "normalize_mcp_name": "agents.kernel.mcp.naming",
}

__all__ = list(_EXPORT_MODULES)


def __getattr__(name: str) -> Any:
    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(name)
    value = getattr(import_module(module_name), name)
    globals()[name] = value
    return value
