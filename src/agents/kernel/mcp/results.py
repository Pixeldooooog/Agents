from __future__ import annotations

import json
from typing import Any, List

from agents.kernel.mcp.types import MCPPromptArgumentDefinition


def format_mcp_result(result: Any) -> Any:
    content = getattr(result, "content", None)
    if content is None and isinstance(result, dict):
        content = result.get("content")
    if not content:
        return result
    parts: List[str] = []
    for item in content:
        item_type = getattr(item, "type", None) or (item.get("type") if isinstance(item, dict) else "")
        if item_type == "text":
            parts.append(getattr(item, "text", None) or item.get("text", ""))
        else:
            parts.append(json.dumps(item, ensure_ascii=False, sort_keys=True, default=str))
    return "\n".join(part for part in parts if part)


def format_mcp_resource_result(result: Any) -> Any:
    contents = getattr(result, "contents", None)
    if contents is None and isinstance(result, dict):
        contents = result.get("contents")
    if contents is None:
        return result
    formatted = []
    for item in contents:
        if isinstance(item, dict):
            formatted.append(dict(item))
            continue
        payload = {
            "uri": str(getattr(item, "uri", "") or ""),
            "mimeType": str(getattr(item, "mimeType", None) or getattr(item, "mime_type", "") or ""),
        }
        if hasattr(item, "text"):
            payload["text"] = getattr(item, "text")
        if hasattr(item, "blob"):
            payload["blob"] = getattr(item, "blob")
        formatted.append(payload)
    return {"contents": formatted}


def prompt_arguments(raw_arguments: Any) -> List[MCPPromptArgumentDefinition]:
    arguments: List[MCPPromptArgumentDefinition] = []
    for argument in raw_arguments or []:
        if isinstance(argument, dict):
            arguments.append(
                MCPPromptArgumentDefinition(
                    name=str(argument.get("name") or ""),
                    description=str(argument.get("description") or ""),
                    required=bool(argument.get("required")),
                )
            )
            continue
        arguments.append(
            MCPPromptArgumentDefinition(
                name=str(getattr(argument, "name", "") or ""),
                description=str(getattr(argument, "description", "") or ""),
                required=bool(getattr(argument, "required", False)),
            )
        )
    return arguments


def format_mcp_prompt_result(result: Any) -> Any:
    if isinstance(result, dict):
        description = result.get("description", "")
        messages = result.get("messages", [])
    else:
        description = getattr(result, "description", "") or ""
        messages = getattr(result, "messages", []) or []
    return {
        "description": str(description or ""),
        "messages": [_prompt_message_payload(message) for message in messages],
    }


def _prompt_message_payload(message: Any) -> dict[str, Any]:
    if isinstance(message, dict):
        role = str(message.get("role") or "")
        content = message.get("content")
    else:
        role = str(getattr(message, "role", "") or "")
        content = getattr(message, "content", None)
    return {"role": role, "content": _prompt_content_payload(content)}


def _prompt_content_payload(content: Any) -> Any:
    if content is None or isinstance(content, (str, int, float, bool, list, dict)):
        return content
    payload = {"type": str(getattr(content, "type", "") or "")}
    for field_name in ["text", "blob", "mimeType", "mime_type", "uri", "name", "description"]:
        if hasattr(content, field_name):
            payload[field_name] = getattr(content, field_name)
    return {key: value for key, value in payload.items() if value not in ("", None)}
