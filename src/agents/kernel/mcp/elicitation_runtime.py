from __future__ import annotations

import html
import inspect
from typing import Any


def build_mcp_elicitation_complete_handler(context: Any) -> Any:
    async def handle(server_name: str, elicitation_id: str) -> None:
        payload = {
            "mcp_server_name": str(server_name or ""),
            "elicitation_id": str(elicitation_id or ""),
        }
        _completion_records(context).append(payload)
        if _has_runtime_event_sink(context):
            context.emit_runtime_event("elicitation_complete", name="mcp", payload=payload)
            return
        enqueue = getattr(context, "async_message_enqueue", None)
        if enqueue is None:
            return
        result = enqueue(_completion_async_message(payload))
        if inspect.isawaitable(result):
            await result

    return handle


def _completion_records(context: Any) -> list[dict[str, str]]:
    records = getattr(context, "mcp_elicitation_completions", None)
    if not isinstance(records, list):
        records = []
        setattr(context, "mcp_elicitation_completions", records)
    return records


def _has_runtime_event_sink(context: Any) -> bool:
    active = getattr(context, "has_runtime_event_sink", None)
    if active is None:
        return False
    return bool(active())


def _completion_async_message(payload: dict[str, str]) -> dict[str, Any]:
    return {
        "type": "user",
        "message": {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": _completion_text(payload),
                }
            ],
        },
        "priority": "later",
        "isReplay": False,
        "isSynthetic": True,
    }


def _completion_text(payload: dict[str, str]) -> str:
    return "\n".join(
        [
            "<mcp_elicitation_complete>",
            "<server>%s</server>" % html.escape(payload["mcp_server_name"]),
            "<elicitation_id>%s</elicitation_id>" % html.escape(payload["elicitation_id"]),
            "</mcp_elicitation_complete>",
        ]
    )
