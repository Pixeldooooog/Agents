# !/usr/bin/env python
# -*- coding: utf-8 -*-
# =====================================================
# @File   ：mcp.py
# @Date   ：2026/04/24 00:00
# @Author ：Zegen
#
# 2026/04/24   Create
# =====================================================

from __future__ import annotations

import inspect
import json
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Protocol

from agents.kernel.capabilities.tools.registry import ToolRegistry


_MCP_UNSAFE_NAME_RE = re.compile(r"[^a-zA-Z0-9_-]")
ALLOWED_IDE_TOOL_NAMES = {"mcp__ide__executeCode", "mcp__ide__getDiagnostics"}


class MCPElicitationHandler(Protocol):
    def __call__(self, server_name: str, params: Any) -> Any:
        raise NotImplementedError()


class MCPElicitationCompleteHandler(Protocol):
    def __call__(self, server_name: str, elicitation_id: str) -> Any:
        raise NotImplementedError()


class MCPListChangedHandler(Protocol):
    def __call__(self, server_name: str, kind: str) -> Any:
        raise NotImplementedError()


MCPSDKMessageHandler = Callable[[dict[str, Any]], Any]
MCPOAuthAuthenticator = Callable[[Any, Mapping[str, Any]], Any]


MCP_AUTHENTICATE_SCHEMA = {
    "type": "object",
    "properties": {
        "callback_url": {
            "type": "string",
            "description": "Full OAuth callback URL after browser authorization.",
        },
        "callbackUrl": {
            "type": "string",
            "description": "Full OAuth callback URL after browser authorization.",
        },
        "wait_for_callback": {
            "type": "boolean",
            "description": "Start a local loopback listener and complete OAuth automatically when the browser redirects.",
        },
        "waitForCallback": {
            "type": "boolean",
            "description": "Start a local loopback listener and complete OAuth automatically when the browser redirects.",
        },
        "open_browser": {
            "type": "boolean",
            "description": "Ask the host to open the authorization URL when a browser opener is available.",
        },
        "openBrowser": {
            "type": "boolean",
            "description": "Ask the host to open the authorization URL when a browser opener is available.",
        },
    },
}


@dataclass(frozen=True)
class MCPServerConfig:
    name: str
    command: str = ""
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    headers: Dict[str, str] = field(default_factory=dict)
    transport: str = "stdio"
    url: str = ""
    timeout_seconds: float = 30.0
    sse_read_timeout_seconds: float = 300.0
    execution_mode: str = "trusted_control_plane"
    sandbox_profile: str = ""
    auth_required: bool = False
    auth_url: str = ""
    auth_status: str = ""
    auth_message: str = ""
    roots: List[str] = field(default_factory=list)
    elicitation_handler: MCPElicitationHandler | None = None
    elicitation_complete_handler: MCPElicitationCompleteHandler | None = None
    list_changed_handler: MCPListChangedHandler | None = None
    sdk_message_handler: MCPSDKMessageHandler | None = None


@dataclass(frozen=True)
class MCPToolDefinition:
    name: str
    description: str
    parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MCPResourceDefinition:
    uri: str
    name: str = ""
    description: str = ""
    mime_type: str = ""


@dataclass(frozen=True)
class MCPPromptArgumentDefinition:
    name: str
    description: str = ""
    required: bool = False


@dataclass(frozen=True)
class MCPPromptDefinition:
    name: str
    description: str = ""
    arguments: List[MCPPromptArgumentDefinition] = field(default_factory=list)


class MCPClient(Protocol):
    async def list_tools(self) -> List[MCPToolDefinition]:
        raise NotImplementedError()

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        raise NotImplementedError()

    async def list_resources(self) -> List[MCPResourceDefinition]:
        raise NotImplementedError()

    async def read_resource(self, uri: str) -> Any:
        raise NotImplementedError()

    async def list_prompts(self) -> List[MCPPromptDefinition]:
        raise NotImplementedError()

    async def get_prompt(self, name: str, arguments: Dict[str, Any] | None = None) -> Any:
        raise NotImplementedError()

    async def close(self) -> None:
        raise NotImplementedError()


class MCPAuthenticationRequired(Exception):
    def __init__(
        self,
        message: str = "",
        *,
        auth_url: str = "",
        transport: str = "",
        url: str = "",
    ):
        super().__init__(message or "MCP server requires authentication")
        self.auth_url = str(auth_url or "")
        self.transport = str(transport or "")
        self.url = str(url or "")


