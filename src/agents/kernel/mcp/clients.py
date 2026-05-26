from __future__ import annotations

import inspect
import os
import shutil
from pathlib import Path
from typing import Any, List, Optional

from agents.kernel.mcp.results import (
    format_mcp_prompt_result,
    format_mcp_resource_result,
    format_mcp_result,
    prompt_arguments,
)
from agents.kernel.mcp.types import (
    MCPAuthenticationRequired,
    MCPPromptDefinition,
    MCPResourceDefinition,
    MCPServerConfig,
    MCPToolDefinition,
)


IDE_TRANSPORTS = {"sse-ide", "ws-ide"}
IDE_CONNECTED_METHOD = "ide_connected"


class _MCPSessionClient:
    def __init__(self, server: MCPServerConfig):
        self.server = server
        self._transport_context: Optional[Any] = None
        self._session_context: Optional[Any] = None
        self._session: Optional[Any] = None
        self._write_stream: Optional[Any] = None

    async def initialize(self) -> None:
        if self._session is not None:
            return
        try:
            from mcp import ClientSession

            read, write = await self._open_transport()
            self._write_stream = write
            self._session_context = ClientSession(
                read,
                write,
                elicitation_callback=self._handle_elicitation,
                list_roots_callback=self._list_roots if self.server.roots else None,
                message_handler=self._handle_message,
            )
            self._session = await self._session_context.__aenter__()
            await self._session.initialize()
            await self._maybe_notify_ide_connected()
        except Exception as exc:
            await self.close()
            auth_error = _auth_error_from_exception(exc, self.server)
            if auth_error is not None:
                raise auth_error from exc
            raise

    async def _open_transport(self) -> tuple[Any, Any]:
        raise NotImplementedError()

    async def _maybe_notify_ide_connected(self) -> None:
        if self.server.transport not in IDE_TRANSPORTS or self._write_stream is None:
            return
        try:
            from mcp import types
            from mcp.shared.message import SessionMessage

            await self._write_stream.send(
                SessionMessage(
                    message=types.JSONRPCMessage(
                        types.JSONRPCNotification(
                            jsonrpc="2.0",
                            method=IDE_CONNECTED_METHOD,
                            params={"pid": os.getpid()},
                        )
                    )
                )
            )
        except Exception:
            return

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
        return format_mcp_result(result)

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
        return format_mcp_resource_result(result)

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
                arguments=prompt_arguments(getattr(prompt, "arguments", []) or []),
            )
            for prompt in raw_prompts
        ]

    async def get_prompt(self, name: str, arguments: Dict[str, Any] | None = None) -> Any:
        await self.initialize()
        result = await self._session.get_prompt(name, arguments or {})
        return format_mcp_prompt_result(result)

    async def close(self) -> None:
        if self._session_context is not None:
            await self._session_context.__aexit__(None, None, None)
            self._session_context = None
            self._session = None
        if self._transport_context is not None:
            await self._transport_context.__aexit__(None, None, None)
            self._transport_context = None
        self._write_stream = None


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
            from agents.kernel.mcp.transports.websocket import websocket_client_with_headers

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
        from agents.kernel.mcp.transports.sdk_control import sdk_control_client

        if self.server.sdk_message_handler is None:
            raise RuntimeError("SDK MCP server is not registered: %s" % self.server.name)
        self._transport_context = sdk_control_client(self.server.sdk_message_handler)
        return await self._transport_context.__aenter__()




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
