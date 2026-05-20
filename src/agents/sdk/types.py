from __future__ import annotations

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


class SDKAssistantMessage(SDKBaseMessage):
    type: Literal["assistant"] = "assistant"
    content: str = ""
    raw: dict[str, Any] = Field(default_factory=dict)


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


def validate_sdk_message(message: SDKMessage | dict[str, Any]) -> SDKMessage:
    """Validate and coerce an SDK stream message against the exported contract."""

    payload = message.model_dump() if isinstance(message, BaseModel) else message
    return SDKMessageAdapter.validate_python(payload)