class _MCPSessionClient:
    def __init__(self, server: MCPServerConfig):
        self.server = server
        self._transport_context: Optional[Any] = None
        self._session_context: Optional[Any] = None
        self._session: Optional[Any] = None

    async def initialize(self) -> None:
        if self._session is not None:
            return
        try:
            from mcp import ClientSession

            read, write = await self._open_transport()
            self._session_context = ClientSession(
                read,
                write,
                elicitation_callback=self._handle_elicitation,
                list_roots_callback=self._list_roots if self.server.roots else None,
                message_handler=self._handle_message,
            )
            self._session = await self._session_context.__aenter__()
            await self._session.initialize()
        except Exception as exc:
            await self.close()
            auth_error = _auth_error_from_exception(exc, self.server)
            if auth_error is not None:
                raise auth_error from exc
            raise

    async def _open_transport(self) -> tuple[Any, Any]:
        raise NotImplementedError()

    async def _list_roots(self, _context: Any) -> Any:
        from mcp import types

        return types.ListRootsResult(
            roots=[
                types.Root(uri=_root_uri(root), name=_root_name(root))
                for root in self.server.roots
            ]
        )

    async def _handle_elicitation(self, _context: Any, _params: Any) -> Any:
        if self.server.elicitation_handler is None:
            return _mcp_elicitation_result(None)
        response = self.server.elicitation_handler(self.server.name, _params)
        if inspect.isawaitable(response):
            response = await response
        return _mcp_elicitation_result(response)

    async def _handle_message(self, message: Any) -> None:
        root = getattr(message, "root", None)
        if root is None:
            return
        try:
            from mcp import types
        except Exception:
            return
        if isinstance(root, types.ElicitCompleteNotification):
            await self._handle_elicitation_complete(root)
            return
        kind = _list_changed_kind(root, types)
        if kind:
            await self._handle_list_changed(kind)

    async def _handle_elicitation_complete(self, root: Any) -> None:
        handler = self.server.elicitation_complete_handler
        if handler is None:
            return
        elicitation_id = str(getattr(root.params, "elicitationId", "") or "")
        response = handler(self.server.name, elicitation_id)
        if inspect.isawaitable(response):
            await response

    async def _handle_list_changed(self, kind: str) -> None:
        handler = self.server.list_changed_handler
        if handler is None:
            return
        response = handler(self.server.name, kind)
        if inspect.isawaitable(response):
            await response

    async def list_tools(self) -> List[MCPToolDefinition]:
        await self.initialize()
        response = await self._session.list_tools()
        raw_tools = getattr(response, "tools", None)
        if raw_tools is None:
            raw_tools = []
            for item in response:
                if isinstance(item, tuple) and item[0] == "tools":
                    raw_tools.extend(item[1])
        return [
            MCPToolDefinition(
                name=tool.name,
                description=getattr(tool, "description", "") or "",
                parameters=dict(getattr(tool, "inputSchema", None) or getattr(tool, "input_schema", None) or {}),
            )
            for tool in raw_tools
        ]

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        await self.initialize()
        result = await self._session.call_tool(name, arguments)
        return _format_mcp_result(result)

    async def list_resources(self) -> List[MCPResourceDefinition]:
        await self.initialize()
        response = await self._session.list_resources()
        raw_resources = getattr(response, "resources", None)
        if raw_resources is None:
            raw_resources = []
            for item in response:
                if isinstance(item, tuple) and item[0] == "resources":
                    raw_resources.extend(item[1])
        return [
            MCPResourceDefinition(
                uri=str(getattr(resource, "uri", "") or ""),
                name=str(getattr(resource, "name", "") or ""),
                description=str(getattr(resource, "description", "") or ""),
                mime_type=str(getattr(resource, "mimeType", None) or getattr(resource, "mime_type", "") or ""),
            )
            for resource in raw_resources
        ]

    async def read_resource(self, uri: str) -> Any:
        await self.initialize()
        result = await self._session.read_resource(uri)
        return _format_mcp_resource_result(result)

    async def list_prompts(self) -> List[MCPPromptDefinition]:
        await self.initialize()
        response = await self._session.list_prompts()
        raw_prompts = getattr(response, "prompts", None)
        if raw_prompts is None:
            raw_prompts = []
            for item in response:
                if isinstance(item, tuple) and item[0] == "prompts":
                    raw_prompts.extend(item[1])
        return [
            MCPPromptDefinition(
                name=str(getattr(prompt, "name", "") or ""),
                description=str(getattr(prompt, "description", "") or ""),
                arguments=_prompt_arguments(getattr(prompt, "arguments", []) or []),
            )
            for prompt in raw_prompts
        ]

    async def get_prompt(self, name: str, arguments: Dict[str, Any] | None = None) -> Any:
        await self.initialize()
        result = await self._session.get_prompt(name, arguments or {})
        return _format_mcp_prompt_result(result)

    async def close(self) -> None:
        if self._session_context is not None:
            await self._session_context.__aexit__(None, None, None)
            self._session_context = None
            self._session = None
        if self._transport_context is not None:
            await self._transport_context.__aexit__(None, None, None)
            self._transport_context = None


