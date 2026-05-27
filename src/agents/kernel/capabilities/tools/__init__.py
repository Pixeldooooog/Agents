# !/usr/bin/env python
# -*- coding: utf-8 -*-
# =====================================================
# @File   ：__init__.py
# @Date   ：2026/04/24 00:00
# @Author ：Zegen
#
# 2026/04/24   Create
# =====================================================

from agents.kernel.capabilities.tools.builtin import register_builtin_tools
from agents.kernel.capabilities.tools.contracts import RegisteredTool, ToolActivity, ToolDefinition, ToolExecutionError
from agents.kernel.capabilities.tools.context import ToolRuntimeContext
from agents.kernel.capabilities.tools.recording import ToolExecutionObserver, ToolExecutionScope
from agents.kernel.capabilities.tools.registry import ToolRegistry

_MCP_EXPORTS = {
    "MCPAuthenticationRequired",
    "MCPClient",
    "MCPPromptArgumentDefinition",
    "MCPPromptDefinition",
    "MCPResourceDefinition",
    "MCPServerConfig",
    "MCPSDKControlClient",
    "MCPSSEClient",
    "MCPStdioClient",
    "MCPStreamableHTTPClient",
    "MCPToolDefinition",
    "MCPToolProvider",
    "MCPWebSocketClient",
    "build_mcp_tool_name",
    "mcp_info_from_name",
    "normalize_mcp_name",
}

__all__ = [
    "MCPClient",
    "MCPAuthenticationRequired",
    "MCPPromptArgumentDefinition",
    "MCPPromptDefinition",
    "MCPServerConfig",
    "MCPSSEClient",
    "MCPSDKControlClient",
    "MCPStdioClient",
    "MCPStreamableHTTPClient",
    "MCPWebSocketClient",
    "MCPResourceDefinition",
    "MCPToolDefinition",
    "MCPToolProvider",
    "build_mcp_tool_name",
    "mcp_info_from_name",
    "normalize_mcp_name",
    "RegisteredTool",
    "ToolActivity",
    "ToolDefinition",
    "ToolExecutionError",
    "ToolRuntimeContext",
    "ToolRegistry",
    "ToolExecutionObserver",
    "ToolExecutionScope",
    "register_builtin_tools",
]


def __getattr__(name: str):
    if name in _MCP_EXPORTS:
        from agents.kernel import mcp

        return getattr(mcp, name)
    raise AttributeError(name)
