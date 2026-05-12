from __future__ import annotations

import json
import time
from typing import Any

from agents.kernel.capabilities.tools.context import ToolRuntimeContext


SESSION_STATUS_SCHEMA = {"type": "object", "properties": {}}

SESSION_EXPORT_SCHEMA = {
    "type": "object",
    "properties": {
        "path": {"type": "string", "description": "Workspace-relative export path. Defaults to .agents/exports/<timestamp>.json or .md."},
        "format": {"type": "string", "enum": ["json", "markdown"]},
        "include_system": {"type": "boolean"},
    },
}

SESSION_SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "include_system": {"type": "boolean"},
        "max_messages": {"type": "integer", "minimum": 1, "maximum": 200},
        "max_chars": {"type": "integer", "minimum": 80, "maximum": 20000},
    },
}

CONTEXT_TRACE_SCHEMA = {
    "type": "object",
    "properties": {
        "include_text": {"type": "boolean"},
        "max_chars": {"type": "integer", "minimum": 0, "maximum": 20000},
    },
}

CONTEXT_MESSAGES_SCHEMA = {
    "type": "object",
    "properties": {
        "include_system": {"type": "boolean"},
        "max_messages": {"type": "integer", "minimum": 1, "maximum": 200},
        "max_chars": {"type": "integer", "minimum": 0, "maximum": 20000},
    },
}

CONTEXT_COMPACT_SCHEMA = {
    "type": "object",
    "properties": {
        "target_tokens": {"type": "integer", "minimum": 1},
    },
}

CONTEXT_REWIND_SCHEMA = {
    "type": "object",
    "properties": {
        "drop_last": {"type": "integer", "minimum": 1, "description": "Number of recent non-system messages to remove."},
    },
}


def session_status(context: ToolRuntimeContext) -> dict[str, Any]:
    session = _session(context)
    runtime = getattr(session, "runtime", None)
    workspace = context.workspace
    messages = list(getattr(session, "messages", []) or [])
    return {
        "workspace": {
            "tenant_id": workspace.tenant_id,
            "user_id": workspace.user_id,
            "agent_id": workspace.agent_id,
            "workspace_id": workspace.workspace_id,
            "path": str(workspace.path),
        },
        "model": {
            "protocol": str(getattr(runtime, "protocol", "") or ""),
            "model": str(getattr(runtime, "model", "") or ""),
        },
        "tools": list(getattr(runtime, "enabled_tools", None) or context.enabled_tools),
        "messages": {
            "total": len(messages),
            "non_system": len([message for message in messages if getattr(message, "role", "") != "system"]),
            "estimated_tokens": _estimate_tokens(session, messages),
            "max_context_tokens": int(getattr(session, "max_context_tokens", 0) or 0),
        },
        "context_trace": len(getattr(session, "context_trace", []) or []),
        "todos": _todo_summary(context),
        "plan_mode": bool(getattr(context, "plan_mode", False)),
    }


def session_export(
    context: ToolRuntimeContext,
    path: str = "",
    format: str = "json",
    include_system: bool = False,
) -> dict[str, Any]:
    session = _session(context)
    export_format = _export_format(format)
    target = _export_path(path, export_format)
    messages = _filtered_messages(session, include_system=bool(include_system))
    content = _session_export_content(context, session, messages, format=export_format)
    result = context.sandbox_client.write_text(target, content)
    return {"path": result.path, "bytes": result.bytes, "format": export_format, "messages": len(messages)}


def session_summary(
    context: ToolRuntimeContext,
    include_system: bool = False,
    max_messages: int = 50,
    max_chars: int = 2000,
) -> dict[str, Any]:
    session = _session(context)
    messages = _filtered_messages(session, include_system=bool(include_system))
    limit = max(1, min(int(max_messages or 50), 200))
    selected = messages[-limit:]
    char_limit = max(80, min(int(max_chars or 2000), 20000))
    summary = _conversation_summary(selected, max_chars=char_limit)
    return {
        "summary": summary,
        "messages": len(selected),
        "total": len(messages),
        "roles": _role_counts(selected),
        "truncated": len(summary) >= char_limit,
    }


def context_trace(context: ToolRuntimeContext, include_text: bool = False, max_chars: int = 240) -> dict[str, Any]:
    session = _session(context)
    limit = max(0, min(int(max_chars or 0), 20000))
    items = [_trace_item_payload(item, include_text=bool(include_text), max_chars=limit) for item in getattr(session, "context_trace", []) or []]
    return {"items": items, "count": len(items)}


def context_messages(
    context: ToolRuntimeContext,
    include_system: bool = False,
    max_messages: int = 50,
    max_chars: int = 240,
) -> dict[str, Any]:
    session = _session(context)
    messages = list(getattr(session, "messages", []) or [])
    if not include_system:
        messages = [message for message in messages if getattr(message, "role", "") != "system"]
    limit = max(1, min(int(max_messages or 50), 200))
    char_limit = max(0, min(int(max_chars or 0), 20000))
    selected = messages[-limit:]
    return {
        "messages": [_message_payload(index, message, max_chars=char_limit) for index, message in enumerate(selected, start=max(0, len(messages) - len(selected)))],
        "count": len(selected),
        "total": len(messages),
    }


def context_compact(context: ToolRuntimeContext, target_tokens: int | None = None) -> dict[str, Any]:
    session = _session(context)
    compact = getattr(session, "compact", None)
    if compact is None:
        raise RuntimeError("session does not support context compaction")
    target = int(target_tokens or 0) or None
    return compact(target)


def context_rewind(context: ToolRuntimeContext, drop_last: int = 1) -> dict[str, Any]:
    session = _session(context)
    count = max(1, int(drop_last or 1))
    messages = list(getattr(session, "messages", []) or [])
    kept, dropped = _drop_last_non_system(messages, count)
    session.messages = kept
    return {
        "before_messages": len(messages),
        "after_messages": len(kept),
        "dropped_messages": dropped,
    }


