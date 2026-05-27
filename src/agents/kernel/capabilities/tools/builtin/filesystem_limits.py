from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from agents.kernel.capabilities.sandbox.text import (
    DEFAULT_TEXT_READ_MAX_BYTES,
    estimate_text_read_tokens,
    normalize_text_read_max_bytes,
    normalize_text_read_max_tokens,
    text_file_too_many_tokens_message,
)
from agents.kernel.capabilities.tools.context import ToolRuntimeContext


def validate_text_read_tokens(context: ToolRuntimeContext, content: str, path: str) -> None:
    max_tokens = effective_text_read_max_tokens(context)
    token_count = estimate_text_read_tokens(content, Path(path).suffix)
    if token_count > max_tokens:
        raise ValueError(text_file_too_many_tokens_message(token_count, max_tokens))


def effective_text_read_max_tokens(context: ToolRuntimeContext) -> int:
    return normalize_text_read_max_tokens(_effective_file_reading_limit(context, "maxTokens"))


def effective_text_read_max_bytes(context: ToolRuntimeContext, explicit_max_bytes: int | None) -> int:
    if explicit_max_bytes is not None:
        return normalize_text_read_max_bytes(explicit_max_bytes)
    return normalize_text_read_max_bytes(_effective_file_reading_limit(context, "maxSizeBytes") or DEFAULT_TEXT_READ_MAX_BYTES)


def _effective_file_reading_limit(context: ToolRuntimeContext, key: str) -> int | None:
    direct_limits = getattr(context, "file_reading_limits", None)
    value = _limit_value(direct_limits, key)
    if value is None:
        metadata = getattr(getattr(context, "agent_spec", None), "metadata", None)
        spec_limits = metadata.get("fileReadingLimits") if isinstance(metadata, dict) else None
        value = _limit_value(spec_limits, key)
    return value


def _limit_value(limits: Any, key: str) -> int | None:
    if not isinstance(limits, dict):
        return None
    value = limits.get(key) if key in limits else limits.get(_camel_to_snake(key))
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return None
    return normalized if normalized > 0 else None


def _camel_to_snake(value: str) -> str:
    return re.sub(r"(?<!^)([A-Z])", r"_\1", value).lower()
