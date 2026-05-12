from __future__ import annotations

from typing import Any

from agents.kernel.capabilities.tools.context import ToolRuntimeContext


MCP_PROMPTS_SCHEMA = {
    "type": "object",
    "properties": {
        "server": {"type": "string", "description": "Optional MCP server name filter."},
        "query": {"type": "string", "description": "Optional text filter over prompt name and description."},
        "max_results": {"type": "integer", "minimum": 1, "maximum": 100},
    },
}

MCP_GET_PROMPT_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "Prompt name to render."},
        "server": {"type": "string", "description": "Optional MCP server name."},
        "arguments": {"type": "object", "additionalProperties": True},
    },
    "required": ["name"],
}


async def mcp_prompts(
    context: ToolRuntimeContext,
    server: str = "",
    query: str = "",
    max_results: int = 50,
) -> dict[str, Any]:
    prompts: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    needle = str(query or "").strip().lower()
    for provider in _providers(context, server=server):
        try:
            for prompt in await provider.list_prompts():
                payload = _prompt_payload(provider, prompt)
                if needle and needle not in _prompt_haystack(payload):
                    continue
                prompts.append(payload)
        except Exception as exc:  # noqa: BLE001 - model should see unavailable prompt servers.
            errors.append({"server": provider.server.name, "error": str(exc)})
    limit = max(1, min(int(max_results or 50), 100))
    return {
        "prompts": prompts[:limit],
        "count": min(len(prompts), limit),
        "total": len(prompts),
        "errors": errors,
    }


async def mcp_get_prompt(
    context: ToolRuntimeContext,
    name: str,
    server: str = "",
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    prompt_name = _required_text(name, "name")
    errors: list[dict[str, str]] = []
    for provider in _providers(context, server=server):
        try:
            return {
                "server": provider.server.name,
                "name": prompt_name,
                "content": await provider.get_prompt(prompt_name, arguments or {}),
            }
        except Exception as exc:  # noqa: BLE001 - try the next matching server when server is omitted.
            errors.append({"server": provider.server.name, "error": str(exc)})
            if server:
                break
    if not _providers(context, server=server):
        raise RuntimeError("no MCP prompt servers available")
    raise RuntimeError("failed to get MCP prompt %s: %s" % (prompt_name, errors))


def _providers(context: ToolRuntimeContext, server: str = "") -> list[Any]:
    wanted = str(server or "").strip()
    providers = list(getattr(context, "mcp_providers", []) or [])
    if wanted:
        providers = [provider for provider in providers if getattr(getattr(provider, "server", None), "name", "") == wanted]
    return providers


def _prompt_payload(provider: Any, prompt: Any) -> dict[str, Any]:
    return {
        "server": provider.server.name,
        "name": str(getattr(prompt, "name", "") or ""),
        "description": str(getattr(prompt, "description", "") or ""),
        "arguments": [
            {
                "name": str(getattr(argument, "name", "") or ""),
                "description": str(getattr(argument, "description", "") or ""),
                "required": bool(getattr(argument, "required", False)),
            }
            for argument in getattr(prompt, "arguments", []) or []
        ],
    }


def _prompt_haystack(payload: dict[str, Any]) -> str:
    arguments = payload.get("arguments") or []
    return " ".join(
        [
            str(payload.get("name") or ""),
            str(payload.get("description") or ""),
            " ".join(str(item.get("name") or "") for item in arguments if isinstance(item, dict)),
        ]
    ).lower()


def _required_text(value: Any, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError("%s is required" % name)
    return text
