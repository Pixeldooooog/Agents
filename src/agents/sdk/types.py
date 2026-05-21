from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Union
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, TypeAdapter


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

    sessionId: str
    summary: str = ""
    lastModified: float = 0.0
    fileSize: float | None = None
    customTitle: str | None = None
    firstPrompt: str | None = None
    gitBranch: str | None = None
    cwd: str | None = None
    tag: str | None = None
    createdAt: float | None = None

    _status: str = PrivateAttr(default="")
    _latest_run_id: str = PrivateAttr(default="")
    _run_ids: list[str] = PrivateAttr(default_factory=list)
    _metadata: dict[str, Any] = PrivateAttr(default_factory=dict)

    @property
    def session_id(self) -> str:
        return self.sessionId

    @property
    def last_modified(self) -> float:
        return self.lastModified

    @property
    def created_at(self) -> float:
        return float(self.createdAt or 0.0)

    @property
    def custom_title(self) -> str:
        return self.customTitle or ""

    @property
    def first_prompt(self) -> str:
        return self.firstPrompt or ""

    @property
    def status(self) -> str:
        return self._status

    @property
    def latest_run_id(self) -> str:
        return self._latest_run_id

    @property
    def run_ids(self) -> list[str]:
        return list(self._run_ids)

    @property
    def metadata(self) -> dict[str, Any]:
        return dict(self._metadata)


class SDKBaseMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    session_id: str
    run_id: str


class SDKSystemMessage(SDKBaseMessage):
    type: Literal["system"] = "system"
    subtype: Literal["init"] = "init"
    agents: list[str] = Field(default_factory=list)
    apiKeySource: Literal["user", "project", "org", "temporary", "oauth"] = "project"
    betas: list[str] = Field(default_factory=list)
    claude_code_version: str = ""
    cwd: str = ""
    tools: list[str] = Field(default_factory=list)
    mcp_servers: list[dict[str, str]] = Field(default_factory=list)
    model: str = ""
    permissionMode: Literal["default", "acceptEdits", "bypassPermissions", "plan", "dontAsk"] = "default"
    slash_commands: list[str] = Field(default_factory=list)
    output_style: str = "default"
    skills: list[str] = Field(default_factory=list)
    plugins: list[dict[str, str]] = Field(default_factory=list)
    fast_mode_state: Literal["off", "cooldown", "on"] | None = None
    uuid: str = Field(default_factory=lambda: str(uuid4()))


class SDKStreamEventMessage(SDKBaseMessage):
    type: Literal["stream_event"] = "stream_event"
    event: dict[str, Any] = Field(default_factory=dict)
    parent_tool_use_id: str | None = None
    uuid: str = Field(default_factory=lambda: str(uuid4()))


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


class SDKAuthStatusMessage(SDKBaseMessage):
    type: Literal["auth_status"] = "auth_status"
    is_authenticating: bool = False
    output: list[str] = Field(default_factory=list)
    error: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class SDKRateLimitEventMessage(SDKBaseMessage):
    type: Literal["rate_limit_event"] = "rate_limit_event"
    rate_limit_info: dict[str, Any] = Field(default_factory=dict)
    uuid: str = Field(default_factory=lambda: str(uuid4()))


class SDKSessionStateChangedMessage(SDKBaseMessage):
    type: Literal["system"] = "system"
    subtype: Literal["session_state_changed"] = "session_state_changed"
    state: Literal["idle", "running", "requires_action"]


class SDKTaskStartedMessage(SDKBaseMessage):
    type: Literal["system"] = "system"
    subtype: Literal["task_started"] = "task_started"
    task_id: str
    tool_use_id: str = ""
    description: str = ""
    task_type: str = ""
    workflow_name: str = ""
    prompt: str = ""


class SDKTaskProgressMessage(SDKBaseMessage):
    type: Literal["system"] = "system"
    subtype: Literal["task_progress"] = "task_progress"
    task_id: str
    tool_use_id: str = ""
    description: str = ""
    usage: dict[str, int] = Field(default_factory=dict)
    last_tool_name: str = ""
    summary: str = ""


class SDKTaskNotificationMessage(SDKBaseMessage):
    type: Literal["system"] = "system"
    subtype: Literal["task_notification"] = "task_notification"
    task_id: str
    tool_use_id: str = ""
    status: Literal["completed", "failed", "stopped"]
    output_file: str = ""
    summary: str = ""
    usage: dict[str, int] = Field(default_factory=dict)


class SDKFilesPersistedMessage(SDKBaseMessage):
    type: Literal["system"] = "system"
    subtype: Literal["files_persisted"] = "files_persisted"
    files: list[dict[str, str]] = Field(default_factory=list)
    failed: list[dict[str, str]] = Field(default_factory=list)
    processed_at: str = ""


class SDKLocalCommandOutputMessage(SDKBaseMessage):
    type: Literal["system"] = "system"
    subtype: Literal["local_command_output"] = "local_command_output"
    content: str = ""
    uuid: str = Field(default_factory=lambda: str(uuid4()))


class SDKHookStartedMessage(SDKBaseMessage):
    type: Literal["system"] = "system"
    subtype: Literal["hook_started"] = "hook_started"
    hook_id: str
    hook_name: str
    hook_event: str
    uuid: str = Field(default_factory=lambda: str(uuid4()))


class SDKHookProgressMessage(SDKBaseMessage):
    type: Literal["system"] = "system"
    subtype: Literal["hook_progress"] = "hook_progress"
    hook_id: str
    hook_name: str
    hook_event: str
    stdout: str = ""
    stderr: str = ""
    output: str = ""
    uuid: str = Field(default_factory=lambda: str(uuid4()))


