from __future__ import annotations

from typing import Any

from agents.kernel.capabilities.tools.builtin.mcp.settings import mcp_settings
from agents.kernel.capabilities.tools.builtin.mcp.store import auth_headers
from agents.kernel.capabilities.tools.context import ToolRuntimeContext
from agents.kernel.mcp.oauth_runtime import authenticate_mcp_oauth_server


def provider_payload(provider: Any) -> dict[str, str]:
    server = getattr(provider, "server", None)
    return {
        "name": str(getattr(server, "name", "") or ""),
        "transport": str(getattr(server, "transport", "") or "stdio"),
        "url": str(getattr(server, "url", "") or ""),
        "headers": str(len(getattr(server, "headers", {}) or {})),
        "execution_mode": str(getattr(server, "execution_mode", "") or ""),
        "auth_required": str(bool(getattr(server, "auth_required", False))).lower(),
        "tools": str(len(getattr(provider, "tools", []) or [])),
    }


def provider_name(provider: Any) -> str:
    return str(getattr(getattr(provider, "server", None), "name", "") or "")


def loaded_tool_names(registry: Any, providers: list[Any]) -> list[str]:
    provider_names = {str(provider_name(provider)) for provider in providers}
    names: list[str] = []
    for name in getattr(registry, "names", lambda: [])():
        spec = _registry_spec(registry, name)
        info = _spec_metadata(spec).get("mcp_info")
        if isinstance(info, dict) and info.get("server") in provider_names and name.startswith("mcp__"):
            names.append(name)
    return sorted(names)


def unregister_loaded_tools(registry: Any) -> list[str]:
    unregister_matching = getattr(registry, "unregister_matching", None)
    if unregister_matching is None:
        return []
    return unregister_matching(lambda definition: isinstance(definition.metadata.get("mcp_info"), dict))


def loaded_definitions(registry: Any) -> list[Any]:
    definitions_matching = getattr(registry, "definitions_matching", None)
    if definitions_matching is None:
        return []
    return definitions_matching(lambda definition: isinstance(definition.metadata.get("mcp_info"), dict))


async def load_kwargs(context: ToolRuntimeContext, records: list[Any], registry: Any | None = None) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "roots": [str(context.workspace.path)],
        "records": records if records else None,
    }
    sdk_mcp_handlers = getattr(context, "sdk_mcp_handlers", None)
    if sdk_mcp_handlers:
        kwargs["sdk_mcp_handlers"] = sdk_mcp_handlers
    mcp_elicitation_handler = getattr(context, "mcp_elicitation_handler", None)
    if mcp_elicitation_handler is not None:
        from agents.kernel.mcp.elicitation_runtime import build_mcp_elicitation_complete_handler

        kwargs["elicitation_handler"] = mcp_elicitation_handler
        kwargs["elicitation_complete_handler"] = build_mcp_elicitation_complete_handler(context)
    if registry is not None:
        from agents.kernel.mcp.list_changed_runtime import build_mcp_list_changed_handler

        kwargs["list_changed_handler"] = build_mcp_list_changed_handler(context, registry)
    scoped_headers = await auth_headers(context, records)
    if scoped_headers:
        kwargs["auth_headers"] = scoped_headers
    kwargs["oauth_authenticator"] = lambda server, arguments: authenticate_mcp_oauth_server(
        context,
        server,
        arguments,
    )
    return kwargs


def loaded_definitions_for_server(registry: Any, server_name: str) -> list[Any]:
    definitions_matching = getattr(registry, "definitions_matching", None)
    if definitions_matching is None:
        return []
    return definitions_matching(lambda definition: definition_server(definition) == server_name)


def unregister_loaded_tools_for_server(registry: Any, server_name: str) -> list[str]:
    unregister_matching = getattr(registry, "unregister_matching", None)
    if unregister_matching is None:
        return []
    return unregister_matching(lambda definition: definition_server(definition) == server_name)


def definition_server(definition: Any) -> str:
    info = definition.metadata.get("mcp_info") if isinstance(getattr(definition, "metadata", None), dict) else None
    if not isinstance(info, dict):
        return ""
    return str(info.get("server") or "")


def target_records(records: list[Any], target: str) -> list[Any]:
    return [
        record
        for record in records
        if str(getattr(record, "name", "") or "") == target and bool(getattr(record, "enabled", True))
    ]


def settings_server_matches(context: ToolRuntimeContext, target: str) -> bool:
    settings = mcp_settings(context)
    name = str(getattr(settings, "SERVER_NAME", "") or "default")
    command = str(getattr(settings, "SERVER_COMMAND", "") or "").strip()
    selected_transport = str(getattr(settings, "SERVER_TRANSPORT", "stdio") or "stdio")
    url = str(getattr(settings, "SERVER_URL", "") or "").strip()
    if name != target:
        return False
    return (selected_transport == "stdio" and bool(command)) or (selected_transport != "stdio" and bool(url))


def replace_providers(previous: list[Any], target: str, replacements: list[Any]) -> list[Any]:
    replaced = False
    result: list[Any] = []
    for provider in previous:
        if provider_name(provider) != target:
            result.append(provider)
            continue
        if not replaced:
            result.extend(replacements)
            replaced = True
    if not replaced:
        result.extend(replacements)
    return result


async def remove_providers(context: ToolRuntimeContext, name: str) -> tuple[list[Any], list[Any]]:
    target = str(name or "").strip()
    providers = list(getattr(context, "mcp_providers", []) or [])
    removed = [provider for provider in providers if provider_name(provider) == target]
    remaining = [provider for provider in providers if provider_name(provider) != target]
    await close_providers(removed)
    return removed, remaining


async def close_providers(providers: list[Any]) -> None:
    first_error: Exception | None = None
    for provider in providers:
        close = getattr(provider, "close", None)
        if close is None:
            continue
        try:
            await close()
        except Exception as exc:
            if first_error is None:
                first_error = exc
    if first_error is not None:
        raise first_error


def merge_unique(*groups: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for item in group:
            value = str(item or "")
            if not value or value in seen:
                continue
            seen.add(value)
            merged.append(value)
    return merged


def _registry_spec(registry: Any, name: str) -> Any | None:
    try:
        specs = registry.specs([name])
    except Exception:
        return None
    return specs[0] if specs else None


def _spec_metadata(spec: Any | None) -> dict[str, Any]:
    raw = getattr(spec, "raw", None)
    if not isinstance(raw, dict):
        return {}
    metadata = raw.get("metadata")
    return dict(metadata) if isinstance(metadata, dict) else {}
