from __future__ import annotations

import json
from typing import Any

from agents.kernel.capabilities.tools.contracts import ToolDefinition, ToolExecutionError
from agents.kernel.schema import ToolCall, ToolResult


def format_tool_result(tool: ToolDefinition, result: Any) -> str:
    if tool.result_formatter is not None:
        return str(tool.result_formatter(result))
    if isinstance(result, str):
        return result
    return json.dumps(result, ensure_ascii=False, sort_keys=True)


def cancelled_tool_result(
    call: ToolCall,
    canceled_by: ToolResult | None = None,
    *,
    cancel_reason: str = "tool_cancelled",
) -> ToolResult:
    cancelled_by = canceled_by.name if canceled_by is not None else ""
    content = "tool execution canceled"
    if cancelled_by:
        content = "%s by sibling tool failure: %s" % (content, cancelled_by)
    elif cancel_reason == "user_interrupted":
        content = "%s by user interrupt" % content
    return ToolResult(
        tool_call_id=call.id,
        name=call.name,
        content=content,
        is_error=True,
        raw={
            "error": "tool_execution_canceled",
            "canceled": True,
            "canceled_by": cancelled_by,
            "cancel_reason": cancel_reason,
        },
    )


def tool_result_payload(
    tool: ToolDefinition,
    result: Any,
    metadata: dict[str, Any],
) -> tuple[str, Any]:
    content = format_tool_result(tool, result)
    output_metadata = dict(metadata or {})
    if tool.max_result_size_chars is not None and len(content) > tool.max_result_size_chars:
        content = content[: tool.max_result_size_chars] + "\n[tool result truncated]"
        output_metadata["result_truncated"] = True
        output_metadata["max_result_size_chars"] = tool.max_result_size_chars
    return content, with_metadata(result, output_metadata)


def tool_error_payload(
    tool: ToolDefinition,
    error: ToolExecutionError,
    metadata: dict[str, Any],
) -> tuple[str, Any]:
    content = str(error.content or "")
    output_metadata = dict(metadata or {})
    if tool.max_result_size_chars is not None and len(content) > tool.max_result_size_chars:
        content = content[: tool.max_result_size_chars] + "\n[tool result truncated]"
        output_metadata["result_truncated"] = True
        output_metadata["max_result_size_chars"] = tool.max_result_size_chars
    raw = error.raw if error.raw is not None else {"error": "tool_execution_error"}
    if isinstance(raw, dict) and "error" not in raw:
        raw = {"error": "tool_execution_error", **raw}
    return content, with_metadata(raw, output_metadata)


def with_metadata(result: Any, metadata: dict[str, Any]) -> Any:
    if not metadata:
        return result
    if isinstance(result, dict):
        payload = dict(result)
        payload["_meta"] = dict(payload.get("_meta") or {})
        payload["_meta"].update(metadata)
        return payload
    return {"result": result, "_meta": dict(metadata)}
