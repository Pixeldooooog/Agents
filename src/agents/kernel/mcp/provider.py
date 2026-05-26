from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List

from agents.kernel.capabilities.tools.registry import ToolRegistry
from agents.kernel.mcp.naming import (
    build_mcp_tool_name,
    is_included_mcp_tool,
    mcp_location,
    normalize_mcp_name,
)
from agents.kernel.mcp.types import (
    MCP_AUTHENTICATE_SCHEMA,
    MCPAuthenticationRequired,
    MCPClient,
    MCPOAuthAuthenticator,
    MCPPromptDefinition,
    MCPResourceDefinition,
    MCPServerConfig,
    MCPToolDefinition,
)


@dataclass(frozen=True)
class MCPToolProvider:
    client: MCPClient
    server: MCPServerConfig
    oauth_authenticator: MCPOAuthAuthenticator | None = None
    tools: List[MCPToolDefinition] = field(default_factory=list, compare=False, repr=False)
    resources: List[MCPResourceDefinition] = field(default_factory=list, compare=False, repr=False)
    prompts: List[MCPPromptDefinition] = field(default_factory=list, compare=False, repr=False)
    resources_loaded: bool = field(default=False, compare=False, repr=False)
    prompts_loaded: bool = field(default=False, compare=False, repr=False)

    async def load_tools(self, registry: ToolRegistry) -> None:
        registered_names = set(registry.names()) if hasattr(registry, "names") else set()
        if self.server.auth_required:
            object.__setattr__(self, "tools", [])
            self._register_auth_tool(registry, registered_names)
            return
        try:
            tools = await self.client.list_tools()
        except MCPAuthenticationRequired as exc:
            object.__setattr__(self, "tools", [])
            self._register_auth_tool(
                registry,
                registered_names,
                auth_url=exc.auth_url,
                transport=exc.transport,
                url=exc.url,
                message=str(exc),
            )
            return
        object.__setattr__(self, "tools", list(tools))
        for tool in tools:
            canonical_name = self._registry_name(tool.name)
            if not is_included_mcp_tool(canonical_name):
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
        location = mcp_location(
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

    async def list_resources(self, refresh: bool = False) -> List[MCPResourceDefinition]:
        if self.resources_loaded and not refresh:
            return list(self.resources)
        list_resources = getattr(self.client, "list_resources", None)
        if list_resources is None:
            object.__setattr__(self, "resources", [])
            object.__setattr__(self, "resources_loaded", True)
            return []
        resources = list(await list_resources())
        object.__setattr__(self, "resources", resources)
        object.__setattr__(self, "resources_loaded", True)
        return list(resources)

    async def read_resource(self, uri: str) -> Any:
        read_resource = getattr(self.client, "read_resource", None)
        if read_resource is None:
            raise RuntimeError("MCP server does not support resources")
        return await read_resource(uri)

    async def list_prompts(self, refresh: bool = False) -> List[MCPPromptDefinition]:
        if self.prompts_loaded and not refresh:
            return list(self.prompts)
        list_prompts = getattr(self.client, "list_prompts", None)
        if list_prompts is None:
            object.__setattr__(self, "prompts", [])
            object.__setattr__(self, "prompts_loaded", True)
            return []
        prompts = list(await list_prompts())
        object.__setattr__(self, "prompts", prompts)
        object.__setattr__(self, "prompts_loaded", True)
        return list(prompts)

    async def get_prompt(self, name: str, arguments: Dict[str, Any] | None = None) -> Any:
        get_prompt = getattr(self.client, "get_prompt", None)
        if get_prompt is None:
            raise RuntimeError("MCP server does not support prompts")
        return await get_prompt(name, arguments or {})

    async def close(self) -> None:
        close = getattr(self.client, "close", None)
        if close is not None:
            await close()