def _mcp_elicitation_result(response: Any) -> Any:
    from mcp import types

    if response is None:
        return types.ElicitResult(action="cancel")
    if isinstance(response, types.ElicitResult):
        return response
    if not isinstance(response, dict):
        raise TypeError("MCP elicitation handler must return a dict")
    action = str(response.get("action") or "cancel")
    if action not in {"accept", "decline", "cancel"}:
        raise ValueError("MCP elicitation action must be accept, decline, or cancel")
    content = response.get("content")
    if content is not None and not isinstance(content, dict):
        raise TypeError("MCP elicitation content must be a dict")
    return types.ElicitResult(
        action=action,
        content=dict(content) if content is not None else None,
    )


def _list_changed_kind(root: Any, types: Any) -> str:
    if isinstance(root, types.ToolListChangedNotification):
        return "tools"
    if isinstance(root, types.PromptListChangedNotification):
        return "prompts"
    if isinstance(root, types.ResourceListChangedNotification):
        return "resources"
    method = str(getattr(root, "method", "") or "")
    if method == "notifications/tools/list_changed":
        return "tools"
    if method == "notifications/prompts/list_changed":
        return "prompts"
    if method == "notifications/resources/list_changed":
        return "resources"
    return ""


class MCPStdioClient(_MCPSessionClient):
    async def _open_transport(self) -> tuple[Any, Any]:
        from mcp import StdioServerParameters
        from mcp.client.stdio import stdio_client

        command = shutil.which(self.server.command) if self.server.command else None
        command = command or self.server.command
        params = StdioServerParameters(
            command=command,
            args=self.server.args,
            env={**os.environ, **self.server.env} if self.server.env else None,
        )
        self._transport_context = stdio_client(params)
        return await self._transport_context.__aenter__()


class MCPStreamableHTTPClient(_MCPSessionClient):
    async def _open_transport(self) -> tuple[Any, Any]:
        from mcp.client.streamable_http import streamablehttp_client

        self._transport_context = streamablehttp_client(
            self.server.url,
            headers=dict(self.server.headers or {}) or None,
            timeout=self.server.timeout_seconds,
            sse_read_timeout=self.server.sse_read_timeout_seconds,
        )
        read, write, _get_session_id = await self._transport_context.__aenter__()
        return read, write


class MCPSSEClient(_MCPSessionClient):
    async def _open_transport(self) -> tuple[Any, Any]:
        from mcp.client.sse import sse_client

        self._transport_context = sse_client(
            self.server.url,
            headers=dict(self.server.headers or {}) or None,
            timeout=self.server.timeout_seconds,
            sse_read_timeout=self.server.sse_read_timeout_seconds,
        )
        return await self._transport_context.__aenter__()


class MCPWebSocketClient(_MCPSessionClient):
    async def _open_transport(self) -> tuple[Any, Any]:
        if self.server.headers:
            from agents.kernel.capabilities.tools.mcp_websocket import websocket_client_with_headers

            self._transport_context = websocket_client_with_headers(
                self.server.url,
                headers=self.server.headers,
            )
            return await self._transport_context.__aenter__()

        from mcp.client.websocket import websocket_client

        self._transport_context = websocket_client(self.server.url)
        return await self._transport_context.__aenter__()


class MCPSDKControlClient(_MCPSessionClient):
    async def _open_transport(self) -> tuple[Any, Any]:
        from agents.kernel.capabilities.tools.mcp_sdk import sdk_control_client

        if self.server.sdk_message_handler is None:
            raise RuntimeError("SDK MCP server is not registered: %s" % self.server.name)
        self._transport_context = sdk_control_client(self.server.sdk_message_handler)
        return await self._transport_context.__aenter__()


