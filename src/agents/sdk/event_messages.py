from __future__ import annotations

import uuid
from typing import Any, Literal

from agents.kernel.schema import RuntimeEvent
from agents.sdk.event_fields import (
    _dict_field,
    _dict_list_field,
    _float,
    _int,
    _nullable_text_field,
    _optional_dict_field,
    _optional_int,
    _string_list_field,
    _text_field,
)
from agents.sdk.event_payloads import _tool_call_id, _tool_contract
from agents.sdk.event_tasks import _task_notification_event_message, _task_started_event_message
from agents.sdk.types import (
    SDKAPIRetryMessage,
    SDKAssistantMessage,
    SDKCompactBoundaryMessage,
    SDKElicitationCompleteMessage,
    SDKHookProgressMessage,
    SDKHookResponseMessage,
    SDKHookStartedMessage,
    SDKLocalCommandOutputMessage,
    SDKMessage,
    SDKPostTurnSummaryMessage,
    SDKPromptSuggestionMessage,
    SDKRateLimitEventMessage,
    SDKResultMessage,
    SDKSessionStateChangedMessage,
    SDKStatusMessage,
    SDKStreamEventMessage,
    SDKToolProgressMessage,
    SDKToolUseSummaryMessage,
    SDKUserMessage,
)


def _project_runtime_event(
    event: RuntimeEvent,
    *,
    session_id: str,
    run_id: str,
    duration_ms: int,
    num_turns: int,
) -> SDKMessage | None:
    if event.type == "user_message":
        message = dict(event.payload.get("message") or {})
        return SDKUserMessage(
            session_id=session_id,
            run_id=run_id,
            uuid=str(event.payload.get("uuid") or event.payload.get("message_id") or ""),
            message=message,
            parent_tool_use_id=event.payload.get("parent_tool_use_id"),
            isSynthetic=bool(event.payload.get("isSynthetic") or event.payload.get("is_synthetic") or False),
            tool_use_result=event.payload.get("tool_use_result"),
            priority=_user_message_priority(event.payload.get("priority")),
            timestamp=str(event.payload.get("timestamp") or "") or None,
            isReplay=bool(event.payload.get("isReplay", event.payload.get("is_replay", True))),
        )
    if event.type == "model_message":
        return SDKAssistantMessage(
            session_id=session_id,
            run_id=run_id,
            message=_assistant_api_message(event.payload),
            parent_tool_use_id=_nullable_text_field(event.payload, "parent_tool_use_id", "parentToolUseId"),
            error=_assistant_error(event.payload.get("error")),
            uuid=_text_field(event.payload, "uuid", "message_id", "messageId") or str(uuid.uuid4()),
        )
    if event.type == "text_delta":
        return SDKStreamEventMessage(
            session_id=session_id,
            run_id=run_id,
            event=_stream_delta_event("text_delta", event.payload),
            parent_tool_use_id=_nullable_text_field(event.payload, "parent_tool_use_id", "parentToolUseId"),
        )
    if event.type == "reasoning_delta":
        return SDKStreamEventMessage(
            session_id=session_id,
            run_id=run_id,
            event=_stream_delta_event("reasoning_delta", event.payload),
            parent_tool_use_id=_nullable_text_field(event.payload, "parent_tool_use_id", "parentToolUseId"),
        )
    if event.type == "model_retry":
        return SDKAPIRetryMessage(
            session_id=session_id,
            run_id=run_id,
            attempt=_retry_attempt(event.payload),
            max_retries=_retry_max_attempts(event.payload),
            retry_delay_ms=_retry_delay_ms(event.payload),
            error_status=_retry_error_status(event.payload),
            error=_retry_error_payload(event.payload),
            metadata=dict(event.payload),
        )
    if event.type == "rate_limit_event":
        rate_limit_info = event.payload.get("rate_limit_info") or event.payload.get("rateLimitInfo") or {}
        return SDKRateLimitEventMessage(
            session_id=session_id,
            run_id=run_id,
            rate_limit_info=dict(rate_limit_info) if isinstance(rate_limit_info, dict) else {},
            uuid=_text_field(event.payload, "uuid", "message_id", "messageId") or str(uuid.uuid4()),
        )
    if event.type == "compact_boundary":
        return SDKCompactBoundaryMessage(
            session_id=session_id,
            run_id=run_id,
            compact_metadata={
                "trigger": str(event.payload.get("trigger") or "auto"),
                "pre_tokens": _int(event.payload.get("pre_tokens")),
                "post_tokens": _int(event.payload.get("post_tokens")),
                "before_messages": _int(event.payload.get("before_messages")),
                "after_messages": _int(event.payload.get("after_messages")),
                "dropped_messages": _int(event.payload.get("dropped_messages")),
            },
        )
    if event.type == "session_state_changed":
        return _project_session_state_event(event, session_id=session_id, run_id=run_id)
    if event.type == "task_started":
        return _task_started_event_message(event, session_id=session_id, run_id=run_id)
    if event.type == "task_notification":
        return _task_notification_event_message(event, session_id=session_id, run_id=run_id)
    if event.type == "local_command_output":
        return SDKLocalCommandOutputMessage(
            session_id=session_id,
            run_id=run_id,
            content=_local_command_output_content(event.payload),
            uuid=_text_field(event.payload, "uuid", "message_id", "messageId") or str(uuid.uuid4()),
        )
    if event.type == "tool_use_summary":
        return SDKToolUseSummaryMessage(
            session_id=session_id,
            run_id=run_id,
            summary=str(event.payload.get("summary") or ""),
            preceding_tool_use_ids=_string_list_field(
                event.payload.get("preceding_tool_use_ids", event.payload.get("precedingToolUseIds"))
            ),
            uuid=_text_field(event.payload, "uuid", "message_id", "messageId") or str(uuid.uuid4()),
        )
    if event.type == "tool_progress":
        contract = _tool_contract(event.payload)
        metadata = dict(contract.get("metadata") or {})
        metadata.update(_dict_field(event.payload.get("metadata")))
        return SDKToolProgressMessage(
            session_id=session_id,
            run_id=run_id,
            tool_call_id=_text_field(event.payload, "tool_call_id", "tool_use_id", "toolUseId"),
            name=_text_field(event.payload, "tool_name", "toolName") or event.name,
            status=_tool_progress_status(event.payload.get("status")),
            input=_dict_field(event.payload.get("input")),
            result=_dict_field(event.payload.get("result")),
            activity=dict(contract.get("activity") or _dict_field(event.payload.get("activity"))),
            target=str(contract.get("target") or event.payload.get("target") or ""),
            paths=list(contract.get("paths") or _string_list_field(event.payload.get("paths"))),
            metadata=metadata,
            error=_text_field(event.payload, "error"),
            output=_text_field(event.payload, "output"),
            full_output=_text_field(event.payload, "full_output", "fullOutput"),
            elapsed_time_seconds=_float(
                event.payload.get("elapsed_time_seconds", event.payload.get("elapsedTimeSeconds"))
            ),
            total_lines=_int(event.payload.get("total_lines", event.payload.get("totalLines"))),
            total_bytes=_int(event.payload.get("total_bytes", event.payload.get("totalBytes"))),
            task_id=_text_field(event.payload, "task_id", "taskId"),
            timeout_ms=_int(event.payload.get("timeout_ms", event.payload.get("timeoutMs"))),
        )
    if event.type == "elicitation_complete":
        return SDKElicitationCompleteMessage(
            session_id=session_id,
            run_id=run_id,
            mcp_server_name=_text_field(event.payload, "mcp_server_name", "mcpServerName", "server"),
            elicitation_id=_text_field(event.payload, "elicitation_id", "elicitationId", "id"),
            uuid=_text_field(event.payload, "uuid", "message_id", "messageId") or str(uuid.uuid4()),
        )
    if event.type == "prompt_suggestion":
        return SDKPromptSuggestionMessage(
            session_id=session_id,
            run_id=run_id,
            suggestion=str(event.payload.get("suggestion") or ""),
            uuid=_text_field(event.payload, "uuid", "message_id", "messageId") or str(uuid.uuid4()),
        )
    if event.type == "post_turn_summary":
        status_category = event.payload.get("status_category", event.payload.get("statusCategory"))
        return SDKPostTurnSummaryMessage(
            session_id=session_id,
            run_id=run_id,
            summarizes_uuid=_text_field(event.payload, "summarizes_uuid", "summarizesUuid"),
            status_category=_post_turn_status_category(status_category),
            status_detail=_text_field(event.payload, "status_detail", "statusDetail"),
            is_noteworthy=bool(event.payload.get("is_noteworthy", event.payload.get("isNoteworthy", False))),
            title=_text_field(event.payload, "title"),
            description=_text_field(event.payload, "description"),
            recent_action=_text_field(event.payload, "recent_action", "recentAction"),
            needs_action=_text_field(event.payload, "needs_action", "needsAction"),
            artifact_urls=_string_list_field(event.payload.get("artifact_urls", event.payload.get("artifactUrls"))),
            uuid=_text_field(event.payload, "uuid", "message_id", "messageId") or str(uuid.uuid4()),
        )
    if event.type == "hook_started":
        return SDKHookStartedMessage(
            session_id=session_id,
            run_id=run_id,
            hook_id=_text_field(event.payload, "hook_id", "hookId"),
            hook_name=_text_field(event.payload, "hook_name", "hookName"),
            hook_event=_text_field(event.payload, "hook_event", "hookEvent"),
        )
    if event.type == "hook_progress":
        return SDKHookProgressMessage(
            session_id=session_id,
            run_id=run_id,
            hook_id=_text_field(event.payload, "hook_id", "hookId"),
            hook_name=_text_field(event.payload, "hook_name", "hookName"),
            hook_event=_text_field(event.payload, "hook_event", "hookEvent"),
            stdout=_text_field(event.payload, "stdout"),
            stderr=_text_field(event.payload, "stderr"),
            output=_text_field(event.payload, "output"),
        )
    if event.type == "hook_response":
        return SDKHookResponseMessage(
            session_id=session_id,
            run_id=run_id,
            hook_id=_text_field(event.payload, "hook_id", "hookId"),
            hook_name=_text_field(event.payload, "hook_name", "hookName"),
            hook_event=_text_field(event.payload, "hook_event", "hookEvent"),
            output=_text_field(event.payload, "output"),
            stdout=_text_field(event.payload, "stdout"),
            stderr=_text_field(event.payload, "stderr"),
            exit_code=_optional_int(event.payload.get("exit_code", event.payload.get("exitCode"))),
            outcome=_hook_outcome(event.payload.get("outcome")),
        )
    if event.type == "tool_start":
        contract = _tool_contract(event.payload)
        return SDKToolProgressMessage(
            session_id=session_id,
            run_id=run_id,
            tool_call_id=_tool_call_id(event.payload),
            name=event.name,
            status="started",
            input=dict(event.payload.get("arguments") or {}),
            activity=dict(contract.get("activity") or {}),
            target=str(contract.get("target") or ""),
            paths=list(contract.get("paths") or []),
            metadata=dict(contract.get("metadata") or {}),
        )
    if event.type == "tool_result":
        status = "failed" if event.payload.get("error") else "completed"
        contract = _tool_contract(event.payload)
        return SDKToolProgressMessage(
            session_id=session_id,
            run_id=run_id,
            tool_call_id=str(event.payload.get("tool_call_id", "") or ""),
            name=event.name,
            status=status,
            result=dict(event.payload),
            activity=dict(contract.get("activity") or {}),
            target=str(contract.get("target") or ""),
            paths=list(contract.get("paths") or []),
            metadata=dict(contract.get("metadata") or {}),
            error=str(event.payload.get("error", "") or ""),
        )
    if event.type == "tool_approval_required":
        tool_call = dict(event.payload.get("tool_call") or {})
        contract = _tool_contract(event.payload)
        return SDKToolProgressMessage(
            session_id=session_id,
            run_id=run_id,
            tool_call_id=_tool_call_id(tool_call),
            name=event.name,
            status="awaiting_approval",
            input=dict(tool_call.get("arguments") or {}),
            result=dict(event.payload),
            activity=dict(contract.get("activity") or {}),
            target=str(contract.get("target") or ""),
            paths=list(contract.get("paths") or []),
            metadata=dict(contract.get("metadata") or {}),
        )
    if event.type == "tool_approval_decision":
        tool_call = dict(event.payload.get("tool_call") or {})
        contract = _tool_contract(event.payload)
        return SDKToolProgressMessage(
            session_id=session_id,
            run_id=run_id,
            tool_call_id=_tool_call_id(tool_call),
            name=event.name,
            status="completed" if event.payload.get("approved") else "denied",
            result=dict(event.payload),
            activity=dict(contract.get("activity") or {}),
            target=str(contract.get("target") or ""),
            paths=list(contract.get("paths") or []),
            metadata=dict(contract.get("metadata") or {}),
        )
    if event.type == "error":
        return SDKStatusMessage(
            session_id=session_id,
            run_id=run_id,
            status=None,
        )
    if event.type == "done":
        return _result_message_from_done(
            event.payload,
            session_id=session_id,
            run_id=run_id,
            duration_ms=duration_ms,
            num_turns=num_turns,
        )
    return SDKStatusMessage(
        session_id=session_id,
        run_id=run_id,
        status=_sdk_status(event.payload.get("status")),
        permissionMode=_nullable_text_field(event.payload, "permissionMode", "permission_mode"),
    )


