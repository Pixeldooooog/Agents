from __future__ import annotations

from dataclasses import replace
from typing import Any

from agents.kernel.capabilities.tools.builtin.mcp.runtime import (
    close_providers,
    loaded_definitions,
    loaded_definitions_for_server,
    loaded_tool_names,
    load_kwargs,
    merge_unique,
    provider_name,
    provider_payload,
    remove_providers,
    replace_providers,
    settings_server_matches,
    target_records,
    unregister_loaded_tools,
    unregister_loaded_tools_for_server,
)
from agents.kernel.capabilities.tools.builtin.mcp.settings import (
    SUPPORTED_TRANSPORTS,
    apply_record_to_settings,
    clear_configured_server,
    coerce_headers,
    configured_server_payload,
    headers_with_ide_auth,
    mcp_settings,
    root_settings,
    set_headers,
    transport as normalize_transport,
)
from agents.kernel.capabilities.tools.builtin.mcp.store import (
    delete_config,
    find_record,
    hydrate_config,
    records,
    save_current_config,
    save_record,
)
from agents.kernel.capabilities.tools.context import ToolRuntimeContext
from agents.kernel.capabilities.tools.registry import ToolRegistry


MCP_SERVERS_SCHEMA = {
    "type": "object",
    "properties": {},
}

MCP_CONFIGURE_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "MCP server name."},
        "command": {"type": "string", "description": "Local MCP stdio server command line."},
        "transport": {"type": "string", "enum": list(SUPPORTED_TRANSPORTS), "description": "MCP transport type."},
        "url": {"type": "string", "description": "Remote MCP server URL for HTTP/SSE/WebSocket transports."},
        "headers": {
            "type": "object",
            "additionalProperties": {"type": "string"},
            "description": "Optional headers for HTTP/SSE/WebSocket MCP transports.",
        },
        "auth_token": {"type": "string", "description": "Optional IDE authorization token for ws-ide transports."},
        "authToken": {"type": "string", "description": "Camel-case alias for auth_token, matching src-origin IDE config."},
        "execution_mode": {"type": "string", "description": "MCP execution mode, defaults to trusted_control_plane."},
        "sandbox_profile": {"type": "string", "description": "Optional sandbox profile for future sandboxed MCP execution."},
        "auth_required": {"type": "boolean", "description": "Whether the server is installed but currently needs authentication."},
        "auth_url": {"type": "string", "description": "Authorization URL surfaced by an OAuth-capable transport."},
        "auth_status": {"type": "string", "description": "Optional authentication status label."},
        "auth_message": {"type": "string", "description": "Optional authentication status or error message."},
    },
}

MCP_CLEAR_SCHEMA = {
    "type": "object",
    "properties": {},
}

MCP_RELOAD_SCHEMA = {
    "type": "object",
    "properties": {},
}

MCP_SERVER_NAME_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "MCP server name. Defaults to current server."},
    },
}


async def mcp_servers(context: ToolRuntimeContext) -> dict[str, Any]:
    await hydrate_config(context)
    providers = list(getattr(context, "mcp_providers", []) or [])
    return {
        "configured": configured_server_payload(mcp_settings(context)),
        "servers": [record.to_dict() for record in await records(context)],
        "providers": [provider_payload(provider) for provider in providers],
        "count": len(providers),
    }


async def mcp_configure(
    context: ToolRuntimeContext,
    command: str = "",
    name: str = "default",
    transport: str = "",
    url: str = "",
    headers: dict[str, Any] | None = None,
    auth_token: str = "",
    execution_mode: str = "",
    sandbox_profile: str = "",
    auth_required: bool = False,
    auth_url: str = "",
    auth_status: str = "",
    auth_message: str = "",
) -> dict[str, Any]:
    settings = mcp_settings(context)
    command_text = str(command or "").strip()
    transport_value = transport or getattr(settings, "SERVER_TRANSPORT", "") or "stdio"
    transport_value = normalize_transport(transport_value)
    url_text = str(url or "").strip()
    if transport_value == "stdio" and not command_text:
        raise ValueError("command is required for stdio MCP servers")
    if transport_value != "stdio" and not url_text:
        raise ValueError("url is required for %s MCP servers" % transport_value)

    settings.SERVER_NAME = str(name or "default").strip() or "default"
    settings.SERVER_COMMAND = command_text
    settings.SERVER_TRANSPORT = transport_value
    settings.SERVER_URL = url_text
    set_headers(
        settings,
        headers_with_ide_auth(
            coerce_headers(headers),
            transport_value=transport_value,
            auth_token=auth_token,
        ),
    )
    settings.EXECUTION_MODE = str(execution_mode or getattr(settings, "EXECUTION_MODE", "") or "trusted_control_plane")
    if sandbox_profile:
        settings.SANDBOX_PROFILE = str(sandbox_profile)
    settings.AUTH_REQUIRED = bool(auth_required)
    settings.AUTH_URL = str(auth_url or "")
    settings.AUTH_STATUS = str(auth_status or "")
    settings.AUTH_MESSAGE = str(auth_message or "")
    await save_current_config(context)
    return await mcp_servers(context)


async def mcp_clear(context: ToolRuntimeContext) -> dict[str, Any]:
    settings = mcp_settings(context)
    removed_providers = list(getattr(context, "mcp_providers", []) or [])
    removed = len(removed_providers)
    previous_name = str(getattr(settings, "SERVER_NAME", "") or "default")
    clear_configured_server(settings)
    await close_providers(removed_providers)
    context.mcp_providers = []
    config_records = await records(context)
    if config_records:
        for record in config_records:
            await delete_config(context, record.name)
    else:
        await delete_config(context, previous_name)
    return {"cleared": True, "removed_providers": removed, "configured": (await mcp_servers(context))["configured"]}


