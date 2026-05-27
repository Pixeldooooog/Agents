from __future__ import annotations

from typing import Any, Dict

from agents.kernel.capabilities.tools.contracts import ToolDefinition


def validate_tool_arguments(tool: ToolDefinition, arguments: Dict[str, Any]) -> str:
    if not tool.strict_input_schema:
        return ""
    schema = dict(tool.parameters or {})
    if not schema:
        return ""
    if schema.get("type") not in ("object", None):
        return ""
    properties = dict(schema.get("properties") or {})
    required = [str(item) for item in schema.get("required") or []]
    for key in required:
        if key not in arguments:
            return "missing required argument: %s" % key
    if schema.get("additionalProperties") is False:
        for key in arguments:
            if key not in properties:
                return "unexpected argument: %s" % key
    for key, value in arguments.items():
        if key not in properties:
            continue
        error = _validate_json_schema_value(key, value, dict(properties[key] or {}))
        if error:
            return error
    return ""


def _validate_json_schema_value(path: str, value: Any, schema: Dict[str, Any]) -> str:
    if "enum" in schema and value not in list(schema.get("enum") or []):
        return "%s must be one of %s" % (path, ", ".join(map(str, schema.get("enum") or [])))
    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        if any(_json_schema_type_matches(value, str(item)) for item in schema_type):
            return ""
        return "%s must match one of: %s" % (path, ", ".join(map(str, schema_type)))
    if schema_type and not _json_schema_type_matches(value, str(schema_type)):
        return "%s must be %s" % (path, schema_type)
    if schema_type == "object":
        if not isinstance(value, dict):
            return "%s must be object" % path
        properties = dict(schema.get("properties") or {})
        for key in schema.get("required") or []:
            if key not in value:
                return "missing required argument: %s.%s" % (path, key)
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in properties:
                    return "unexpected argument: %s.%s" % (path, key)
        for key, nested in properties.items():
            if key in value:
                error = _validate_json_schema_value("%s.%s" % (path, key), value[key], dict(nested or {}))
                if error:
                    return error
    if schema_type == "array":
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                error = _validate_json_schema_value("%s[%d]" % (path, index), item, dict(item_schema))
                if error:
                    return error
    return ""


def _json_schema_type_matches(value: Any, schema_type: str) -> bool:
    if schema_type == "string":
        return isinstance(value, str)
    if schema_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if schema_type == "number":
        return (isinstance(value, int) or isinstance(value, float)) and not isinstance(value, bool)
    if schema_type == "boolean":
        return isinstance(value, bool)
    if schema_type == "object":
        return isinstance(value, dict)
    if schema_type == "array":
        return isinstance(value, list)
    if schema_type == "null":
        return value is None
    return True
