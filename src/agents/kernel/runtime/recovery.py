from __future__ import annotations

from agents.kernel.schema import Message, ModelResponse, RuntimeEvent

MAX_OUTPUT_TOKENS_RECOVERY_LIMIT = 3
MAX_OUTPUT_STOP_REASONS = {
    "length",
    "max_output_tokens",
    "max_tokens",
    "model_context_window_exceeded",
}
MAX_OUTPUT_RECOVERY_PROMPT = (
    "Output token limit hit. Resume directly - no apology, no recap of what you were doing. "
    "Pick up mid-thought if that is where the cut happened. Break remaining work into smaller pieces."
)


def is_max_output_tokens_response(response: ModelResponse) -> bool:
    return not response.tool_calls and _normalized_stop_reason(response) in MAX_OUTPUT_STOP_REASONS


def max_output_recovery_count(events: list[RuntimeEvent]) -> int:
    return len([event for event in events if event.type == "model_recovery" and event.name == "max_output_tokens"])


def can_recover_max_output_tokens(response: ModelResponse, events: list[RuntimeEvent]) -> bool:
    return is_max_output_tokens_response(response) and max_output_recovery_count(events) < MAX_OUTPUT_TOKENS_RECOVERY_LIMIT


def is_max_output_recovery_exhausted(response: ModelResponse, events: list[RuntimeEvent]) -> bool:
    return is_max_output_tokens_response(response) and max_output_recovery_count(events) >= MAX_OUTPUT_TOKENS_RECOVERY_LIMIT


def max_output_recovery_message(attempt: int) -> Message:
    return Message.from_text(
        "user",
        MAX_OUTPUT_RECOVERY_PROMPT,
        raw={
            "is_meta": True,
            "recovery": {
                "reason": "max_output_tokens",
                "attempt": attempt,
                "max_attempts": MAX_OUTPUT_TOKENS_RECOVERY_LIMIT,
            },
        },
    )


def max_output_recovery_event(response: ModelResponse, attempt: int) -> RuntimeEvent:
    return RuntimeEvent(
        type="model_recovery",
        name="max_output_tokens",
        payload={
            "attempt": attempt,
            "max_attempts": MAX_OUTPUT_TOKENS_RECOVERY_LIMIT,
            "stop_reason": _normalized_stop_reason(response),
            "message": "continuing after model output limit",
        },
    )


def max_output_exhausted_message(response: ModelResponse) -> str:
    stop_reason = _normalized_stop_reason(response) or "max_output_tokens"
    return "model output limit recovery exhausted after %d attempts: %s" % (
        MAX_OUTPUT_TOKENS_RECOVERY_LIMIT,
        stop_reason,
    )


def _normalized_stop_reason(response: ModelResponse) -> str:
    return str(response.stop_reason or "").strip().lower()