@dataclass(frozen=True)
class MCPToolProvider:
    client: MCPClient
    server: MCPServerConfig
    oauth_authenticator: MCPOAuthAuthenticator | None = None

    async def load_tools(self, registry: ToolRegistry) -> None:
        registered_names = set(registry.names()) if hasattr(registry, "names") else set()
        if self.server.auth_required:
            self._register_auth_tool(registry, registered_names)
            return
        try:
            tools = await self.client.list_tools()
        except MCPAuthenticationRequired as exc:
            self._register_auth_tool(
                registry,
                registered_names,
                auth_url=exc.auth_url,
                transport=exc.transport,
                url=exc.url,
                message=str(exc),
            )
            return
        for tool in tools:
            canonical_name = self._registry_name(tool.name)
            if not _is_included_mcp_tool(canonical_name):
                continue
            if canonical_name not in registered_names:
                registry.register(
                    canonical_name,
                    tool.description,
                    tool.parameters,
                    self._handler(tool.name),
                    metadata=self._metadata(tool.name),
                )
                registered_names.add(canonical_name)

            legacy_name = self._legacy_registry_name(tool.name)
            if legacy_name != canonical_name and legacy_name not in registered_names:
                registry.register(
                    legacy_name,
                    tool.description,
                    tool.parameters,
                    self._handler(tool.name),
                    metadata=self._metadata(tool.name, alias_of=canonical_name, legacy_name=True),
                )
                registered_names.add(legacy_name)

    def _register_auth_tool(
        self,
        registry: ToolRegistry,
        registered_names: set[str],
        *,
        auth_url: str = "",
        transport: str = "",
        url: str = "",
        message: str = "",
    ) -> None:
        remote_name = "authenticate"
        name = build_mcp_tool_name(self.server.name, remote_name)
        if name in registered_names:
            return
        location = _mcp_location(
            transport or self.server.transport,
            url or self.server.url,
        )
        description = (
            "The `%s` MCP server (%s) is installed but requires authentication. "
            "Call this tool to start or surface the authorization flow for the user."
        ) % (self.server.name, location)
        registry.register(
            name,
            description,
            MCP_AUTHENTICATE_SCHEMA,
            self._auth_handler(
                auth_url=auth_url,
                transport=transport,
                url=url,
                message=message,
            ),
            metadata=self._metadata(
                remote_name,
                auth_tool=True,
                requires_auth=True,
                transport=transport,
                url=url,
                concurrency_safe=False,
                max_result_size_chars=10000,
            ),
        )
        registered_names.add(name)

    def _registry_name(self, name: str) -> str:
        return build_mcp_tool_name(self.server.name, name)

    def _legacy_registry_name(self, name: str) -> str:
        return "mcp_%s_%s" % (self.server.name, name)

    def _metadata(
        self,
        remote_name: str,
        *,
        alias_of: str = "",
        legacy_name: bool = False,
        auth_tool: bool = False,
        requires_auth: bool = False,
        transport: str = "",
        url: str = "",
        concurrency_safe: bool | None = None,
        max_result_size_chars: int | None = None,
    ) -> Dict[str, Any]:
        metadata: Dict[str, Any] = {
            "source": "mcp",
            "server": self.server.name,
            "remote_name": remote_name,
            "transport": transport or self.server.transport,
            "url": url or self.server.url,
            "execution_mode": self.server.execution_mode,
            "sandbox_profile": self.server.sandbox_profile,
            "risk": "medium",
            "mcp_info": {
                "server": self.server.name,
                "remote_name": remote_name,
                "normalized_server": normalize_mcp_name(self.server.name),
                "normalized_tool": normalize_mcp_name(remote_name),
            },
        }
        if alias_of:
            metadata["alias_of"] = alias_of
        if legacy_name:
            metadata["legacy_name"] = True
        if auth_tool:
            metadata["auth_tool"] = True
        if requires_auth:
            metadata["requires_auth"] = True
        if concurrency_safe is not None:
            metadata["concurrency_safe"] = concurrency_safe
        if max_result_size_chars is not None:
            metadata["max_result_size_chars"] = max_result_size_chars
        return metadata

    def _handler(self, remote_name: str):
        async def call_remote(**arguments: Any) -> str:
            result = await self.client.call_tool(remote_name, dict(arguments))
            if isinstance(result, str):
                return result
            return json.dumps(result, ensure_ascii=False, sort_keys=True)

        return call_remote

    def _auth_handler(
        self,
        *,
        auth_url: str = "",
        transport: str = "",
        url: str = "",
        message: str = "",
    ):
        async def authenticate(
            callback_url: str = "",
            callbackUrl: str = "",
            wait_for_callback: bool = True,
            waitForCallback: bool = True,
            open_browser: bool = True,
            openBrowser: bool = True,
        ) -> str:
            callback_value = str(callback_url or callbackUrl or "").strip()
            auth_url_value = str(auth_url or self.server.auth_url or "")
            transport_value = str(transport or self.server.transport or "stdio")
            if self.oauth_authenticator is not None and transport_value in {"sse", "http"} and (
                callback_value or not auth_url_value
            ):
                payload = await self.oauth_authenticator(
                    self.server,
                    {
                        "callback_url": callback_value,
                        "auth_url": auth_url_value,
                        "transport": transport_value,
                        "url": str(url or self.server.url or ""),
                        "wait_for_callback": bool(wait_for_callback and waitForCallback),
                        "open_browser": bool(open_browser and openBrowser),
                    },
                )
                return json.dumps(payload, ensure_ascii=False, sort_keys=True)
            payload = self._auth_payload(
                auth_url=auth_url,
                transport=transport,
                url=url,
                message=message,
            )
            return json.dumps(payload, ensure_ascii=False, sort_keys=True)

        return authenticate

    def _auth_payload(
        self,
        *,
        auth_url: str = "",
        transport: str = "",
        url: str = "",
        message: str = "",
    ) -> Dict[str, Any]:
        transport_value = str(transport or self.server.transport or "stdio")
        url_value = str(url or self.server.url or "")
        auth_url_value = str(auth_url or self.server.auth_url or "")
        base_message = str(message or self.server.auth_message or "").strip()
        if transport_value == "claudeai-proxy":
            return {
                "status": "unsupported",
                "server": self.server.name,
                "transport": transport_value,
                "url": url_value,
                "message": base_message
                or 'This is a claude.ai MCP connector. Ask the user to run /mcp and authenticate "%s" manually.'
                % self.server.name,
            }
        if transport_value not in {"sse", "http"}:
            return {
                "status": "unsupported",
                "server": self.server.name,
                "transport": transport_value,
                "url": url_value,
                "message": base_message
                or 'Server "%s" uses %s transport which does not support OAuth from this tool. Ask the user to run /mcp and authenticate manually.'
                % (self.server.name, transport_value),
            }
        if not auth_url_value:
            return {
                "status": "error",
                "server": self.server.name,
                "transport": transport_value,
                "url": url_value,
                "message": base_message
                or "Failed to start OAuth flow for %s: no authorization URL is available. Ask the user to run /mcp and authenticate manually."
                % self.server.name,
            }
        return {
            "status": "auth_url",
            "server": self.server.name,
            "transport": transport_value,
            "url": url_value,
            "authUrl": auth_url_value,
            "auth_url": auth_url_value,
            "message": base_message
            or "Ask the user to open this URL in their browser to authorize the %s MCP server:\n\n%s\n\nOnce they complete the flow, the server's tools will become available automatically."
            % (self.server.name, auth_url_value),
        }

    async def list_resources(self) -> List[MCPResourceDefinition]:
        list_resources = getattr(self.client, "list_resources", None)
        if list_resources is None:
            return []
        return await list_resources()

    async def read_resource(self, uri: str) -> Any:
        read_resource = getattr(self.client, "read_resource", None)
        if read_resource is None:
            raise RuntimeError("MCP server does not support resources")
        return await read_resource(uri)

    async def list_prompts(self) -> List[MCPPromptDefinition]:
        list_prompts = getattr(self.client, "list_prompts", None)
        if list_prompts is None:
            return []
        return await list_prompts()

    async def get_prompt(self, name: str, arguments: Dict[str, Any] | None = None) -> Any:
        get_prompt = getattr(self.client, "get_prompt", None)
        if get_prompt is None:
            raise RuntimeError("MCP server does not support prompts")
        return await get_prompt(name, arguments or {})

    async def close(self) -> None:
        close = getattr(self.client, "close", None)
        if close is not None:
            await close()


