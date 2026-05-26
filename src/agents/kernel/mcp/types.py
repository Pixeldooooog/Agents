from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Protocol


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
