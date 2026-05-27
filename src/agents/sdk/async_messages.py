from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Literal

from agents.sdk.types import SDKUserMessage


@dataclass
class _SDKAsyncMessageQueueItem:
    sequence: int
    message: SDKUserMessage


def _coerce_async_user_message(
    message: SDKUserMessage | dict[str, Any] | str,
    *,
    session_id: str = "",
    priority: Literal["now", "next", "later"] | None = None,
) -> SDKUserMessage:
    if isinstance(message, SDKUserMessage):
        values = message.model_dump()
    elif isinstance(message, dict):
        values = dict(message)
    else:
        values = {
            "type": "user",
            "session_id": session_id,
            "uuid": "msg_%s" % uuid.uuid4().hex,
            "message": {"role": "user", "content": [{"type": "text", "text": str(message)}]},
            "priority": priority,
            "isReplay": False,
        }
    if session_id:
        values["session_id"] = session_id
    values.setdefault("type", "user")
    values.setdefault("session_id", session_id)
    values["uuid"] = str(values.get("uuid") or "msg_%s" % uuid.uuid4().hex)
    if priority is not None:
        values["priority"] = priority
    elif not values.get("priority"):
        values["priority"] = "next"
    if "message" not in values:
        values["message"] = {"role": "user", "content": []}
    values.setdefault("isReplay", False)
    return SDKUserMessage.model_validate(values)


def _sorted_async_message_items(items: list[_SDKAsyncMessageQueueItem]) -> list[_SDKAsyncMessageQueueItem]:
    return sorted(items, key=lambda item: (_async_message_priority(item.message.priority), item.sequence))


def _async_message_priority_value(message: dict[str, Any]) -> Literal["now", "next", "later"] | None:
    value = str(message.get("priority") or "")
    return value if value in {"now", "next", "later"} else None


def _async_message_priority(value: str | None) -> int:
    if value == "now":
        return 0
    if value == "later":
        return 2
    return 1
