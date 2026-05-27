from __future__ import annotations

import inspect
import json
from dataclasses import dataclass
from typing import Any, Protocol

from agents.kernel.runtime.types import ModelClientProtocol
from agents.kernel.schema import Message, ModelRequest, ToolCall, ToolResult


TOOL_USE_SUMMARY_SYSTEM_PROMPT = """Write a short summary label describing what these tool calls accomplished. It appears as a single-line row in a mobile app and truncates around 30 characters, so think git-commit-subject, not sentence.

Keep the verb in past tense and the most distinctive noun. Drop articles, connectors, and long location context first.

Examples:
- Searched in auth/
- Fixed NPE in UserService
- Created signup endpoint
- Read config.json
- Ran failing tests"""


@dataclass(frozen=True)
class ToolUseSummaryItem:
    name: str
    input: Any
    output: Any
    is_error: bool = False


@dataclass(frozen=True)
class ToolUseSummary:
    summary: str
    source: str = "deterministic"


class ToolUseSummaryGenerator(Protocol):
    source: str

    async def generate_tool_use_summary(
        self,
        items: list[ToolUseSummaryItem],
        *,
        last_assistant_text: str = "",
    ) -> str | None:
        raise NotImplementedError()


class ModelToolUseSummaryGenerator:
    source = "model"

    def __init__(
        self,
        model_client: ModelClientProtocol,
        *,
        protocol: str,
        model: str,
        max_input_chars: int = 300,
        max_output_chars: int = 300,
    ):
        self.model_client = model_client
        self.protocol = protocol
        self.model = model
        self.max_input_chars = max_input_chars
        self.max_output_chars = max_output_chars

    async def generate_tool_use_summary(
        self,
        items: list[ToolUseSummaryItem],
        *,
        last_assistant_text: str = "",
    ) -> str | None:
        if not items:
            return None
        try:
            response = await self.model_client.async_complete(
                ModelRequest(
                    protocol=self.protocol,
                    model=self.model,
                    messages=[
                        Message.from_text("system", TOOL_USE_SUMMARY_SYSTEM_PROMPT),
                        Message.from_text("user", self._user_prompt(items, last_assistant_text=last_assistant_text)),
                    ],
                    metadata={
                        "query_source": "tool_use_summary_generation",
                        "max_tokens": 64,
                    },
                )
            )
        except Exception:
            return None
        return _clean_summary(response.content_text())

    async def async_close(self) -> None:
        close = getattr(self.model_client, "async_close", None)
        if close is not None:
            await close()

    def _user_prompt(self, items: list[ToolUseSummaryItem], *, last_assistant_text: str) -> str:
        tool_summaries = "\n\n".join(self._tool_prompt(item) for item in items)
        context_prefix = ""
        if last_assistant_text:
            context_prefix = "User's intent (from assistant's last message): %s\n\n" % last_assistant_text[:200]
        return "%sTools completed:\n\n%s\n\nLabel:" % (context_prefix, tool_summaries)

    def _tool_prompt(self, item: ToolUseSummaryItem) -> str:
        return "Tool: %s\nInput: %s\nOutput: %s" % (
            item.name,
            _truncate_json(item.input, self.max_input_chars),
            _truncate_json(item.output, self.max_output_chars),
        )


async def build_tool_use_summary(
    generator: ToolUseSummaryGenerator | Any | None,
    results: list[ToolResult],
    calls: list[ToolCall],
    contract_provider: Any,
    *,
    last_assistant_text: str = "",
) -> ToolUseSummary | None:
    if generator is not None:
        generated = await _generate_tool_use_summary(
            generator,
            _tool_summary_items(results, calls),
            last_assistant_text=last_assistant_text,
        )
        if generated:
            source = str(getattr(generator, "source", "generated") or "generated")
            return ToolUseSummary(summary=generated, source=source)

    fallback = deterministic_tool_batch_summary(results, calls, contract_provider)
    if not fallback:
        return None
    return ToolUseSummary(summary=fallback)


def deterministic_tool_batch_summary(
    results: list[ToolResult],
    calls: list[ToolCall],
    contract_provider: Any,
) -> str:
    if len(results) == 1:
        result = results[0]
        call = calls[0] if calls else ToolCall(id=result.tool_call_id, name=result.name, arguments={})
        contract = contract_provider(call)
        activity = contract.get("activity") if isinstance(contract, dict) else {}
        if isinstance(activity, dict) and activity.get("summary"):
            return str(activity["summary"])
        if result.is_error:
            return "Failed %s" % result.name
        return "Ran %s" % result.name
    failures = sum(1 for result in results if result.is_error)
    if failures:
        return "Ran %d tools, %d failed" % (len(results), failures)
    return "Ran %d tools" % len(results)


def _tool_summary_items(results: list[ToolResult], calls: list[ToolCall]) -> list[ToolUseSummaryItem]:
    items: list[ToolUseSummaryItem] = []
    for index, result in enumerate(results):
        call = calls[index] if index < len(calls) else ToolCall(id=result.tool_call_id, name=result.name, arguments={})
        output = result.raw if result.raw is not None else {"content": result.content, "is_error": result.is_error}
        items.append(
            ToolUseSummaryItem(
                name=call.name or result.name,
                input=dict(call.arguments),
                output=output,
                is_error=result.is_error,
            )
        )
    return items


async def _generate_tool_use_summary(
    generator: Any,
    items: list[ToolUseSummaryItem],
    *,
    last_assistant_text: str,
) -> str | None:
    try:
        method = getattr(generator, "generate_tool_use_summary", None)
        response = method(items, last_assistant_text=last_assistant_text) if method is not None else generator(
            items,
            last_assistant_text=last_assistant_text,
        )
        if inspect.isawaitable(response):
            response = await response
    except Exception:
        return None
    return _clean_summary(response)


def _clean_summary(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    return first_line[:120].strip() or None


def _truncate_json(value: Any, max_chars: int) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    except Exception:
        text = "[unable to serialize]"
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 3)] + "..."