def _assistant_api_message(payload: dict[str, Any]) -> dict[str, Any]:
    message = payload.get("message")
    if isinstance(message, dict):
        return dict(message)
    raw = payload.get("raw")
    if isinstance(raw, dict) and isinstance(raw.get("message"), dict):
        return dict(raw["message"])
    content = str(payload.get("content") or "")
    return {
        "id": str(payload.get("message_id") or payload.get("id") or "msg_%s" % uuid.uuid4().hex),
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": content}] if content else [],
        "model": str(payload.get("model") or ""),
        "stop_reason": payload.get("stop_reason"),
        "stop_sequence": payload.get("stop_sequence"),
        "usage": payload.get("usage") if isinstance(payload.get("usage"), dict) else {},
    }


def _assistant_error(value: Any) -> Literal[
    "authentication_failed",
    "billing_error",
    "rate_limit",
    "invalid_request",
    "server_error",
    "unknown",
    "max_output_tokens",
] | None:
    text = str(value or "")
    if text in {
        "authentication_failed",
        "billing_error",
        "rate_limit",
        "invalid_request",
        "server_error",
        "unknown",
        "max_output_tokens",
    }:
        return text
    return None


def _user_message_priority(value: Any) -> str | None:
    text = str(value or "")
    return text if text in {"now", "next", "later"} else None


