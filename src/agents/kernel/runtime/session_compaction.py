from __future__ import annotations

from agents.kernel.context.compaction_metadata import compact_boundary_payload
from agents.kernel.schema import Message, RuntimeEvent


def compact_status_event(status: str | None) -> RuntimeEvent:
    return RuntimeEvent(
        type="status",
        name="context",
        payload={"status": status},
    )


def should_emit_compact_status(messages: list[Message], *, max_context_tokens: int) -> bool:
    if not messages:
        return False
    return sum(message.approx_token_count() for message in messages) > max_context_tokens


def compact_boundary_event(
    messages: list[Message],
    fitted: list[Message],
    *,
    trigger: str,
    pre_tokens: int,
    post_tokens: int,
) -> RuntimeEvent | None:
    if len(fitted) == len(messages) and post_tokens >= pre_tokens:
        return None
    return RuntimeEvent(
        type="compact_boundary",
        name="context",
        payload=compact_boundary_payload(
            messages,
            fitted,
            trigger=trigger,
            pre_tokens=pre_tokens,
            post_tokens=post_tokens,
        ),
    )


def compact_stats(
    *,
    before_messages: int,
    before_tokens: int,
    after_messages: int,
    after_tokens: int,
) -> dict[str, int]:
    return {
        "before_messages": before_messages,
        "after_messages": after_messages,
        "dropped_messages": max(0, before_messages - after_messages),
        "before_tokens": before_tokens,
        "after_tokens": after_tokens,
    }