async def mcp_enable(context: ToolRuntimeContext, name: str = "") -> dict[str, Any]:
    target = str(name or "").strip() or str(getattr(mcp_settings(context), "SERVER_NAME", "") or "default")
    record = await find_record(context, target)
    if record is None:
        raise KeyError("mcp server not found: %s" % target)
    enabled = replace(record, enabled=True)
    await save_record(context, enabled)
    apply_record_to_settings(mcp_settings(context), enabled)
    return {"enabled": enabled.name, "configured": (await mcp_servers(context))["configured"]}


async def mcp_disable(context: ToolRuntimeContext, name: str = "") -> dict[str, Any]:
    settings = mcp_settings(context)
    target = str(name or "").strip() or str(getattr(settings, "SERVER_NAME", "") or "default")
    record = await find_record(context, target)
    if record is not None:
        await save_record(context, replace(record, enabled=False))
    _removed, remaining = await remove_providers(context, target)
    context.mcp_providers = remaining
    if not target or str(getattr(settings, "SERVER_NAME", "") or "default") == target:
        clear_configured_server(settings)
    return {"disabled": target, "configured": (await mcp_servers(context))["configured"]}


async def mcp_remove(context: ToolRuntimeContext, name: str = "") -> dict[str, Any]:
    settings = mcp_settings(context)
    target = str(name or "").strip() or str(getattr(settings, "SERVER_NAME", "") or "default")
    await delete_config(context, target)
    _removed, remaining = await remove_providers(context, target)
    context.mcp_providers = remaining
    if str(getattr(settings, "SERVER_NAME", "") or "default") == target:
        clear_configured_server(settings)
    return {"removed": target, "configured": (await mcp_servers(context))["configured"]}


async def mcp_reload(context: ToolRuntimeContext, registry: Any) -> dict[str, Any]:
    from agents.kernel.mcp.loading import load_configured_mcp

    previous_providers = list(getattr(context, "mcp_providers", []) or [])
    previous_names = [provider_name(provider) for provider in previous_providers]
    config_records = await records(context)
    staging_registry = ToolRegistry()
    providers = await load_configured_mcp(
        root_settings(context),
        staging_registry,
        **(await load_kwargs(context, config_records, registry=registry)),
    )
    definitions = loaded_definitions(staging_registry)

    try:
        await close_providers(previous_providers)
    except Exception:
        await close_providers(providers)
        raise

    removed_tools = unregister_loaded_tools(registry)
    for definition in definitions:
        registry.register_definition(definition)

    context.mcp_providers = providers
    loaded_tools = loaded_tool_names(registry, providers)
    removed_set = set(removed_tools)
    context.enabled_tools = merge_unique(
        [tool for tool in list(getattr(context, "enabled_tools", []) or []) if tool not in removed_set],
        loaded_tools,
    )
    return {
        "reloaded": True,
        "closed_providers": previous_names,
        "removed_tools": removed_tools,
        "providers": [provider_payload(provider) for provider in providers],
        "loaded_tools": loaded_tools,
        "configured": (await mcp_servers(context))["configured"],
    }


async def mcp_reconnect(context: ToolRuntimeContext, registry: Any, name: str = "") -> dict[str, Any]:
    from agents.kernel.mcp.loading import load_configured_mcp

    target = str(name or "").strip() or str(getattr(mcp_settings(context), "SERVER_NAME", "") or "default")
    config_records = await records(context)
    target_config_records = target_records(config_records, target)
    if config_records and not target_config_records:
        known = {str(getattr(record, "name", "") or "") for record in config_records}
        if target in known:
            raise RuntimeError("mcp server is disabled: %s" % target)
        raise KeyError("mcp server not found: %s" % target)
    if not config_records and not settings_server_matches(context, target):
        raise KeyError("mcp server not found: %s" % target)

    previous_providers = list(getattr(context, "mcp_providers", []) or [])
    previous_target_providers = [provider for provider in previous_providers if provider_name(provider) == target]
    staging_registry = ToolRegistry()
    providers = await load_configured_mcp(
        root_settings(context),
        staging_registry,
        **(await load_kwargs(context, target_config_records, registry=registry)),
    )
    definitions = loaded_definitions_for_server(staging_registry, target)

    try:
        await close_providers(previous_target_providers)
    except Exception:
        await close_providers(providers)
        raise

    removed_tools = unregister_loaded_tools_for_server(registry, target)
    for definition in definitions:
        registry.register_definition(definition)

    context.mcp_providers = replace_providers(previous_providers, target, providers)
    loaded_tools = loaded_tool_names(registry, providers)
    removed_set = set(removed_tools)
    context.enabled_tools = merge_unique(
        [tool for tool in list(getattr(context, "enabled_tools", []) or []) if tool not in removed_set],
        loaded_tools,
    )
    return {
        "reconnected": True,
        "server": target,
        "serverName": target,
        "closed_providers": [provider_name(provider) for provider in previous_target_providers],
        "removed_tools": removed_tools,
        "providers": [provider_payload(provider) for provider in providers],
        "loaded_tools": loaded_tools,
        "configured": (await mcp_servers(context))["configured"],
    }
