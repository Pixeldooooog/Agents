from __future__ import annotations

from agents.kernel.schema import Message


def user_message(text: str, message_id: str | None = None) -> Message:
    if not message_id:
        return Message.from_text("user", text)
    return Message.from_text(
        "user",
        text,
        raw={"uuid": str(message_id), "message_id": str(message_id)},
    )
