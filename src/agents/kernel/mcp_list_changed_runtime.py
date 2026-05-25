from __future__ import annotations

import html
import inspect
from typing import Any

from agents.kernel.capabilities.tools.registry import ToolRegistry


_LIST_CHANGED_KINDS = {"tools", "prompts", "resources"}


def build_mcp_list_changed_handler(context: Any, registry: Any) -> Any:
    async def handle(server_name: str, kind: str) -> None:
        payload: dict[str, Any] = {
            "mcp_server_name": str(server_name or ""),
            "kind": _normalize_kind(kind),
        }
        try:
            payload.update(await _handle_list_changed(context, registry, payload["mcp_server_name"], payload["kind"]))
        except Exception as exc:  # noqa: BLE001 - MCP notifications must not break the client reader.
            payload.update({"refreshed": False, "error": str(exc)})
        _list_changed_records(context).append(payload)
        await _emit_or_enqueue(context, payload)

    return handle


async def _handle_list_changed(context: Any, registry: Any, server_name: str, kind: str) -> dict[str, Any]:
    if kind == "unknown":
        return {"refreshed": False, "reason": "unsupported_kind"}
    if kind == "prompts":
        return await _refresh_prompts_for_server(context, server_name)
    if kind == "resources":
        return await _refresh_resources_for_server(context, server_name)
    if registry is None:
        return {"refreshed": False, "reason": "missing_registry"}
    return await _refresh_tools_for_server(context, registry, server_name)


async def _refresh_tools_for_server(context: Any, registry: Any, server_name: str) -> dict[str, Any]:
    providers = _providers_for_server(context, server_name)
    if not providers:
        return {"refreshed": False, "reason": "server_not_loaded"}

    staging = ToolRegistry()
    for provider in providers:
        await provider.load_tools(staging)
    definitions = _definitions_for_server(staging, server_name)
    removed_tools = _unregister_definitions_for_server(registry, server_name)
    for definition in definitions:
        registry.register_definition(definition)
    loaded_tools = _canonical_tool_names(definitions)
    _replace_enabled_tools(context, removed_tools, loaded_tools)
    return {
        "refreshed": True,
        "removed_tools": removed_tools,
        "loaded_tools": loaded_tools,
    }


async def _refresh_prompts_for_server(context: Any, server_name: str) -> dict[str, Any]:
    providers = _providers_for_server(context, server_name)
    if not providers:
        return {"refreshed": False, "reason": "server_not_loaded"}
    prompts: list[Any] = []
    for provider in providers:
        prompts.extend(await provider.list_prompts(refresh=True))
    loaded_prompts = sorted(str(getattr(prompt, "name", "") or "") for prompt in prompts if getattr(prompt, "name", ""))
    return {
        "refreshed": True,
        "prompt_count": len(prompts),
        "loaded_prompts": loaded_prompts,
    }


async def _refresh_resources_for_server(context: Any, server_name: str) -> dict[str, Any]:
    providers = _providers_for_server(context, server_name)
    if not providers:
        return {"refreshed": False, "reason": "server_not_loaded"}
    resources: list[Any] = []
    for provider in providers:
        resources.extend(await provider.list_resources(refresh=True))
    loaded_resources = sorted(str(getattr(resource, "uri", "") or "") for resource in resources if getattr(resource, "uri", ""))
    return {
        "refreshed": True,
        "resource_count": len(resources),
        "loaded_resources": loaded_resources,
    }


def _normalize_kind(kind: str) -> str:
    value = str(kind or "").strip().lower()
    return value if value in _LIST_CHANGED_KINDS else "unknown"


def _providers_for_server(context: Any, server_name: str) -> list[Any]:
    return [provider for provider in list(getattr(context, "mcp_providers", []) or []) if _provider_name(provider) == server_name]


def _provider_name(provider: Any) -> str:
    return str(getattr(getattr(provider, "server", None), "name", "") or "")


def _definitions_for_server(registry: Any, server_name: str) -> list[Any]:
    definitions_matching = getattr(registry, "definitions_matching", None)
    if definitions_matching is None:
        return []
    return definitions_matching(lambda definition: _definition_mcp_server(definition) == server_name)


def _unregister_definitions_for_server(registry: Any, server_name: str) -> list[str]:
    unregister_matching = getattr(registry, "unregister_matching", None)
    if unregister_matching is None:
        return []
    return unregister_matching(lambda definition: _definition_mcp_server(definition) == server_name)


def _definition_mcp_server(definition: Any) -> str:
    metadata = getattr(definition, "metadata", None)
    info = metadata.get("mcp_info") if isinstance(metadata, dict) else None
    if not isinstance(info, dict):
        return ""
    return str(info.get("server") or "")


def _canonical_tool_names(definitions: list[Any]) -> list[str]:
    return sorted(
        str(getattr(definition, "name", "") or "")
        for definition in definitions
        if str(getattr(definition, "name", "") or "").startswith("mcp__")
    )


def _replace_enabled_tools(context: Any, removed_tools: list[str], loaded_tools: list[str]) -> None:
    removed = set(removed_tools)
    previous = [tool for tool in list(getattr(context, "enabled_tools", []) or []) if tool not in removed]
    context.enabled_tools = _merge_unique(previous, loaded_tools)


def _merge_unique(*groups: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for group in groups:
        for value in group:
            item = str(value or "")
            if not item or item in seen:
                continue
            seen.add(item)
            result.append(item)
    return result


def _list_changed_records(context: Any) -> list[dict[str, Any]]:
    records = getattr(context, "mcp_list_changed_notifications", None)
    if not isinstance(records, list):
        records = []
        setattr(context, "mcp_list_changed_notifications", records)
    return records


async def _emit_or_enqueue(context: Any, payload: dict[str, Any]) -> None:
    if _has_runtime_event_sink(context):
        context.emit_runtime_event("mcp_list_changed", name="mcp", payload=payload)
        return
    enqueue = getattr(context, "async_message_enqueue", None)
    if enqueue is None:
        return
    result = enqueue(_list_changed_async_message(payload))
    if inspect.isawaitable(result):
        await result


def _has_runtime_event_sink(context: Any) -> bool:
    active = getattr(context, "has_runtime_event_sink", None)
    if active is None:
        return False
    return bool(active())


def _list_changed_async_message(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "user",
        "message": {
            "role": "user",
            "content": [{"type": "text", "text": _list_changed_text(payload)}],
        },
        "priority": "later",
        "isReplay": False,
        "isSynthetic": True,
    }


def _list_changed_text(payload: dict[str, Any]) -> str:
    lines = [
        "<mcp_list_changed>",
        "<server>%s</server>" % html.escape(str(payload.get("mcp_server_name") or "")),
        "<kind>%s</kind>" % html.escape(str(payload.get("kind") or "")),
        "<refreshed>%s</refreshed>" % str(bool(payload.get("refreshed"))).lower(),
    ]
    for tool in payload.get("loaded_tools") or []:
        lines.append("<loaded_tool>%s</loaded_tool>" % html.escape(str(tool or "")))
    for prompt in payload.get("loaded_prompts") or []:
        lines.append("<loaded_prompt>%s</loaded_prompt>" % html.escape(str(prompt or "")))
    for resource in payload.get("loaded_resources") or []:
        lines.append("<loaded_resource>%s</loaded_resource>" % html.escape(str(resource or "")))
    error = str(payload.get("error") or "")
    if error:
        lines.append("<error>%s</error>" % html.escape(error))
    lines.append("</mcp_list_changed>")
    return "\n".join(lines)
