from __future__ import annotations

from typing import Any

from agents.kernel.context.compaction import ConversationCompaction, HeuristicContextCompactor
from agents.kernel.context.compaction_prompts import (
    compact_summary_system_prompt,
    compact_summary_user_prompt,
    format_compact_summary,
)
from agents.kernel.schema import Message, ModelRequest


class ModelContextCompactor:
    """Model-backed compactor with deterministic fallback for offline/runtime failures."""

    def __init__(
        self,
        model_client: Any,
        *,
        protocol: str,
        model: str,
        fallback: HeuristicContextCompactor | None = None,
        max_summary_tokens: int = 2048,
    ):
        self.model_client = model_client
        self.protocol = protocol
        self.model = model
        self.fallback = fallback or HeuristicContextCompactor()
        self.max_summary_tokens = max(1, int(max_summary_tokens or 2048))

    def compact(self, messages: list[Message], max_context_tokens: int, target_tokens: int) -> ConversationCompaction:
        return self.fallback.compact(messages, max_context_tokens, target_tokens)

    async def acompact(
        self,
        messages: list[Message],
        max_context_tokens: int,
        target_tokens: int,
    ) -> ConversationCompaction:
        total_tokens = sum(message.approx_token_count() for message in messages)
        if total_tokens <= max_context_tokens:
            return ConversationCompaction("", list(messages), 0, total_tokens, summary_source="none")

        kept = _tail_within_budget(messages, target_tokens)
        dropped = messages[: len(messages) - len(kept)]
        if not dropped:
            return ConversationCompaction("", list(messages), 0, total_tokens, summary_source="none")

        summary = await self._generate_summary(dropped)
        if not summary:
            fallback = self.fallback.compact(messages, max_context_tokens, target_tokens)
            return fallback.with_summary_source("heuristic_fallback")
        return ConversationCompaction(
            summary=summary,
            kept_messages=kept,
            dropped_messages=len(dropped),
            source_token_estimate=total_tokens,
            summary_source="model",
        )

    async def async_close(self) -> None:
        close = getattr(self.model_client, "async_close", None)
        if close is not None:
            await close()

    async def _generate_summary(self, messages: list[Message]) -> str | None:
        try:
            response = await self.model_client.async_complete(
                ModelRequest(
                    protocol=self.protocol,
                    model=self.model,
                    messages=[
                        Message.from_text("system", compact_summary_system_prompt()),
                        Message.from_text("user", compact_summary_user_prompt(messages)),
                    ],
                    metadata={
                        "query_source": "compact",
                        "max_tokens": self.max_summary_tokens,
                        "is_compaction": True,
                    },
                )
            )
        except Exception:
            return None
        return _clean_model_summary(response.content_text())


def _tail_within_budget(messages: list[Message], target_tokens: int) -> list[Message]:
    kept: list[Message] = []
    kept_tokens = 0
    for message in reversed(messages):
        message_tokens = message.approx_token_count()
        if kept and kept_tokens + message_tokens > target_tokens:
            break
        kept.append(message)
        kept_tokens += message_tokens
    kept.reverse()
    return kept


def _clean_model_summary(value: Any) -> str | None:
    summary = format_compact_summary(str(value or ""))
    return summary or None
