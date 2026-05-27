"""SDK control-response handlers for MCP server state and messages."""

from __future__ import annotations

import inspect
from dataclasses import replace
from typing import Any

from agents.kernel.mcp.config import MCPServerRecord
from agents.sdk.control import (
    SDKControlMcpMessageRequest,
    SDKControlMcpReconnectRequest,
    SDKControlMcpSetServersRequest,
    SDKControlMcpToggleRequest,
)
from agents.sdk.control_payloads import (
    _mcp_record_from_control_config,
    _mcp_server_status_from_record,
    _merge_mcp_server_statuses,
    _settings_mcp_server_statuses,
)
from agents.sdk.mcp.control import active_session_for_options, reconnect_mcp_server
from agents.sdk.types import SDKOptions


class SDKControlMcpMixin:
    async def _mcp_statuses_for_options(self, options: SDKOptions) -> list[dict[str, Any]]:
        statuses = await self._sdk_mcp_server_statuses_for_scope(
            tenant_id=options.tenant_id or "",
            user_id=options.user_id or "",
            agent_id=options.agent_id or "",
            workspace_id="",
        )
        sdk_statuses = [{"name": name, "status": "connected"} for name in self.sdk_mcp_handlers]
        return [dict(item) for item in _merge_mcp_server_statuses(sdk_statuses, statuses)]

    async def _mcp_set_servers_control_response(
        self,
        request: SDKControlMcpSetServersRequest,
        options: SDKOptions,
    ) -> dict[str, Any]:
        assert self.persistence is not None
        tenant_id = options.tenant_id or ""
        user_id = options.user_id or ""
        agent_id = options.agent_id or ""
        workspace_id = ""
        existing = await self.persistence.mcp_configs.list_for_scope(
            tenant_id=tenant_id,
            user_id=user_id,
            agent_id=agent_id,
            workspace_id=workspace_id,
        )
        wanted = {str(name): dict(config) for name, config in request.servers.items()}
        existing_names = {record.name for record in existing}
        removed: list[str] = []
        for record in existing:
            if record.name not in wanted:
                await self.persistence.mcp_configs.delete(
                    record.name,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    agent_id=agent_id,
                    workspace_id=workspace_id,
                )
                removed.append(record.name)
        added: list[str] = []
        errors: dict[str, str] = {}
        for name, config in wanted.items():
            try:
                await self.persistence.mcp_configs.save(
                    _mcp_record_from_control_config(
                        name,
                        config,
                        tenant_id=tenant_id,
                        user_id=user_id,
                        agent_id=agent_id,
                        workspace_id=workspace_id,
                    )
                )
                if name not in existing_names:
                    added.append(name)
            except Exception as exc:
                errors[name] = str(exc)
        return {"added": sorted(added), "removed": sorted(removed), "errors": errors}

    async def _mcp_toggle_control_response(
        self,
        request: SDKControlMcpToggleRequest,
        options: SDKOptions,
    ) -> dict[str, Any]:
        assert self.persistence is not None
        tenant_id = options.tenant_id or ""
        user_id = options.user_id or ""
        agent_id = options.agent_id or ""
        workspace_id = ""
        records = await self.persistence.mcp_configs.list_for_scope(
            tenant_id=tenant_id,
            user_id=user_id,
            agent_id=agent_id,
            workspace_id=workspace_id,
        )
        for record in records:
            if record.name == request.serverName:
                await self.persistence.mcp_configs.save(replace(record, enabled=request.enabled))
                return {"serverName": request.serverName, "enabled": request.enabled}
        if request.serverName in self.sdk_mcp_handlers:
            await self.persistence.mcp_configs.save(
                MCPServerRecord(
                    name=request.serverName,
                    command="",
                    transport="sdk",
                    enabled=request.enabled,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    agent_id=agent_id,
                    workspace_id=workspace_id,
                )
            )
            return {"serverName": request.serverName, "enabled": request.enabled}
        raise KeyError("MCP server not found: %s" % request.serverName)

    async def _mcp_reconnect_control_response(
        self,
        request: SDKControlMcpReconnectRequest,
        options: SDKOptions,
    ) -> dict[str, Any]:
        server_name = str(request.serverName or "").strip()
        return await reconnect_mcp_server(
            server_name,
            active_session=active_session_for_options(self.active_turn_sessions, options),
            sdk_handler_registered=server_name in self.sdk_mcp_handlers,
            sdk_server_enabled=lambda name: self._sdk_mcp_server_enabled(name, options),
            status_for_server=lambda name: self._mcp_status_for_server(name, options),
        )

    async def _mcp_status_for_server(self, server_name: str, options: SDKOptions) -> str | None:
        for item in await self._mcp_statuses_for_options(options):
            if str(item.get("name") or "") == server_name:
                return str(item.get("status") or "")
        return None

    async def _mcp_message_control_response(
        self,
        request: SDKControlMcpMessageRequest,
        options: SDKOptions,
    ) -> dict[str, Any]:
        handler = self.sdk_mcp_handlers.get(request.server_name)
        if handler is None:
            raise KeyError("SDK MCP server not registered: %s" % request.server_name)
        if not await self._sdk_mcp_server_enabled(request.server_name, options):
            raise RuntimeError("SDK MCP server is disabled: %s" % request.server_name)
        response = handler(request.message)
        if inspect.isawaitable(response):
            response = await response
        return {"mcp_response": response}

    async def _sdk_mcp_server_enabled(self, name: str, options: SDKOptions) -> bool:
        assert self.persistence is not None
        records = await self.persistence.mcp_configs.list_for_scope(
            tenant_id=options.tenant_id or "",
            user_id=options.user_id or "",
            agent_id=options.agent_id or "",
            workspace_id="",
        )
        for record in records:
            if record.name == name:
                return bool(record.enabled)
        return True

    async def _sdk_mcp_server_statuses_for_scope(
        self,
        *,
        tenant_id: str,
        user_id: str = "",
        agent_id: str = "",
        workspace_id: str = "",
    ) -> list[dict[str, str]]:
        servers = _settings_mcp_server_statuses(self.settings)
        if self.persistence is None:
            return servers
        try:
            records = await self.persistence.mcp_configs.list_for_scope(
                tenant_id=tenant_id,
                user_id=user_id,
                agent_id=agent_id,
                workspace_id=workspace_id,
            )
        except Exception:
            return servers
        return _merge_mcp_server_statuses(servers, [_mcp_server_status_from_record(record) for record in records])
