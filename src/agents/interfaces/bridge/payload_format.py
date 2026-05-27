from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from agents.interfaces.bridge.sessions import TerminalSessionRecord
from agents.kernel.schema import Message


def _compact_text(value: str, limit: int = 96) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _context_layer_counts(items: list[Any]) -> str:
    counts: dict[str, int] = {}
    for item in items:
        layer = getattr(getattr(item, "layer", ""), "value", getattr(item, "layer", ""))
        key = str(layer or "unknown")
        counts[key] = counts.get(key, 0) + 1
    return ", ".join("%s:%s" % (key, value) for key, value in sorted(counts.items())) or "none"


def _safe_len(factory) -> int:
    try:
        return len(factory())
    except Exception:
        return 0


def _catalog_count(rows: list[list[str]], sentinel: str) -> int:
    if len(rows) == 1 and rows[0][0] == sentinel and ("none" in rows[0][1] or "not " in rows[0][1]):
        return 0
    return len(rows)


def _join_limited(values: list[str], limit: int = 6) -> str:
    if not values:
        return "none"
    shown = values[:limit]
    suffix = " +%s more" % (len(values) - limit) if len(values) > limit else ""
    return ", ".join(shown) + suffix


def session_records_payload(records: list[TerminalSessionRecord]) -> list[dict[str, str]]:
    return [
        {
            "id": record.session_id,
            "short_id": short_session_id(record.session_id),
            "updated": format_timestamp(record.updated_at),
            "model": record.model,
            "messages": str(record.message_count),
            "workspace": short_path(record.workspace_path) if record.workspace_path else "",
        }
        for record in records
    ]


def messages_payload(messages: list[Message]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for message in messages:
        role = str(message.role)
        if role == "system":
            continue
        content = message.content_text()
        if not content and message.tool_calls:
            content = "tool calls: %s" % ", ".join(call.name for call in message.tool_calls)
        if not content:
            continue
        rows.append({"role": role, "content": content})
    return rows


def estimate_session_tokens(session: Any) -> str:
    try:
        return str(session._estimate_tokens(getattr(session, "messages", [])))
    except Exception:
        return "unknown"


def parse_positive_int(value: str) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = int(text)
    except ValueError:
        return None
    return parsed if parsed > 0 else None


def _csv_setting(raw: str) -> list[str]:
    return [item.strip() for item in str(raw or "").split(",") if item.strip()]


def short_session_id(session_id: str) -> str:
    return str(session_id).replace("session_", "", 1)


def format_timestamp(value: float) -> str:
    if not value:
        return ""
    return datetime.datetime.fromtimestamp(value).strftime("%Y-%m-%d %H:%M")


def model_base_url(session: Any) -> str:
    runtime = getattr(session, "runtime", None)
    model_client = getattr(runtime, "model_client", None)
    config = getattr(model_client, "config", None)
    return str(getattr(config, "base_url", "") or "")


def model_endpoint(session: Any) -> str:
    base_url = model_base_url(session)
    if not base_url:
        return ""
    parsed = urlparse(base_url)
    return parsed.netloc or base_url


def short_path(path: str) -> str:
    try:
        value = Path(path).expanduser()
        home = Path.home()
        return "~/%s" % value.relative_to(home) if value.is_relative_to(home) else str(value)
    except Exception:
        return str(path)
