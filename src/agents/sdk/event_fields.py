from __future__ import annotations

import asyncio
import json
import time
from typing import Any


def _json_object(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return dict(parsed) if isinstance(parsed, dict) else {}


def _json_list(value: str) -> list[Any]:
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return []
    return list(parsed) if isinstance(parsed, list) else []


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _dict_field(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _optional_dict_field(value: Any) -> dict[str, Any] | None:
    return dict(value) if isinstance(value, dict) else None


def _dict_list_field(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _millis(timestamp: float) -> float:
    return timestamp * 1000


def _truncate(value: str, *, limit: int = 500) -> str:
    value = value.strip()
    return value if len(value) <= limit else value[: limit - 3] + "..."


def _first_non_empty(values) -> str:
    for value in values:
        text = str(value or "")
        if text:
            return text
    return ""


def _text_field(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if value is not None:
            return str(value)
    return ""


def _nullable_text_field(payload: dict[str, Any], *keys: str) -> str | None:
    text = _text_field(payload, *keys)
    return text or None


def _string_list_field(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item or "")]


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return _int(value)


def _duration_ms(started_at: float) -> int:
    return int((time.monotonic() - started_at) * 1000)


def _is_sdk_interrupt_cancel(exc: asyncio.CancelledError) -> bool:
    return bool(exc.args) and str(exc.args[0]) == "interrupt"
