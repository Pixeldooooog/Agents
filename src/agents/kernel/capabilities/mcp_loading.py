from __future__ import annotations

import json
import shlex
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from agents.kernel.capabilities.tools.mcp import (
    MCPElicitationHandler,
    MCPSSEClient,
    MCPSDKControlClient,
    MCPServerConfig,
    MCPStdioClient,
    MCPStreamableHTTPClient,
    MCPToolProvider,
    MCPWebSocketClient,
)
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


async def load_configured_mcp(
    settings: Any,
    registry: ToolRegistry,
    roots: list[str] | None = None,
    elicitation_handler: MCPElicitationHandler | None = None,
    sdk_mcp_handlers: Mapping[str, Any] | None = None,
    records: list[Any] | None = None,
) -> list[MCPToolProvider]:
    roots = _normalize_roots(roots)
    servers = _servers_from_records(
        settings,
        records,
        roots=roots,
        elicitation_handler=elicitation_handler,
        sdk_mcp_handlers=sdk_mcp_handlers,
    )
    if records is None:
        settings_server = _server_from_settings(
            settings,
            roots=roots,
            elicitation_handler=elicitation_handler,
            sdk_mcp_handlers=sdk_mcp_handlers,
        )
        servers = [settings_server] if settings_server is not None else []

    providers: list[MCPToolProvider] = []
    for server in servers:
        provider = MCPToolProvider(client=_client_for_server(server), server=server)
        await provider.load_tools(registry)
        providers.append(provider)
    return providers


def _server_from_settings(
    settings: Any,
    *,
    roots: list[str],
    elicitation_handler: MCPElicitationHandler | None,
    sdk_mcp_handlers: Mapping[str, Any] | None,
) -> MCPServerConfig | None:
    command = str(settings.mcp.SERVER_COMMAND or "").strip()
    transport = str(getattr(settings.mcp, "SERVER_TRANSPORT", "stdio") or "stdio")
    url = str(getattr(settings.mcp, "SERVER_URL", "") or "").strip()
    auth_required = bool(getattr(settings.mcp, "AUTH_REQUIRED", False))
    if transport == "stdio" and not command:
        return None
    if transport not in {"stdio", "sdk"} and not url:
        return None
    command_parts = shlex.split(command) if command else []
    return MCPServerConfig(
        name=settings.mcp.SERVER_NAME or "default",
        command=command_parts[0] if command_parts else "",
        args=command_parts[1:],
        headers=_headers_from_settings(settings.mcp),
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
        roots=roots,
        elicitation_handler=elicitation_handler,
        sdk_message_handler=_sdk_handler_for(settings.mcp.SERVER_NAME or "default", sdk_mcp_handlers),
    )


def _servers_from_records(
    settings: Any,
    records: list[Any] | None,
    *,
    roots: list[str],
    elicitation_handler: MCPElicitationHandler | None,
    sdk_mcp_handlers: Mapping[str, Any] | None,
) -> list[MCPServerConfig]:
    if records is None:
        return []
    return [
        _server_from_record(
            settings,
            record,
            roots=roots,
            elicitation_handler=elicitation_handler,
            sdk_mcp_handlers=sdk_mcp_handlers,
        )
        for record in records
        if bool(getattr(record, "enabled", True))
    ]


def _server_from_record(
    settings: Any,
    record: Any,
    *,
    roots: list[str],
    elicitation_handler: MCPElicitationHandler | None,
    sdk_mcp_handlers: Mapping[str, Any] | None,
) -> MCPServerConfig:
    command = str(getattr(record, "command", "") or "").strip()
    command_parts = shlex.split(command) if command else []
    return MCPServerConfig(
        name=str(getattr(record, "name", "") or "default"),
        command=command_parts[0] if command_parts else "",
        args=command_parts[1:],
        headers={str(key): str(value) for key, value in dict(getattr(record, "headers", {}) or {}).items()},
        timeout_seconds=getattr(settings.mcp, "CLIENT_TIMEOUT", 30.0),
        sse_read_timeout_seconds=getattr(settings.mcp, "SSE_READ_TIMEOUT", 300.0),
        transport=str(getattr(record, "transport", "stdio") or "stdio"),
        url=str(getattr(record, "url", "") or ""),
        execution_mode=str(getattr(record, "execution_mode", "") or "trusted_control_plane"),
        sandbox_profile=str(getattr(record, "sandbox_profile", "") or ""),
        auth_required=bool(getattr(record, "auth_required", False)),
        auth_url=str(getattr(record, "auth_url", "") or ""),
        auth_status=str(getattr(record, "auth_status", "") or ""),
        auth_message=str(getattr(record, "auth_message", "") or ""),
        roots=roots,
        elicitation_handler=elicitation_handler,
        sdk_message_handler=_sdk_handler_for(str(getattr(record, "name", "") or "default"), sdk_mcp_handlers),
    )


def _client_for_server(server: MCPServerConfig) -> Any:
    transport = server.transport
    if transport == "stdio":
        client = MCPStdioClient(server)
    elif transport == "http":
        client = MCPStreamableHTTPClient(server)
    elif transport == "sse":
        client = MCPSSEClient(server)
    elif transport == "ws":
        client = MCPWebSocketClient(server)
    elif transport == "sdk":
        if server.sdk_message_handler is None:
            raise RuntimeError("MCP sdk transport requires a registered SDK MCP handler: %s" % server.name)
        client = MCPSDKControlClient(server)
    else:
        client = _UnavailableMCPClient()
        if not server.auth_required:
            raise RuntimeError("MCP %s transport is not implemented yet" % transport)
    return client


def _sdk_handler_for(name: str, handlers: Mapping[str, Any] | None) -> Any | None:
    if not handlers:
        return None
    return handlers.get(str(name or "").strip())


def _normalize_roots(roots: list[str] | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for root in roots or []:
        value = str(root or "").strip()
        if not value:
            continue
        if not value.startswith("file://"):
            value = str(Path(value).expanduser().resolve())
        if value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


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