class SDKHookResponseMessage(SDKBaseMessage):
    type: Literal["system"] = "system"
    subtype: Literal["hook_response"] = "hook_response"
    hook_id: str
    hook_name: str
    hook_event: str
    output: str = ""
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    outcome: Literal["success", "error", "cancelled"] = "success"
    uuid: str = Field(default_factory=lambda: str(uuid4()))


class SDKToolUseSummaryMessage(SDKBaseMessage):
    type: Literal["tool_use_summary"] = "tool_use_summary"
    summary: str
    preceding_tool_use_ids: list[str] = Field(default_factory=list)
    uuid: str = Field(default_factory=lambda: str(uuid4()))


class SDKElicitationCompleteMessage(SDKBaseMessage):
    type: Literal["system"] = "system"
    subtype: Literal["elicitation_complete"] = "elicitation_complete"
    mcp_server_name: str
    elicitation_id: str
    uuid: str = Field(default_factory=lambda: str(uuid4()))


class SDKPromptSuggestionMessage(SDKBaseMessage):
    type: Literal["prompt_suggestion"] = "prompt_suggestion"
    suggestion: str
    uuid: str = Field(default_factory=lambda: str(uuid4()))


class SDKPostTurnSummaryMessage(SDKBaseMessage):
    type: Literal["system"] = "system"
    subtype: Literal["post_turn_summary"] = "post_turn_summary"
    summarizes_uuid: str
    status_category: Literal["blocked", "waiting", "completed", "review_ready", "failed"]
    status_detail: str = ""
    is_noteworthy: bool = False
    title: str = ""
    description: str = ""
    recent_action: str = ""
    needs_action: str = ""
    artifact_urls: list[str] = Field(default_factory=list)
    uuid: str = Field(default_factory=lambda: str(uuid4()))


class SDKAssistantMessage(SDKBaseMessage):
    type: Literal["assistant"] = "assistant"
    message: dict[str, Any] = Field(default_factory=dict)
    parent_tool_use_id: str | None = None
    error: Literal[
        "authentication_failed",
        "billing_error",
        "rate_limit",
        "invalid_request",
        "server_error",
        "unknown",
        "max_output_tokens",
    ] | None = None
    uuid: str = Field(default_factory=lambda: str(uuid4()))

    @property
    def content(self) -> str:
        return _message_content_text(self.message)


class SDKUserMessage(SDKBaseMessage):
    type: Literal["user"] = "user"
    uuid: str = ""
    message: dict[str, Any] = Field(default_factory=dict)
    parent_tool_use_id: str | None = None
    isSynthetic: bool = False
    tool_use_result: Any = None
    priority: Literal["now", "next", "later"] | None = None
    timestamp: str | None = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    isReplay: bool = True

    @property
    def content(self) -> str:
        return _message_content_text(self.message)

    @property
    def is_synthetic(self) -> bool:
        return self.isSynthetic

    @property
    def is_replay(self) -> bool:
        return self.isReplay


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
    type: Literal["system"] = "system"
    subtype: Literal["status"] = "status"
    status: Literal["compacting"] | None = None
    permissionMode: str | None = None
    uuid: str = Field(default_factory=lambda: str(uuid4()))


class SDKResultMessage(SDKBaseMessage):
    type: Literal["result"] = "result"
    subtype: Literal[
        "success",
        "error_during_execution",
        "error_max_turns",
        "error_max_budget_usd",
        "error_max_structured_output_retries",
    ] = "success"
    duration_ms: int = 0
    duration_api_ms: int = 0
    is_error: bool = False
    num_turns: int = 0
    result: str = ""
    stop_reason: str | None = None
    total_cost_usd: float = 0.0
    usage: dict[str, Any] = Field(default_factory=dict)
    modelUsage: dict[str, Any] = Field(default_factory=dict)
    permission_denials: list[dict[str, Any]] = Field(default_factory=list)
    structured_output: Any = None
    fast_mode_state: dict[str, Any] | None = None
    errors: list[str] = Field(default_factory=list)
    uuid: str = Field(default_factory=lambda: str(uuid4()))

    @property
    def content(self) -> str:
        return self.result

    @property
    def status(self) -> str:
        if self.is_error:
            return "error"
        return str(self.stop_reason or "finished")

    @property
    def error(self) -> str:
        return self.errors[0] if self.errors else ""


SDKMessage = Union[
    SDKSystemMessage,
    SDKStreamEventMessage,
    SDKAPIRetryMessage,
    SDKCompactBoundaryMessage,
    SDKAuthStatusMessage,
    SDKRateLimitEventMessage,
    SDKSessionStateChangedMessage,
    SDKTaskStartedMessage,
    SDKTaskProgressMessage,
    SDKTaskNotificationMessage,
    SDKFilesPersistedMessage,
    SDKLocalCommandOutputMessage,
    SDKHookStartedMessage,
    SDKHookProgressMessage,
    SDKHookResponseMessage,
    SDKToolUseSummaryMessage,
    SDKElicitationCompleteMessage,
    SDKPromptSuggestionMessage,
    SDKPostTurnSummaryMessage,
    SDKUserMessage,
    SDKAssistantMessage,
    SDKToolProgressMessage,
    SDKStatusMessage,
    SDKResultMessage,
]


SDKMessageAdapter = TypeAdapter(SDKMessage)


def _message_content_text(message: dict[str, Any]) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text") or ""))
        return "".join(parts)
    return ""


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