def normalize_mcp_name(name: str) -> str:
    value = str(name or "")
    normalized = _MCP_UNSAFE_NAME_RE.sub("_", value)
    if value.startswith("claude.ai "):
        normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized or "unnamed"


def build_mcp_tool_name(server_name: str, tool_name: str) -> str:
    return "mcp__%s__%s" % (normalize_mcp_name(server_name), normalize_mcp_name(tool_name))


def _is_included_mcp_tool(name: str) -> bool:
    return not name.startswith("mcp__ide__") or name in ALLOWED_IDE_TOOL_NAMES


def mcp_info_from_name(name: str) -> Dict[str, str] | None:
    value = str(name or "")
    if not value.startswith("mcp__"):
        return None
    parts = value[len("mcp__") :].split("__", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        return None
    return {"server": parts[0], "tool": parts[1]}


def _mcp_location(transport: str, url: str) -> str:
    transport_value = str(transport or "stdio")
    url_value = str(url or "").strip()
    return "%s at %s" % (transport_value, url_value) if url_value else transport_value


def _root_uri(root: str) -> str:
    value = str(root or "").strip()
    if value.startswith("file://"):
        return value
    return Path(value).expanduser().resolve().as_uri()


def _root_name(root: str) -> str:
    value = str(root or "").strip()
    if value.startswith("file://"):
        return Path(value.removeprefix("file://")).name or value
    return Path(value).expanduser().name or value


def _auth_error_from_exception(exc: Exception, server: MCPServerConfig) -> MCPAuthenticationRequired | None:
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    if status_code == 401:
        return MCPAuthenticationRequired(
            "MCP server %s requires authentication" % server.name,
            transport=server.transport,
            url=server.url,
        )
    return None


def _format_mcp_result(result: Any) -> Any:
    content = getattr(result, "content", None)
    if content is None and isinstance(result, dict):
        content = result.get("content")
    if not content:
        return result
    parts: List[str] = []
    for item in content:
        item_type = getattr(item, "type", None) or (item.get("type") if isinstance(item, dict) else "")
        if item_type == "text":
            parts.append(getattr(item, "text", None) or item.get("text", ""))
        else:
            parts.append(json.dumps(item, ensure_ascii=False, sort_keys=True, default=str))
    return "\n".join(part for part in parts if part)


def _format_mcp_resource_result(result: Any) -> Any:
    contents = getattr(result, "contents", None)
    if contents is None and isinstance(result, dict):
        contents = result.get("contents")
    if contents is None:
        return result
    formatted = []
    for item in contents:
        if isinstance(item, dict):
            formatted.append(dict(item))
            continue
        payload = {
            "uri": str(getattr(item, "uri", "") or ""),
            "mimeType": str(getattr(item, "mimeType", None) or getattr(item, "mime_type", "") or ""),
        }
        if hasattr(item, "text"):
            payload["text"] = getattr(item, "text")
        if hasattr(item, "blob"):
            payload["blob"] = getattr(item, "blob")
        formatted.append(payload)
    return {"contents": formatted}


def _prompt_arguments(raw_arguments: Any) -> List[MCPPromptArgumentDefinition]:
    arguments: List[MCPPromptArgumentDefinition] = []
    for argument in raw_arguments or []:
        if isinstance(argument, dict):
            arguments.append(
                MCPPromptArgumentDefinition(
                    name=str(argument.get("name") or ""),
                    description=str(argument.get("description") or ""),
                    required=bool(argument.get("required")),
                )
            )
            continue
        arguments.append(
            MCPPromptArgumentDefinition(
                name=str(getattr(argument, "name", "") or ""),
                description=str(getattr(argument, "description", "") or ""),
                required=bool(getattr(argument, "required", False)),
            )
        )
    return arguments


def _format_mcp_prompt_result(result: Any) -> Any:
    if isinstance(result, dict):
        description = result.get("description", "")
        messages = result.get("messages", [])
    else:
        description = getattr(result, "description", "") or ""
        messages = getattr(result, "messages", []) or []
    return {
        "description": str(description or ""),
        "messages": [_prompt_message_payload(message) for message in messages],
    }


def _prompt_message_payload(message: Any) -> dict[str, Any]:
    if isinstance(message, dict):
        role = str(message.get("role") or "")
        content = message.get("content")
    else:
        role = str(getattr(message, "role", "") or "")
        content = getattr(message, "content", None)
    return {"role": role, "content": _prompt_content_payload(content)}


def _prompt_content_payload(content: Any) -> Any:
    if content is None or isinstance(content, (str, int, float, bool, list, dict)):
        return content
    payload = {"type": str(getattr(content, "type", "") or "")}
    for field_name in ["text", "blob", "mimeType", "mime_type", "uri", "name", "description"]:
        if hasattr(content, field_name):
            payload[field_name] = getattr(content, field_name)
    return {key: value for key, value in payload.items() if value not in ("", None)}