def _session_state(value: Any) -> str:
    text = str(value or "")
    return text if text in {"idle", "running", "requires_action"} else "idle"


def _session_state_event(state: str) -> RuntimeEvent:
    return RuntimeEvent(type="session_state_changed", name="session", payload={"state": state})


def _project_session_state_event(
    event: RuntimeEvent,
    *,
    session_id: str,
    run_id: str,
) -> SDKSessionStateChangedMessage:
    state = _session_state(event.payload.get("state"))
    return SDKSessionStateChangedMessage(session_id=session_id, run_id=run_id, state=state)


def _result_message_from_done(
    payload: dict[str, Any],
    *,
    session_id: str,
    run_id: str,
    duration_ms: int,
    num_turns: int,
) -> SDKResultMessage:
    status = str(payload.get("status") or payload.get("stop_reason") or payload.get("stopReason") or "finished")
    errors = _string_list_field(payload.get("errors"))
    error = _text_field(payload, "error")
    if error and not errors:
        errors = [error]
    is_error = bool(payload.get("is_error", payload.get("isError", False))) or bool(errors) or status == "error"
    result = payload["result"] if "result" in payload else payload.get("content", "")
    return SDKResultMessage(
        session_id=session_id,
        run_id=run_id,
        subtype=_result_subtype(payload.get("subtype"), is_error=is_error),
        duration_ms=_int(payload.get("duration_ms", payload.get("durationMs", duration_ms))),
        duration_api_ms=_int(payload.get("duration_api_ms", payload.get("durationApiMs", 0))),
        is_error=is_error,
        num_turns=_int(payload.get("num_turns", payload.get("numTurns", num_turns))),
        result=str(result or ""),
        stop_reason=_nullable_text_field(payload, "stop_reason", "stopReason") or status,
        total_cost_usd=_float(payload.get("total_cost_usd", payload.get("totalCostUsd", 0))),
        usage=_dict_field(payload.get("usage")),
        modelUsage=_dict_field(payload.get("modelUsage", payload.get("model_usage"))),
        permission_denials=_dict_list_field(payload.get("permission_denials", payload.get("permissionDenials"))),
        structured_output=payload.get("structured_output", payload.get("structuredOutput")),
        fast_mode_state=_optional_dict_field(payload.get("fast_mode_state", payload.get("fastModeState"))),
        errors=errors,
        uuid=_text_field(payload, "uuid", "message_id", "messageId") or str(uuid.uuid4()),
    )


