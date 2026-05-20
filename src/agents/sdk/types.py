from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter


class SDKOptions(BaseModel):
    """High-level SDK options independent from platform store wiring."""

    model_config = ConfigDict(extra="forbid")

    model: str | None = None
    protocol: str | None = None
    cwd: str | None = None
    system_prompt: str | None = None
    allowed_tools: list[str] | None = None
    skills: list[str] | None = None
    permission_mode: str | None = None
    output_format: dict[str, Any] | None = None
    session_id: str | None = None
    agent_id: str | None = None
    tenant_id: str | None = None
    user_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SDKListSessionsOptions(BaseModel):
    """Options for SDK session listing over the configured run store."""

    model_config = ConfigDict(extra="forbid")

    limit: int = Field(default=50, ge=0, le=200)
    offset: int = Field(default=0, ge=0)
    tenant_id: str = ""
    user_id: str = ""
    agent_id: str = ""
    cwd: str = ""


class SDKGetSessionMessagesOptions(BaseModel):
    """Options for replaying projected SDK messages from a stored session."""

    model_config = ConfigDict(extra="forbid")

    limit: int = Field(default=0, ge=0, le=1000)
    offset: int = Field(default=0, ge=0)
    include_system_messages: bool = True


class SDKForkSessionOptions(BaseModel):
    """Options for forking a stored SDK session."""

    model_config = ConfigDict(extra="forbid")

    title: str = ""
    up_to_message_id: str = ""


class SDKForkSessionResult(BaseModel):
    """Result returned after forking a stored SDK session."""

    model_config = ConfigDict(extra="forbid")

    session_id: str
    run_ids: list[str] = Field(default_factory=list)


class SDKSessionInfo(BaseModel):
    """Session metadata returned by SDK list/get session helpers.

    Timestamps use milliseconds since epoch to match the src-origin SDK contract.
    """

    model_config = ConfigDict(extra="forbid")

    session_id: str
    summary: str = ""
    last_modified: float = 0.0
    created_at: float = 0.0
    custom_title: str = ""
    first_prompt: str = ""
    cwd: str = ""
    tag: str = ""
    status: str = ""
    latest_run_id: str = ""
    run_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SDKBaseMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    session_id: str
    run_id: str


class SDKSystemMessage(SDKBaseMessage):
    type: Literal["system"] = "system"
    subtype: Literal["init"] = "init"
    cwd: str = ""
    model: str = ""
    protocol: str = ""
    tools: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SDKAPIRetryMessage(SDKBaseMessage):
    type: Literal["system"] = "system"
    subtype: Literal["api_retry"] = "api_retry"
    attempt: int = 0
    max_retries: int = 0
    retry_delay_ms: int = 0
    error_status: int | None = None
    error: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SDKCompactBoundaryMessage(SDKBaseMessage):
    type: Literal["system"] = "system"
    subtype: Literal["compact_boundary"] = "compact_boundary"
    compact_metadata: dict[str, Any] = Field(default_factory=dict)


class SDKAssistantMessage(SDKBaseMessage):
    type: Literal["assistant"] = "assistant"
    content: str = ""
    raw: dict[str, Any] = Field(default_factory=dict)


class SDKUserMessage(SDKBaseMessage):
    type: Literal["user"] = "user"
    uuid: str = ""
    message: dict[str, Any] = Field(default_factory=dict)
    content: str = ""
    parent_tool_use_id: str | None = None
    is_synthetic: bool = False
    tool_use_result: Any = None
    priority: Literal["now", "next", "later"] | None = None
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    is_replay: bool = True


class SDKToolProgressMessage(SDKBaseMessage):
    type: Literal["tool_progress"] = "tool_progress"
    tool_call_id: str = ""
    name: str
    status: Literal["started", "completed", "failed", "awaiting_approval", "denied"]
    input: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] = Field(default_factory=dict)
    activity: dict[str, Any] = Field(default_factory=dict)
    target: str = ""
    paths: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    error: str = ""


class SDKStatusMessage(SDKBaseMessage):
    type: Literal["status"] = "status"
    status: str
    message: str = ""
    data: dict[str, Any] = Field(default_factory=dict)


class SDKResultMessage(SDKBaseMessage):
    type: Literal["result"] = "result"
    subtype: Literal["success", "error"] = "success"
    content: str = ""
    stop_reason: str = ""
    duration_ms: int = 0
    num_turns: int = 0
    status: str = "finished"
    error: str = ""
    usage: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


SDKMessage = Union[
    SDKSystemMessage,
    SDKAPIRetryMessage,
    SDKCompactBoundaryMessage,
    SDKUserMessage,
    SDKAssistantMessage,
    SDKToolProgressMessage,
    SDKStatusMessage,
    SDKResultMessage,
]


SDKMessageAdapter = TypeAdapter(SDKMessage)


def sdk_options_json_schema() -> dict[str, Any]:
    """Return the JSON schema accepted by high-level SDK options."""

    return SDKOptions.model_json_schema()


def sdk_message_json_schema() -> dict[str, Any]:
    """Return the JSON schema for the SDK stream message union."""

    return SDKMessageAdapter.json_schema()


def sdk_result_json_schema() -> dict[str, Any]:
    """Return the JSON schema for final SDK result messages."""

    return SDKResultMessage.model_json_schema()


def sdk_session_info_json_schema() -> dict[str, Any]:
    """Return the JSON schema for SDK session metadata."""

    return SDKSessionInfo.model_json_schema()


def validate_sdk_message(message: SDKMessage | dict[str, Any]) -> SDKMessage:
    """Validate and coerce an SDK stream message against the exported contract."""

    payload = message.model_dump() if isinstance(message, BaseModel) else message
    return SDKMessageAdapter.validate_python(payload)
