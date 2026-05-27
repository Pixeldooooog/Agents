from __future__ import annotations

import uuid
from typing import Any

from agents.sdk.event_fields import _json_object


def _tool_result_payload_data(payload: dict[str, Any]) -> dict[str, Any]:
    raw = payload.get("raw")
    if isinstance(raw, dict):
        if isinstance(raw.get("result"), str):
            parsed = _json_object(raw["result"])
            if parsed:
                return {**parsed, "_meta": dict(raw.get("_meta") or {})}
        return dict(raw)
    if isinstance(raw, str):
        parsed = _json_object(raw)
        if parsed:
            return parsed
    content = payload.get("content")
    if isinstance(content, str):
        parsed = _json_object(content)
        if parsed:
            return parsed
    return {}


def _tool_call_id(payload: dict[str, Any]) -> str:
    return str(payload.get("id") or payload.get("tool_call_id") or uuid.uuid4())


def _tool_contract(payload: dict[str, Any]) -> dict[str, Any]:
    contract = payload.get("contract")
    return dict(contract) if isinstance(contract, dict) else {}