def _result_subtype(
    value: Any,
    *,
    is_error: bool,
) -> Literal[
    "success",
    "error_during_execution",
    "error_max_turns",
    "error_max_budget_usd",
    "error_max_structured_output_retries",
]:
    text = str(value or "")
    if text in {
        "error_during_execution",
        "error_max_turns",
        "error_max_budget_usd",
        "error_max_structured_output_retries",
    }:
        return text
    return "error_during_execution" if is_error else "success"


def _retry_attempt(payload: dict[str, Any]) -> int:
    if payload.get("next_attempt") is not None:
        return _int(payload.get("next_attempt"))
    if payload.get("attempt") is not None:
        return _int(payload.get("attempt"))
    return _int(payload.get("failed_attempt")) + 1 if payload.get("failed_attempt") is not None else 0


def _retry_max_attempts(payload: dict[str, Any]) -> int:
    return _int(payload.get("max_attempts") or payload.get("max_retries"))


def _retry_delay_ms(payload: dict[str, Any]) -> int:
    if payload.get("retry_delay_ms") is not None:
        return _int(payload.get("retry_delay_ms"))
    return int(float(payload.get("delay_seconds") or 0) * 1000)


def _retry_error_status(payload: dict[str, Any]) -> int | None:
    value = payload.get("error_status", payload.get("status_code", payload.get("status")))
    if value is None or value == "":
        return None
    return _int(value)


