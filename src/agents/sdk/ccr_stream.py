from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any


class SDKCCRStreamAccumulator:
    def __init__(self) -> None:
        self.by_message: dict[str, dict[int, list[str]]] = {}
        self.scope_to_message: dict[str, str] = {}


def accumulate_stream_events(
    buffer: list[dict[str, Any]],
    state: SDKCCRStreamAccumulator,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    touched: dict[tuple[str, int], dict[str, Any]] = {}
    for message in buffer:
        event = message.get("event")
        if not isinstance(event, dict):
            out.append(message)
            continue
        event_type = event.get("type")
        if event_type == "message_start":
            event_message = event.get("message")
            message_id = event_message.get("id") if isinstance(event_message, dict) else None
            if not isinstance(message_id, str):
                out.append(message)
                continue
            previous_id = state.scope_to_message.get(_stream_scope_key(message))
            if previous_id:
                state.by_message.pop(previous_id, None)
            state.scope_to_message[_stream_scope_key(message)] = message_id
            state.by_message[message_id] = {}
            out.append(message)
            continue
        if event_type != "content_block_delta":
            out.append(message)
            continue
        delta = event.get("delta")
        if not isinstance(delta, dict) or delta.get("type") != "text_delta":
            out.append(message)
            continue
        text = delta.get("text")
        if not isinstance(text, str):
            out.append(message)
            continue
        message_id = state.scope_to_message.get(_stream_scope_key(message))
        blocks = state.by_message.get(message_id or "")
        if blocks is None:
            out.append(message)
            continue
        index = event.get("index")
        if not isinstance(index, int):
            out.append(message)
            continue
        chunks = blocks.setdefault(index, [])
        chunks.append(text)
        touched_key = (message_id or "", index)
        existing = touched.get(touched_key)
        if existing is not None:
            existing_event = existing["event"]
            existing_event["delta"]["text"] = "".join(chunks)
            continue
        snapshot = {
            "type": "stream_event",
            "uuid": message.get("uuid") if isinstance(message.get("uuid"), str) else str(uuid.uuid4()),
            "session_id": message.get("session_id"),
            "parent_tool_use_id": message.get("parent_tool_use_id"),
            "event": {
                "type": "content_block_delta",
                "index": index,
                "delta": {"type": "text_delta", "text": "".join(chunks)},
            },
        }
        touched[touched_key] = snapshot
        out.append(snapshot)
    return out


def clear_stream_accumulator_for_message(
    state: SDKCCRStreamAccumulator,
    assistant: dict[str, Any],
) -> None:
    message = assistant.get("message")
    message_id = message.get("id") if isinstance(message, dict) else None
    if not isinstance(message_id, str):
        return
    state.by_message.pop(message_id, None)
    scope = _stream_scope_key(assistant)
    if state.scope_to_message.get(scope) == message_id:
        state.scope_to_message.pop(scope, None)


def _stream_scope_key(message: Mapping[str, Any]) -> str:
    return f"{message.get('session_id')}:{message.get('parent_tool_use_id') or ''}"
