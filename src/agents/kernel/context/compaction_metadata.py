from __future__ import annotations

from typing import Any
from uuid import uuid4

from agents.kernel.schema import Message


def compact_boundary_payload(
    messages: list[Message],
    fitted: list[Message],
    *,
    trigger: str,
    pre_tokens: int,
    post_tokens: int,
) -> dict[str, Any]:
    boundary_uuid = str(uuid4())
    payload: dict[str, Any] = {
        "uuid": boundary_uuid,
        "trigger": trigger,
        "pre_tokens": pre_tokens,
        "post_tokens": post_tokens,
        "before_messages": len(messages),
        "after_messages": len(fitted),
        "dropped_messages": max(0, len(messages) - len(fitted)),
    }
    segment = preserved_segment(messages, fitted, anchor_uuid=boundary_uuid)
    if segment:
        payload["preserved_segment"] = segment
    return payload


def preserved_segment(
    messages: list[Message],
    fitted: list[Message],
    *,
    anchor_uuid: str,
) -> dict[str, str] | None:
    preserved_ids = _preserved_message_ids(messages, fitted)
    if not preserved_ids:
        return None
    return {
        "head_uuid": preserved_ids[0],
        "anchor_uuid": anchor_uuid,
        "tail_uuid": preserved_ids[-1],
    }


def _preserved_message_ids(messages: list[Message], fitted: list[Message]) -> list[str]:
    source_by_identity = {id(message): message for message in messages}
    source_ids = {_message_uuid(message) for message in messages}
    source_ids.discard("")
    preserved: list[str] = []
    seen: set[str] = set()
    for message in fitted:
        candidate = source_by_identity.get(id(message))
        message_id = _message_uuid(candidate or message)
        if not message_id or message_id in seen:
            continue
        if candidate is None and message_id not in source_ids:
            continue
        seen.add(message_id)
        preserved.append(message_id)
    return preserved


def _message_uuid(message: Message | None) -> str:
    if message is None or not isinstance(message.raw, dict):
        return ""
    for key in ("uuid", "message_id", "messageId", "id"):
        value = message.raw.get(key)
        if value:
            return str(value)
    nested = message.raw.get("message")
    if isinstance(nested, dict):
        for key in ("uuid", "message_id", "messageId", "id"):
            value = nested.get(key)
            if value:
                return str(value)
    return ""