def _retry_error_payload(payload: dict[str, Any]) -> dict[str, Any]:
    error = payload.get("error")
    if isinstance(error, dict):
        return dict(error)
    return {
        "message": str(error or payload.get("message") or "model request failed"),
        "type": str(payload.get("error_type") or payload.get("type") or "unknown"),
    }


def _tool_progress_status(value: Any) -> str:
    status = str(value or "running")
    if status in {"started", "running", "stalled", "completed", "failed", "awaiting_approval", "denied"}:
        return status
    return "running"


def _local_command_output_content(payload: dict[str, Any]) -> str:
    content = str(payload.get("content") or payload.get("output") or "")
    content = content.replace("<local-command-stdout>", "").replace("</local-command-stdout>", "")
    content = content.replace("<local-command-stderr>", "").replace("</local-command-stderr>", "")
    return content.strip()


def _stream_delta_event(event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    delta = str(payload.get("delta") or "")
    raw = payload.get("event") if isinstance(payload.get("event"), dict) else {}
    if raw:
        return dict(raw)
    if event_type == "reasoning_delta":
        return {
            "type": "content_block_delta",
            "delta": {"type": "thinking_delta", "thinking": delta},
        }
    return {
        "type": "content_block_delta",
        "delta": {"type": "text_delta", "text": delta},
    }


def _hook_outcome(value: Any) -> Literal["success", "error", "cancelled"]:
    text = str(value or "")
    if text == "error":
        return "error"
    if text == "cancelled":
        return "cancelled"
    return "success"


def _post_turn_status_category(value: Any) -> Literal["blocked", "waiting", "completed", "review_ready", "failed"]:
    text = str(value or "")
    if text == "blocked":
        return "blocked"
    if text == "waiting":
        return "waiting"
    if text == "review_ready":
        return "review_ready"
    if text == "failed":
        return "failed"
    return "completed"


def _sdk_status(value: Any) -> Literal["compacting"] | None:
    return "compacting" if str(value or "") == "compacting" else None