def _session(context: ToolRuntimeContext) -> Any:
    session = getattr(context, "session", None)
    if session is None:
        raise RuntimeError("session is not available")
    return session


def _trace_item_payload(item: Any, *, include_text: bool, max_chars: int) -> dict[str, Any]:
    layer = getattr(getattr(item, "layer", None), "value", getattr(item, "layer", ""))
    payload = {
        "id": str(getattr(item, "id", "") or ""),
        "layer": str(layer or ""),
        "source": str(getattr(item, "source", "") or ""),
        "priority": int(getattr(item, "priority", 0) or 0),
        "included": bool(getattr(item, "included", False)),
        "tokens": int(getattr(item, "tokens", 0) or 0),
    }
    text = str(getattr(item, "text", "") or "")
    if include_text:
        payload["text"] = _truncate(text, max_chars)
    else:
        payload["preview"] = _truncate(" ".join(text.split()), max_chars)
    return payload


def _message_payload(index: int, message: Any, *, max_chars: int) -> dict[str, Any]:
    tool_calls = getattr(message, "tool_calls", []) or []
    return {
        "index": index,
        "role": str(getattr(message, "role", "") or ""),
        "content": _truncate(_message_text(message), max_chars),
        "tool_calls": [str(getattr(call, "name", "") or "") for call in tool_calls],
    }


def _message_text(message: Any) -> str:
    content_text = getattr(message, "content_text", None)
    if content_text is not None:
        return str(content_text() or "")
    return str(getattr(message, "content", "") or "")


def _conversation_summary(messages: list[Any], *, max_chars: int) -> str:
    if not messages:
        return "No conversation messages yet."
    lines = ["Session summary:"]
    for message in messages:
        role = str(getattr(message, "role", "") or "message")
        text = " ".join(_message_text(message).split())
        if not text:
            tool_calls = [str(getattr(call, "name", "") or "") for call in getattr(message, "tool_calls", []) or []]
            text = "tool calls: %s" % ", ".join(tool_calls) if tool_calls else "(empty)"
        lines.append("- %s: %s" % (role, text[:240]))
    summary = "\n".join(lines)
    return _truncate(summary, max_chars)


def _role_counts(messages: list[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for message in messages:
        role = str(getattr(message, "role", "") or "message")
        counts[role] = counts.get(role, 0) + 1
    return counts


def _filtered_messages(session: Any, *, include_system: bool) -> list[Any]:
    messages = list(getattr(session, "messages", []) or [])
    if include_system:
        return messages
    return [message for message in messages if getattr(message, "role", "") != "system"]


def _session_export_content(context: ToolRuntimeContext, session: Any, messages: list[Any], *, format: str) -> str:
    runtime = getattr(session, "runtime", None)
    payload = {
        "exported_at": time.time(),
        "workspace": {
            "tenant_id": context.workspace.tenant_id,
            "user_id": context.workspace.user_id,
            "agent_id": context.workspace.agent_id,
            "workspace_id": context.workspace.workspace_id,
            "path": str(context.workspace.path),
        },
        "model": {
            "protocol": str(getattr(runtime, "protocol", "") or ""),
            "model": str(getattr(runtime, "model", "") or ""),
        },
        "messages": [message.to_dict() if hasattr(message, "to_dict") else {"role": getattr(message, "role", ""), "content": _message_text(message)} for message in messages],
    }
    if format == "json":
        return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    lines = [
        "# Session Export",
        "",
        "- Model: %s / %s" % (payload["model"]["protocol"] or "-", payload["model"]["model"] or "-"),
        "- Workspace: %s" % payload["workspace"]["path"],
        "- Messages: %s" % len(messages),
        "",
    ]
    for message in messages:
        lines.extend(["## %s" % str(getattr(message, "role", "") or "message"), "", _message_text(message), ""])
    return "\n".join(lines).rstrip() + "\n"


def _drop_last_non_system(messages: list[Any], count: int) -> tuple[list[Any], int]:
    kept = list(messages)
    dropped = 0
    index = len(kept) - 1
    while index >= 0 and dropped < count:
        if getattr(kept[index], "role", "") != "system":
            kept.pop(index)
            dropped += 1
        index -= 1
    return kept, dropped


def _export_format(value: str) -> str:
    normalized = str(value or "json").strip().lower()
    if normalized in {"md", "markdown"}:
        return "markdown"
    if normalized == "json":
        return "json"
    raise ValueError("format must be json or markdown")


def _export_path(path: str, format: str) -> str:
    text = str(path or "").strip()
    suffix = "md" if format == "markdown" else "json"
    if not text:
        return ".agents/exports/session-%s.%s" % (time.strftime("%Y%m%d%H%M%S"), suffix)
    if text.endswith("/") or text.endswith("\\"):
        raise ValueError("export path must include a file name")
    if "/../" in text or text.startswith("../") or text in {".", ".."}:
        raise ValueError("export path must stay inside the workspace")
    return text


def _estimate_tokens(session: Any, messages: list[Any]) -> int:
    estimate = getattr(session, "_estimate_tokens", None)
    if estimate is None:
        return 0
    return int(estimate(messages) or 0)


def _todo_summary(context: ToolRuntimeContext) -> dict[str, int]:
    summary = {"pending": 0, "in_progress": 0, "completed": 0}
    for item in getattr(context, "todos", []) or []:
        status = str(item.get("status") or "")
        if status in summary:
            summary[status] += 1
    return summary


def _truncate(value: str, max_chars: int) -> str:
    text = str(value or "")
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n[truncated]"
