from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from typing import Any

from agents.kernel.capabilities.tools.context import ToolRuntimeContext
from agents.kernel.mcp_config import server_record_for_scope


MCP_SERVERS_SCHEMA = {
    "type": "object",
    "properties": {},
}

MCP_CONFIGURE_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "MCP server name."},
        "command": {"type": "string", "description": "Local MCP server command line."},
        "execution_mode": {"type": "string", "description": "MCP execution mode, defaults to trusted_control_plane."},
        "sandbox_profile": {"type": "string", "description": "Optional sandbox profile for future sandboxed MCP execution."},
    },
    "required": ["command"],
}

MCP_CLEAR_SCHEMA = {
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
            "execution_mode": str(getattr(settings, "EXECUTION_MODE", "") or ""),
            "sandbox_profile": str(getattr(settings, "SANDBOX_PROFILE", "") or ""),
            "enabled": bool(configured_command),
        },
        "servers": [record.to_dict() for record in records],
        "providers": [_provider_payload(provider) for provider in providers],
        "count": len(providers),
    }


async def mcp_configure(
    context: ToolRuntimeContext,
    command: str,
    name: str = "default",
    execution_mode: str = "",
    sandbox_profile: str = "",
) -> dict[str, Any]:
    command_text = str(command or "").strip()
    if not command_text:
        raise ValueError("command is required")
    settings = _mcp_settings(context)
    settings.SERVER_NAME = str(name or "default").strip() or "default"
    settings.SERVER_COMMAND = command_text
    settings.EXECUTION_MODE = str(execution_mode or getattr(settings, "EXECUTION_MODE", "") or "trusted_control_plane")
    if sandbox_profile:
        settings.SANDBOX_PROFILE = str(sandbox_profile)
    await _save_mcp_config(context)
    await _disable_other_mcp_configs(context, settings.SERVER_NAME)
    return await mcp_servers(context)


async def mcp_clear(context: ToolRuntimeContext) -> dict[str, Any]:
    settings = _mcp_settings(context)
    removed = len(list(getattr(context, "mcp_providers", []) or []))
    previous_name = str(getattr(settings, "SERVER_NAME", "") or "default")
    settings.SERVER_NAME = ""
    settings.SERVER_COMMAND = ""
    context.mcp_providers = []
    await _delete_mcp_config(context, previous_name)
    return {"cleared": True, "removed_providers": removed, "configured": (await mcp_servers(context))["configured"]}


async def mcp_enable(context: ToolRuntimeContext, name: str = "") -> dict[str, Any]:
    target = str(name or "").strip() or str(getattr(_mcp_settings(context), "SERVER_NAME", "") or "default")
    record = await _find_mcp_record(context, target)
    if record is None:
        raise KeyError("mcp server not found: %s" % target)
    enabled = replace(record, enabled=True)
    await _save_mcp_record(context, enabled)
    await _disable_other_mcp_configs(context, enabled.name)
    settings = _mcp_settings(context)
    settings.SERVER_NAME = enabled.name
    settings.SERVER_COMMAND = enabled.command
    settings.EXECUTION_MODE = enabled.execution_mode
    settings.SANDBOX_PROFILE = enabled.sandbox_profile
    return {"enabled": enabled.name, "configured": (await mcp_servers(context))["configured"]}


async def mcp_disable(context: ToolRuntimeContext, name: str = "") -> dict[str, Any]:
    settings = _mcp_settings(context)
    target = str(name or "").strip() or str(getattr(settings, "SERVER_NAME", "") or "default")
    record = await _find_mcp_record(context, target)
    if record is not None:
        await _save_mcp_record(context, replace(record, enabled=False))
    if not target or str(getattr(settings, "SERVER_NAME", "") or "default") == target:
        settings.SERVER_NAME = ""
        settings.SERVER_COMMAND = ""
        context.mcp_providers = [
            provider for provider in list(getattr(context, "mcp_providers", []) or []) if _provider_name(provider) != target
        ]
    return {"disabled": target, "configured": (await mcp_servers(context))["configured"]}


async def mcp_remove(context: ToolRuntimeContext, name: str = "") -> dict[str, Any]:
    settings = _mcp_settings(context)
    target = str(name or "").strip() or str(getattr(settings, "SERVER_NAME", "") or "default")
    await _delete_mcp_config(context, target)
    if str(getattr(settings, "SERVER_NAME", "") or "default") == target:
        settings.SERVER_NAME = ""
        settings.SERVER_COMMAND = ""
        context.mcp_providers = [
            provider for provider in list(getattr(context, "mcp_providers", []) or []) if _provider_name(provider) != target
        ]
    return {"removed": target, "configured": (await mcp_servers(context))["configured"]}


def _mcp_settings(context: ToolRuntimeContext) -> Any:
    settings = getattr(context, "settings", None)
    if settings is None:
        settings = SimpleNamespace()
        context.settings = settings
    mcp = getattr(settings, "mcp", None)
    if mcp is None:
        mcp = SimpleNamespace(SERVER_NAME="", SERVER_COMMAND="", EXECUTION_MODE="", SANDBOX_PROFILE="")
        settings.mcp = mcp
    return mcp


def _provider_payload(provider: Any) -> dict[str, str]:
    server = getattr(provider, "server", None)
    return {
        "name": str(getattr(server, "name", "") or ""),
        "execution_mode": str(getattr(server, "execution_mode", "") or ""),
        "tools": str(len(getattr(provider, "tools", []) or [])),
    }


def _provider_name(provider: Any) -> str:
    return str(getattr(getattr(provider, "server", None), "name", "") or "")


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
            execution_mode=str(getattr(settings, "EXECUTION_MODE", "") or "trusted_control_plane"),
            sandbox_profile=str(getattr(settings, "SANDBOX_PROFILE", "") or ""),
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
    settings.EXECUTION_MODE = active.execution_mode
    settings.SANDBOX_PROFILE = active.sandbox_profile


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


async def _find_mcp_record(context: ToolRuntimeContext, name: str) -> Any | None:
    target = str(name or "default").strip() or "default"
    return next((record for record in await _mcp_records(context) if record.name == target), None)


async def _disable_other_mcp_configs(context: ToolRuntimeContext, active_name: str) -> None:
    store = getattr(context, "mcp_config_store", None)
    if store is None:
        return
    active = str(active_name or "default").strip() or "default"
    for record in await _mcp_records(context):
        if record.name != active and record.enabled:
            await store.save(replace(record, enabled=False))


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
