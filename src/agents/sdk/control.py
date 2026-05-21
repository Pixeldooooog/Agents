from __future__ import annotations

from typing import Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from agents.sdk.types import SDKMessage, SDKUserMessage


PermissionMode = Literal["default", "acceptEdits", "bypassPermissions", "plan", "dontAsk"]


class SDKControlHookCallbackMatcher(BaseModel):
    model_config = ConfigDict(extra="forbid")

    matcher: str | None = None
    hookCallbackIds: list[str] = Field(default_factory=list)
    timeout: float | None = None


class SDKControlInitializeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subtype: Literal["initialize"] = "initialize"
    hooks: dict[str, list[SDKControlHookCallbackMatcher]] | None = None
    sdkMcpServers: list[str] | None = None
    jsonSchema: dict[str, Any] | None = None
    systemPrompt: str | None = None
    appendSystemPrompt: str | None = None
    agents: dict[str, Any] | None = None
    promptSuggestions: bool | None = None
    agentProgressSummaries: bool | None = None


class SDKControlInterruptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subtype: Literal["interrupt"] = "interrupt"


class SDKControlPermissionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subtype: Literal["can_use_tool"] = "can_use_tool"
    tool_name: str
    input: dict[str, Any] = Field(default_factory=dict)
    permission_suggestions: list[dict[str, Any]] | None = None
    blocked_path: str | None = None
    decision_reason: str | None = None
    title: str | None = None
    display_name: str | None = None
    tool_use_id: str
    agent_id: str | None = None
    description: str | None = None


class SDKControlSetPermissionModeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subtype: Literal["set_permission_mode"] = "set_permission_mode"
    mode: PermissionMode
    ultraplan: bool | None = None


class SDKControlSetModelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subtype: Literal["set_model"] = "set_model"
    model: str | None = None


class SDKControlSetMaxThinkingTokensRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subtype: Literal["set_max_thinking_tokens"] = "set_max_thinking_tokens"
    max_thinking_tokens: float | None = None


class SDKControlMcpStatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subtype: Literal["mcp_status"] = "mcp_status"


class SDKControlGetContextUsageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subtype: Literal["get_context_usage"] = "get_context_usage"


class SDKControlRewindFilesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subtype: Literal["rewind_files"] = "rewind_files"
    user_message_id: str
    dry_run: bool | None = None


class SDKControlCancelAsyncMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subtype: Literal["cancel_async_message"] = "cancel_async_message"
    message_uuid: str


class SDKControlSeedReadStateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subtype: Literal["seed_read_state"] = "seed_read_state"
    path: str
    mtime: float


class SDKHookCallbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subtype: Literal["hook_callback"] = "hook_callback"
    callback_id: str
    input: dict[str, Any] = Field(default_factory=dict)
    tool_use_id: str | None = None


class SDKControlMcpMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subtype: Literal["mcp_message"] = "mcp_message"
    server_name: str
    message: Any


class SDKControlMcpSetServersRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subtype: Literal["mcp_set_servers"] = "mcp_set_servers"
    servers: dict[str, dict[str, Any]] = Field(default_factory=dict)


class SDKControlReloadPluginsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subtype: Literal["reload_plugins"] = "reload_plugins"


class SDKControlMcpReconnectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subtype: Literal["mcp_reconnect"] = "mcp_reconnect"
    serverName: str


class SDKControlMcpToggleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subtype: Literal["mcp_toggle"] = "mcp_toggle"
    serverName: str
    enabled: bool


class SDKControlStopTaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subtype: Literal["stop_task"] = "stop_task"
    task_id: str


class SDKControlApplyFlagSettingsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subtype: Literal["apply_flag_settings"] = "apply_flag_settings"
    settings: dict[str, Any] = Field(default_factory=dict)


class SDKControlGetSettingsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subtype: Literal["get_settings"] = "get_settings"


class SDKControlElicitationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subtype: Literal["elicitation"] = "elicitation"
    mcp_server_name: str
    message: str
    mode: Literal["form", "url"] | None = None
    url: str | None = None
    elicitation_id: str | None = None
    requested_schema: dict[str, Any] | None = None


