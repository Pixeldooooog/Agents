from __future__ import annotations

from typing import Any

from agents.kernel.capabilities.tools.builtin.mcp.settings import apply_record_to_settings, headers, mcp_settings
from agents.kernel.capabilities.tools.context import ToolRuntimeContext
from agents.kernel.mcp.auth import mcp_authorization_headers_for_scope
from agents.kernel.mcp.config import server_record_for_scope


async def save_current_config(context: ToolRuntimeContext) -> None:
    store = getattr(context, "mcp_config_store", None)
    if store is None:
        return
    settings = mcp_settings(context)
    await save_record(
        context,
        server_record_for_scope(
            name=str(getattr(settings, "SERVER_NAME", "") or "default"),
            command=str(getattr(settings, "SERVER_COMMAND", "") or ""),
            transport=str(getattr(settings, "SERVER_TRANSPORT", "") or "stdio"),
            url=str(getattr(settings, "SERVER_URL", "") or ""),
            headers=headers(settings),
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


async def save_record(context: ToolRuntimeContext, record: Any) -> None:
    store = getattr(context, "mcp_config_store", None)
    if store is not None:
        await store.save(record)


async def hydrate_config(context: ToolRuntimeContext) -> None:
    store = getattr(context, "mcp_config_store", None)
    if store is None:
        return
    active = next((record for record in await records(context) if record.enabled), None)
    if active is not None:
        apply_record_to_settings(mcp_settings(context), active)


async def records(context: ToolRuntimeContext) -> list[Any]:
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


async def auth_headers(context: ToolRuntimeContext, config_records: list[Any]) -> dict[str, str]:
    store = getattr(context, "mcp_auth_store", None)
    if store is None:
        return {}
    workspace = context.workspace
    names = [
        str(getattr(record, "name", "") or "")
        for record in config_records
        if bool(getattr(record, "enabled", True))
    ]
    if not names:
        settings = mcp_settings(context)
        command = str(getattr(settings, "SERVER_COMMAND", "") or "").strip()
        selected_transport = str(getattr(settings, "SERVER_TRANSPORT", "stdio") or "stdio")
        url = str(getattr(settings, "SERVER_URL", "") or "").strip()
        if (selected_transport == "stdio" and command) or (selected_transport != "stdio" and url):
            names = [str(getattr(settings, "SERVER_NAME", "") or "default")]
    return await mcp_authorization_headers_for_scope(
        store,
        names=names,
        tenant_id=workspace.tenant_id,
        user_id=workspace.user_id,
        agent_id=workspace.agent_id,
        workspace_id=workspace.workspace_id,
    )


async def find_record(context: ToolRuntimeContext, name: str) -> Any | None:
    target = str(name or "default").strip() or "default"
    return next((record for record in await records(context) if record.name == target), None)


async def delete_config(context: ToolRuntimeContext, name: str) -> None:
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
