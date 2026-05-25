from __future__ import annotations

import json
from dataclasses import replace
from types import SimpleNamespace
from typing import Any

from agents.kernel.capabilities.tools.context import ToolRuntimeContext
from agents.kernel.capabilities.tools.registry import ToolRegistry
from agents.kernel.mcp_auth import mcp_authorization_headers_for_scope
from agents.kernel.mcp_config import server_record_for_scope
from agents.kernel.mcp_oauth_runtime import authenticate_mcp_oauth_server


IDE_AUTH_HEADER = "X-Claude-Code-Ide-Authorization"
SUPPORTED_TRANSPORTS = ("stdio", "sse", "sse-ide", "http", "ws", "ws-ide", "sdk", "claudeai-proxy")

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
        "headers": {"type": "object", "additionalProperties": {"type": "string"}, "description": "Optional headers for HTTP/SSE/WebSocket MCP transports."},
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
    await _hydrate_mcp_config(context)
    settings = _mcp_settings(context)
    providers = list(getattr(context, "mcp_providers", []) or [])
    configured_command = str(getattr(settings, "SERVER_COMMAND", "") or "").strip()
    configured_name = str(getattr(settings, "SERVER_NAME", "") or "").strip()
    records = await _mcp_records(context)
    return {
        "configured": {
            "name": configured_name,
            "command": configured_command,
            "transport": str(getattr(settings, "SERVER_TRANSPORT", "") or "stdio"),
            "url": str(getattr(settings, "SERVER_URL", "") or ""),
            "headers": _headers(settings),
            "execution_mode": str(getattr(settings, "EXECUTION_MODE", "") or ""),
            "sandbox_profile": str(getattr(settings, "SANDBOX_PROFILE", "") or ""),
            "auth_required": bool(getattr(settings, "AUTH_REQUIRED", False)),
            "auth_url": str(getattr(settings, "AUTH_URL", "") or ""),
            "auth_status": str(getattr(settings, "AUTH_STATUS", "") or ""),
            "auth_message": str(getattr(settings, "AUTH_MESSAGE", "") or ""),
            "enabled": bool(configured_command or str(getattr(settings, "SERVER_URL", "") or "").strip()),
        },
        "servers": [record.to_dict() for record in records],
        "providers": [_provider_payload(provider) for provider in providers],
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
    command_text = str(command or "").strip()
    settings = _mcp_settings(context)
    transport_value = _transport(transport or getattr(settings, "SERVER_TRANSPORT", "") or "stdio")
    url_text = str(url or "").strip()
    if transport_value == "stdio" and not command_text:
        raise ValueError("command is required for stdio MCP servers")
    if transport_value != "stdio" and not url_text:
        raise ValueError("url is required for %s MCP servers" % transport_value)
    settings.SERVER_NAME = str(name or "default").strip() or "default"
    settings.SERVER_COMMAND = command_text
    settings.SERVER_TRANSPORT = transport_value
    settings.SERVER_URL = url_text
    settings.SERVER_HEADERS = _headers_with_ide_auth(
        _coerce_headers(headers),
        transport=transport_value,
        auth_token=auth_token,
    )
    settings.SERVER_HEADERS_JSON = json.dumps(settings.SERVER_HEADERS, ensure_ascii=False, sort_keys=True)
    settings.EXECUTION_MODE = str(execution_mode or getattr(settings, "EXECUTION_MODE", "") or "trusted_control_plane")
    if sandbox_profile:
        settings.SANDBOX_PROFILE = str(sandbox_profile)
    settings.AUTH_REQUIRED = bool(auth_required)
    settings.AUTH_URL = str(auth_url or "")
    settings.AUTH_STATUS = str(auth_status or "")
    settings.AUTH_MESSAGE = str(auth_message or "")
    await _save_mcp_config(context)
    return await mcp_servers(context)


async def mcp_clear(context: ToolRuntimeContext) -> dict[str, Any]:
    settings = _mcp_settings(context)
    removed_providers = list(getattr(context, "mcp_providers", []) or [])
    removed = len(removed_providers)
    previous_name = str(getattr(settings, "SERVER_NAME", "") or "default")
    settings.SERVER_NAME = ""
    settings.SERVER_COMMAND = ""
    settings.SERVER_URL = ""
    settings.SERVER_HEADERS = {}
    settings.SERVER_HEADERS_JSON = ""
    settings.AUTH_REQUIRED = False
    settings.AUTH_URL = ""
    settings.AUTH_STATUS = ""
    settings.AUTH_MESSAGE = ""
    await _close_mcp_providers(removed_providers)
    context.mcp_providers = []
    records = await _mcp_records(context)
    if records:
        for record in records:
            await _delete_mcp_config(context, record.name)
    else:
        await _delete_mcp_config(context, previous_name)
    return {"cleared": True, "removed_providers": removed, "configured": (await mcp_servers(context))["configured"]}


async def mcp_enable(context: ToolRuntimeContext, name: str = "") -> dict[str, Any]:
    target = str(name or "").strip() or str(getattr(_mcp_settings(context), "SERVER_NAME", "") or "default")
    record = await _find_mcp_record(context, target)
    if record is None:
        raise KeyError("mcp server not found: %s" % target)
    enabled = replace(record, enabled=True)
    await _save_mcp_record(context, enabled)
    settings = _mcp_settings(context)
    settings.SERVER_NAME = enabled.name
    settings.SERVER_COMMAND = enabled.command
    settings.SERVER_TRANSPORT = enabled.transport
    settings.SERVER_URL = enabled.url
    settings.SERVER_HEADERS = dict(enabled.headers)
    settings.SERVER_HEADERS_JSON = json.dumps(settings.SERVER_HEADERS, ensure_ascii=False, sort_keys=True) if settings.SERVER_HEADERS else ""
    settings.EXECUTION_MODE = enabled.execution_mode
    settings.SANDBOX_PROFILE = enabled.sandbox_profile
    settings.AUTH_REQUIRED = enabled.auth_required
    settings.AUTH_URL = enabled.auth_url
    settings.AUTH_STATUS = enabled.auth_status
    settings.AUTH_MESSAGE = enabled.auth_message
    return {"enabled": enabled.name, "configured": (await mcp_servers(context))["configured"]}


async def mcp_disable(context: ToolRuntimeContext, name: str = "") -> dict[str, Any]:
    settings = _mcp_settings(context)
    target = str(name or "").strip() or str(getattr(settings, "SERVER_NAME", "") or "default")
    record = await _find_mcp_record(context, target)
    if record is not None:
        await _save_mcp_record(context, replace(record, enabled=False))
    _removed, remaining = await _remove_mcp_providers(context, target)
    context.mcp_providers = remaining
    if not target or str(getattr(settings, "SERVER_NAME", "") or "default") == target:
        settings.SERVER_NAME = ""
        settings.SERVER_COMMAND = ""
        settings.SERVER_URL = ""
        settings.SERVER_HEADERS = {}
        settings.SERVER_HEADERS_JSON = ""
        settings.AUTH_REQUIRED = False
        settings.AUTH_URL = ""
        settings.AUTH_STATUS = ""
        settings.AUTH_MESSAGE = ""
    return {"disabled": target, "configured": (await mcp_servers(context))["configured"]}


async def mcp_remove(context: ToolRuntimeContext, name: str = "") -> dict[str, Any]:
    settings = _mcp_settings(context)
    target = str(name or "").strip() or str(getattr(settings, "SERVER_NAME", "") or "default")
    await _delete_mcp_config(context, target)
    _removed, remaining = await _remove_mcp_providers(context, target)
    context.mcp_providers = remaining
    if str(getattr(settings, "SERVER_NAME", "") or "default") == target:
        settings.SERVER_NAME = ""
        settings.SERVER_COMMAND = ""
        settings.SERVER_URL = ""
        settings.SERVER_HEADERS = {}
        settings.SERVER_HEADERS_JSON = ""
        settings.AUTH_REQUIRED = False
        settings.AUTH_URL = ""
        settings.AUTH_STATUS = ""
        settings.AUTH_MESSAGE = ""
    return {"removed": target, "configured": (await mcp_servers(context))["configured"]}


async def mcp_reload(context: ToolRuntimeContext, registry: Any) -> dict[str, Any]:
    from agents.kernel.capabilities.mcp_loading import load_configured_mcp

    previous_providers = list(getattr(context, "mcp_providers", []) or [])
    previous_names = [_provider_name(provider) for provider in previous_providers]
    records = await _mcp_records(context)
    staging_registry = ToolRegistry()
    load_kwargs = await _mcp_load_kwargs(context, records, registry=registry)
    providers = await load_configured_mcp(_settings(context), staging_registry, **load_kwargs)
    definitions = _loaded_mcp_definitions(staging_registry)

    try:
        await _close_mcp_providers(previous_providers)
    except Exception:
        await _close_mcp_providers(providers)
        raise

    removed_tools = _unregister_loaded_mcp_tools(registry)
    for definition in definitions:
        registry.register_definition(definition)

    context.mcp_providers = providers
    loaded_tools = _loaded_mcp_tool_names(registry, providers)
    removed_set = set(removed_tools)
    context.enabled_tools = _merge_unique(
        [tool for tool in list(getattr(context, "enabled_tools", []) or []) if tool not in removed_set],
        loaded_tools,
    )
    return {
        "reloaded": True,
        "closed_providers": previous_names,
        "removed_tools": removed_tools,
        "providers": [_provider_payload(provider) for provider in providers],
        "loaded_tools": loaded_tools,
        "configured": (await mcp_servers(context))["configured"],
    }


async def mcp_reconnect(context: ToolRuntimeContext, registry: Any, name: str = "") -> dict[str, Any]:
    from agents.kernel.capabilities.mcp_loading import load_configured_mcp

    target = str(name or "").strip() or str(getattr(_mcp_settings(context), "SERVER_NAME", "") or "default")
    records = await _mcp_records(context)
    target_records = _target_mcp_records(records, target)
    if records and not target_records:
        known = {str(getattr(record, "name", "") or "") for record in records}
        if target in known:
            raise RuntimeError("mcp server is disabled: %s" % target)
        raise KeyError("mcp server not found: %s" % target)
    if not records and not _settings_mcp_server_matches(context, target):
        raise KeyError("mcp server not found: %s" % target)

    previous_providers = list(getattr(context, "mcp_providers", []) or [])
    previous_target_providers = [provider for provider in previous_providers if _provider_name(provider) == target]
    staging_registry = ToolRegistry()
    load_kwargs = await _mcp_load_kwargs(context, target_records, registry=registry)
    providers = await load_configured_mcp(_settings(context), staging_registry, **load_kwargs)
    definitions = _loaded_mcp_definitions_for_server(staging_registry, target)

    try:
        await _close_mcp_providers(previous_target_providers)
    except Exception:
        await _close_mcp_providers(providers)
        raise

    removed_tools = _unregister_loaded_mcp_tools_for_server(registry, target)
    for definition in definitions:
        registry.register_definition(definition)

    context.mcp_providers = _replace_mcp_providers(previous_providers, target, providers)
    loaded_tools = _loaded_mcp_tool_names(registry, providers)
    removed_set = set(removed_tools)
    context.enabled_tools = _merge_unique(
        [tool for tool in list(getattr(context, "enabled_tools", []) or []) if tool not in removed_set],
        loaded_tools,
    )
    return {
        "reconnected": True,
        "server": target,
        "serverName": target,
        "closed_providers": [_provider_name(provider) for provider in previous_target_providers],
        "removed_tools": removed_tools,
        "providers": [_provider_payload(provider) for provider in providers],
        "loaded_tools": loaded_tools,
        "configured": (await mcp_servers(context))["configured"],
    }


def _mcp_settings(context: ToolRuntimeContext) -> Any:
    settings = getattr(context, "settings", None)
    if settings is None:
        settings = SimpleNamespace()
        context.settings = settings
    mcp = getattr(settings, "mcp", None)
    if mcp is None:
        mcp = SimpleNamespace(
            SERVER_NAME="",
            SERVER_COMMAND="",
            SERVER_TRANSPORT="stdio",
            SERVER_URL="",
            SERVER_HEADERS={},
            SERVER_HEADERS_JSON="",
            EXECUTION_MODE="",
            SANDBOX_PROFILE="",
            AUTH_REQUIRED=False,
            AUTH_URL="",
            AUTH_STATUS="",
            AUTH_MESSAGE="",
        )
        settings.mcp = mcp
    for name, value in {
        "SERVER_NAME": "",
        "SERVER_COMMAND": "",
        "SERVER_TRANSPORT": "stdio",
        "SERVER_URL": "",
        "SERVER_HEADERS": {},
        "SERVER_HEADERS_JSON": "",
        "EXECUTION_MODE": "",
        "SANDBOX_PROFILE": "",
        "AUTH_REQUIRED": False,
        "AUTH_URL": "",
        "AUTH_STATUS": "",
        "AUTH_MESSAGE": "",
    }.items():
        if not hasattr(mcp, name):
            setattr(mcp, name, value)
    return mcp


def _settings(context: ToolRuntimeContext) -> Any:
    _mcp_settings(context)
    return context.settings


def _provider_payload(provider: Any) -> dict[str, str]:
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


def _provider_name(provider: Any) -> str:
    return str(getattr(getattr(provider, "server", None), "name", "") or "")


def _loaded_mcp_tool_names(registry: Any, providers: list[Any]) -> list[str]:
    provider_names = {str(_provider_name(provider)) for provider in providers}
    names: list[str] = []
    for name in getattr(registry, "names", lambda: [])():
        spec = _registry_spec(registry, name)
        metadata = _spec_metadata(spec)
        info = metadata.get("mcp_info") if isinstance(metadata, dict) else None
        if not isinstance(info, dict):
            continue
        if info.get("server") not in provider_names:
            continue
        if name.startswith("mcp__"):
            names.append(name)
    return sorted(names)


def _unregister_loaded_mcp_tools(registry: Any) -> list[str]:
    unregister_matching = getattr(registry, "unregister_matching", None)
    if unregister_matching is None:
        return []
    return unregister_matching(lambda definition: isinstance(definition.metadata.get("mcp_info"), dict))


def _loaded_mcp_definitions(registry: Any) -> list[Any]:
    definitions_matching = getattr(registry, "definitions_matching", None)
    if definitions_matching is None:
        return []
    return definitions_matching(lambda definition: isinstance(definition.metadata.get("mcp_info"), dict))


async def _mcp_load_kwargs(context: ToolRuntimeContext, records: list[Any], registry: Any | None = None) -> dict[str, Any]:
    load_kwargs: dict[str, Any] = {
        "roots": [str(context.workspace.path)],
        "records": records if records else None,
    }
    sdk_mcp_handlers = getattr(context, "sdk_mcp_handlers", None)
    if sdk_mcp_handlers:
        load_kwargs["sdk_mcp_handlers"] = sdk_mcp_handlers
    mcp_elicitation_handler = getattr(context, "mcp_elicitation_handler", None)
    if mcp_elicitation_handler is not None:
        from agents.kernel.mcp_elicitation_runtime import build_mcp_elicitation_complete_handler

        load_kwargs["elicitation_handler"] = mcp_elicitation_handler
        load_kwargs["elicitation_complete_handler"] = build_mcp_elicitation_complete_handler(context)
    if registry is not None:
        from agents.kernel.mcp_list_changed_runtime import build_mcp_list_changed_handler

        load_kwargs["list_changed_handler"] = build_mcp_list_changed_handler(context, registry)
    auth_headers = await _mcp_auth_headers(context, records)
    if auth_headers:
        load_kwargs["auth_headers"] = auth_headers
    load_kwargs["oauth_authenticator"] = lambda server, arguments: authenticate_mcp_oauth_server(
        context,
        server,
        arguments,
    )
    return load_kwargs


def _loaded_mcp_definitions_for_server(registry: Any, server_name: str) -> list[Any]:
    definitions_matching = getattr(registry, "definitions_matching", None)
    if definitions_matching is None:
        return []
    return definitions_matching(lambda definition: _definition_mcp_server(definition) == server_name)


def _unregister_loaded_mcp_tools_for_server(registry: Any, server_name: str) -> list[str]:
    unregister_matching = getattr(registry, "unregister_matching", None)
    if unregister_matching is None:
        return []
    return unregister_matching(lambda definition: _definition_mcp_server(definition) == server_name)


def _definition_mcp_server(definition: Any) -> str:
    info = definition.metadata.get("mcp_info") if isinstance(getattr(definition, "metadata", None), dict) else None
    if not isinstance(info, dict):
        return ""
    return str(info.get("server") or "")


def _target_mcp_records(records: list[Any], target: str) -> list[Any]:
    return [
        record
        for record in records
        if str(getattr(record, "name", "") or "") == target and bool(getattr(record, "enabled", True))
    ]


def _settings_mcp_server_matches(context: ToolRuntimeContext, target: str) -> bool:
    settings = _mcp_settings(context)
    name = str(getattr(settings, "SERVER_NAME", "") or "default")
    command = str(getattr(settings, "SERVER_COMMAND", "") or "").strip()
    transport = str(getattr(settings, "SERVER_TRANSPORT", "stdio") or "stdio")
    url = str(getattr(settings, "SERVER_URL", "") or "").strip()
    if name != target:
        return False
    return (transport == "stdio" and bool(command)) or (transport != "stdio" and bool(url))


def _replace_mcp_providers(previous: list[Any], target: str, replacements: list[Any]) -> list[Any]:
    replaced = False
    result: list[Any] = []
    for provider in previous:
        if _provider_name(provider) != target:
            result.append(provider)
            continue
        if not replaced:
            result.extend(replacements)
            replaced = True
    if not replaced:
        result.extend(replacements)
    return result


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


def _merge_unique(*groups: list[str]) -> list[str]:
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


def _transport(value: str) -> str:
    transport = str(value or "stdio").strip() or "stdio"
    if transport not in SUPPORTED_TRANSPORTS:
        raise ValueError("unsupported MCP transport: %s" % transport)
    return transport


def _headers(settings: Any) -> dict[str, str]:
    raw = getattr(settings, "SERVER_HEADERS", None)
    if isinstance(raw, dict):
        return _coerce_headers(raw)
    raw_json = str(getattr(settings, "SERVER_HEADERS_JSON", "") or "").strip()
    if not raw_json:
        return {}
    try:
        parsed = json.loads(raw_json)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return _coerce_headers(parsed)


def _coerce_headers(headers: dict[str, Any] | None) -> dict[str, str]:
    if not isinstance(headers, dict):
        return {}
    return {str(key): str(value) for key, value in headers.items()}


def _headers_with_ide_auth(headers: dict[str, str], *, transport: str, auth_token: str) -> dict[str, str]:
    if transport != "ws-ide":
        return headers
    token = str(auth_token or "").strip()
    if not token or _has_header(headers, IDE_AUTH_HEADER):
        return headers
    return {**headers, IDE_AUTH_HEADER: token}


def _has_header(headers: dict[str, str], name: str) -> bool:
    wanted = name.lower()
    return any(str(key).lower() == wanted for key in headers)


async def _save_mcp_config(context: ToolRuntimeContext) -> None:
    store = getattr(context, "mcp_config_store", None)
    if store is None:
        return
    settings = _mcp_settings(context)
    await _save_mcp_record(
        context,
        server_record_for_scope(
            name=str(getattr(settings, "SERVER_NAME", "") or "default"),
            command=str(getattr(settings, "SERVER_COMMAND", "") or ""),
            transport=str(getattr(settings, "SERVER_TRANSPORT", "") or "stdio"),
            url=str(getattr(settings, "SERVER_URL", "") or ""),
            headers=_headers(settings),
            execution_mode=str(getattr(settings, "EXECUTION_MODE", "") or "trusted_control_plane"),
            sandbox_profile=str(getattr(settings, "SANDBOX_PROFILE", "") or ""),
            auth_required=bool(getattr(settings, "AUTH_REQUIRED", False)),
            auth_url=str(getattr(settings, "AUTH_URL", "") or ""),
            auth_status=str(getattr(settings, "AUTH_STATUS", "") or ""),
            auth_message=str(getattr(settings, "AUTH_MESSAGE", "") or ""),
            workspace=context.workspace,
            enabled=True,
        ),
    )


async def _save_mcp_record(context: ToolRuntimeContext, record: Any) -> None:
    store = getattr(context, "mcp_config_store", None)
    if store is None:
        return
    await store.save(record)


async def _hydrate_mcp_config(context: ToolRuntimeContext) -> None:
    store = getattr(context, "mcp_config_store", None)
    if store is None:
        return
    workspace = context.workspace
    records = await store.list_for_scope(
        workspace.tenant_id,
        user_id=workspace.user_id,
        agent_id=workspace.agent_id,
        workspace_id=workspace.workspace_id,
    )
    active = next((record for record in records if record.enabled), None)
    if active is None:
        return
    settings = _mcp_settings(context)
    settings.SERVER_NAME = active.name
    settings.SERVER_COMMAND = active.command
    settings.SERVER_TRANSPORT = active.transport
    settings.SERVER_URL = active.url
    settings.SERVER_HEADERS = dict(active.headers)
    settings.SERVER_HEADERS_JSON = json.dumps(settings.SERVER_HEADERS, ensure_ascii=False, sort_keys=True) if settings.SERVER_HEADERS else ""
    settings.EXECUTION_MODE = active.execution_mode
    settings.SANDBOX_PROFILE = active.sandbox_profile
    settings.AUTH_REQUIRED = active.auth_required
    settings.AUTH_URL = active.auth_url
    settings.AUTH_STATUS = active.auth_status
    settings.AUTH_MESSAGE = active.auth_message


async def _mcp_records(context: ToolRuntimeContext) -> list[Any]:
    store = getattr(context, "mcp_config_store", None)
    if store is None:
        return []
    workspace = context.workspace
    return await store.list_for_scope(
        workspace.tenant_id,
        user_id=workspace.user_id,
        agent_id=workspace.agent_id,
        workspace_id=workspace.workspace_id,
    )


async def _mcp_auth_headers(context: ToolRuntimeContext, records: list[Any]) -> dict[str, str]:
    store = getattr(context, "mcp_auth_store", None)
    if store is None:
        return {}
    workspace = context.workspace
    names = [str(getattr(record, "name", "") or "") for record in records if bool(getattr(record, "enabled", True))]
    if not names:
        settings = _mcp_settings(context)
        command = str(getattr(settings, "SERVER_COMMAND", "") or "").strip()
        transport = str(getattr(settings, "SERVER_TRANSPORT", "stdio") or "stdio")
        url = str(getattr(settings, "SERVER_URL", "") or "").strip()
        if (transport == "stdio" and command) or (transport != "stdio" and url):
            names = [str(getattr(settings, "SERVER_NAME", "") or "default")]
    return await mcp_authorization_headers_for_scope(
        store,
        names=names,
        tenant_id=workspace.tenant_id,
        user_id=workspace.user_id,
        agent_id=workspace.agent_id,
        workspace_id=workspace.workspace_id,
    )


async def _find_mcp_record(context: ToolRuntimeContext, name: str) -> Any | None:
    target = str(name or "default").strip() or "default"
    return next((record for record in await _mcp_records(context) if record.name == target), None)


async def _remove_mcp_providers(context: ToolRuntimeContext, name: str) -> tuple[list[Any], list[Any]]:
    target = str(name or "").strip()
    providers = list(getattr(context, "mcp_providers", []) or [])
    removed = [provider for provider in providers if _provider_name(provider) == target]
    remaining = [provider for provider in providers if _provider_name(provider) != target]
    await _close_mcp_providers(removed)
    return removed, remaining


async def _close_mcp_providers(providers: list[Any]) -> None:
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


async def _delete_mcp_config(context: ToolRuntimeContext, name: str) -> None:
    store = getattr(context, "mcp_config_store", None)
    if store is None:
        return
    workspace = context.workspace
    await store.delete(
        name or "default",
        workspace.tenant_id,
        user_id=workspace.user_id,
        agent_id=workspace.agent_id,
        workspace_id=workspace.workspace_id,
    )
