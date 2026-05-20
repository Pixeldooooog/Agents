from __future__ import annotations

from typing import Any


STRUCTURED_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {},
    "additionalProperties": True,
}


def structured_output(**payload: Any) -> dict[str, Any]:
    return {
        "data": "Structured output provided successfully",
        "structured_output": dict(payload),
    }


def format_structured_output_result(result: Any) -> str:
    if isinstance(result, dict) and result.get("data"):
        return str(result["data"])
    return "Structured output provided successfully"


def structured_output_schema_from_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    schema = (metadata or {}).get("structured_output_schema")
    if not isinstance(schema, dict):
        return dict(STRUCTURED_OUTPUT_SCHEMA)
    return _normalize_object_schema(schema)


def _normalize_object_schema(schema: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(schema)
    schema_type = normalized.get("type", "object")
    if schema_type != "object":
        raise ValueError("structured_output_schema must be an object JSON schema")
    normalized["type"] = "object"
    if not isinstance(normalized.get("properties"), dict):
        normalized["properties"] = {}
    return normalized