SDKControlRequestInner = Union[
    SDKControlInterruptRequest,
    SDKControlPermissionRequest,
    SDKControlInitializeRequest,
    SDKControlSetPermissionModeRequest,
    SDKControlSetModelRequest,
    SDKControlSetMaxThinkingTokensRequest,
    SDKControlMcpStatusRequest,
    SDKControlGetContextUsageRequest,
    SDKHookCallbackRequest,
    SDKControlMcpMessageRequest,
    SDKControlRewindFilesRequest,
    SDKControlCancelAsyncMessageRequest,
    SDKControlSeedReadStateRequest,
    SDKControlMcpSetServersRequest,
    SDKControlReloadPluginsRequest,
    SDKControlMcpReconnectRequest,
    SDKControlMcpToggleRequest,
    SDKControlStopTaskRequest,
    SDKControlApplyFlagSettingsRequest,
    SDKControlGetSettingsRequest,
    SDKControlElicitationRequest,
]


class SDKControlRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["control_request"] = "control_request"
    request_id: str
    request: SDKControlRequestInner


class SDKControlSuccessResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subtype: Literal["success"] = "success"
    request_id: str
    response: dict[str, Any] | None = None


class SDKControlErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subtype: Literal["error"] = "error"
    request_id: str
    error: str
    pending_permission_requests: list[SDKControlRequest] | None = None


SDKControlResponseInner = Union[SDKControlSuccessResponse, SDKControlErrorResponse]


class SDKControlResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["control_response"] = "control_response"
    response: SDKControlResponseInner


class SDKControlCancelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["control_cancel_request"] = "control_cancel_request"
    request_id: str


class SDKKeepAliveMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["keep_alive"] = "keep_alive"


class SDKUpdateEnvironmentVariablesMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["update_environment_variables"] = "update_environment_variables"
    variables: dict[str, str] = Field(default_factory=dict)


SDKStdoutMessage = Union[
    SDKMessage,
    SDKControlResponse,
    SDKControlRequest,
    SDKControlCancelRequest,
    SDKKeepAliveMessage,
]


SDKStdinMessage = Union[
    SDKUserMessage,
    SDKControlRequest,
    SDKControlResponse,
    SDKKeepAliveMessage,
    SDKUpdateEnvironmentVariablesMessage,
]


SDKControlRequestAdapter = TypeAdapter(SDKControlRequest)
SDKControlResponseAdapter = TypeAdapter(SDKControlResponse)
SDKControlCancelRequestAdapter = TypeAdapter(SDKControlCancelRequest)
SDKStdoutMessageAdapter = TypeAdapter(SDKStdoutMessage)
SDKStdinMessageAdapter = TypeAdapter(SDKStdinMessage)


def sdk_control_request_json_schema() -> dict[str, Any]:
    return SDKControlRequest.model_json_schema()


def sdk_control_response_json_schema() -> dict[str, Any]:
    return SDKControlResponse.model_json_schema()


def sdk_control_cancel_request_json_schema() -> dict[str, Any]:
    return SDKControlCancelRequest.model_json_schema()


def sdk_stdout_message_json_schema() -> dict[str, Any]:
    return SDKStdoutMessageAdapter.json_schema()


def sdk_stdin_message_json_schema() -> dict[str, Any]:
    return SDKStdinMessageAdapter.json_schema()


def validate_sdk_control_request(message: SDKControlRequest | dict[str, Any]) -> SDKControlRequest:
    payload = message.model_dump() if isinstance(message, BaseModel) else message
    return SDKControlRequestAdapter.validate_python(payload)


def validate_sdk_control_response(message: SDKControlResponse | dict[str, Any]) -> SDKControlResponse:
    payload = message.model_dump() if isinstance(message, BaseModel) else message
    return SDKControlResponseAdapter.validate_python(payload)


def validate_sdk_stdin_message(message: SDKStdinMessage | dict[str, Any]) -> SDKStdinMessage:
    payload = message.model_dump() if isinstance(message, BaseModel) else message
    return SDKStdinMessageAdapter.validate_python(payload)


def validate_sdk_stdout_message(message: SDKStdoutMessage | dict[str, Any]) -> SDKStdoutMessage:
    payload = message.model_dump() if isinstance(message, BaseModel) else message
    return SDKStdoutMessageAdapter.validate_python(payload)
