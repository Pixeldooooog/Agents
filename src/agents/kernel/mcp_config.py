from __future__ import annotations

import time
import json
from dataclasses import dataclass, field, replace
from typing import List, Optional, Protocol, Dict

from agents.kernel.persistence import SQLiteDatabase


@dataclass(frozen=True)
class MCPServerRecord:
    name: str
    command: str
    transport: str = "stdio"
    url: str = ""
    headers: Dict[str, str] = field(default_factory=dict)
    execution_mode: str = "trusted_control_plane"
    sandbox_profile: str = ""
    auth_required: bool = False
    auth_url: str = ""
    auth_status: str = ""
    auth_message: str = ""
    enabled: bool = True
    agent_id: str = ""
    tenant_id: str = ""
    user_id: str = ""
    workspace_id: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def with_update(self) -> "MCPServerRecord":
        return replace(self, updated_at=time.time())

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "command": self.command,
            "transport": self.transport,
            "url": self.url,
            "headers": dict(self.headers),
            "execution_mode": self.execution_mode,
            "sandbox_profile": self.sandbox_profile,
            "auth_required": self.auth_required,
            "auth_url": self.auth_url,
            "auth_status": self.auth_status,
            "auth_message": self.auth_message,
            "enabled": self.enabled,
            "agent_id": self.agent_id,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "workspace_id": self.workspace_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class MCPConfigStore(Protocol):
    async def save(self, server: MCPServerRecord) -> None:
        raise NotImplementedError()

    async def list_for_scope(
        self,
        tenant_id: str,
        user_id: str = "",
        agent_id: str = "",
        workspace_id: str = "",
    ) -> List[MCPServerRecord]:
        raise NotImplementedError()

    async def delete(
        self,
        name: str,
        tenant_id: str,
        user_id: str = "",
        agent_id: str = "",
        workspace_id: str = "",
    ) -> None:
        raise NotImplementedError()


class InMemoryMCPConfigStore:
    def __init__(self):
        self._records: dict[tuple[str, str, str, str, str], MCPServerRecord] = {}

    async def save(self, server: MCPServerRecord) -> None:
        record = server.with_update()
        self._records[_key(record)] = record

    async def list_for_scope(
        self,
        tenant_id: str,
        user_id: str = "",
        agent_id: str = "",
        workspace_id: str = "",
    ) -> List[MCPServerRecord]:
        records = [
            record
            for record in self._records.values()
            if _matches(record, tenant_id, user_id, agent_id, workspace_id)
        ]
        return sorted(records, key=lambda record: (record.updated_at, record.name), reverse=True)

    async def delete(
        self,
        name: str,
        tenant_id: str,
        user_id: str = "",
        agent_id: str = "",
        workspace_id: str = "",
    ) -> None:
        for key, record in list(self._records.items()):
            if record.name == _name(name) and _matches(record, tenant_id, user_id, agent_id, workspace_id):
                self._records.pop(key, None)


class SQLiteMCPConfigStore:
    def __init__(self, database: SQLiteDatabase):
        self.database = database

    async def save(self, server: MCPServerRecord) -> None:
        record = server.with_update()
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO mcp_servers (
                    name, command, transport, url, headers_json, execution_mode, sandbox_profile,
                    auth_required, auth_url, auth_status, auth_message, enabled,
                    agent_id, tenant_id, user_id, workspace_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(tenant_id, user_id, agent_id, workspace_id, name) DO UPDATE SET
                    command = excluded.command,
                    transport = excluded.transport,
                    url = excluded.url,
                    headers_json = excluded.headers_json,
                    execution_mode = excluded.execution_mode,
                    sandbox_profile = excluded.sandbox_profile,
                    auth_required = excluded.auth_required,
                    auth_url = excluded.auth_url,
                    auth_status = excluded.auth_status,
                    auth_message = excluded.auth_message,
                    enabled = excluded.enabled,
                    updated_at = excluded.updated_at
                """,
                (
                    record.name,
                    record.command,
                    record.transport,
                    record.url,
                    json.dumps(record.headers, ensure_ascii=False, sort_keys=True),
                    record.execution_mode,
                    record.sandbox_profile,
                    1 if record.auth_required else 0,
                    record.auth_url,
                    record.auth_status,
                    record.auth_message,
                    1 if record.enabled else 0,
                    record.agent_id,
                    record.tenant_id,
                    record.user_id,
                    record.workspace_id,
                    record.created_at,
                    record.updated_at,
                ),
            )

    async def list_for_scope(
        self,
        tenant_id: str,
        user_id: str = "",
        agent_id: str = "",
        workspace_id: str = "",
    ) -> List[MCPServerRecord]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM mcp_servers
                WHERE tenant_id = ?
                  AND (user_id = '' OR user_id = ?)
                  AND (agent_id = '' OR agent_id = ?)
                  AND (workspace_id = '' OR workspace_id = ?)
                ORDER BY updated_at DESC, name ASC
                """,
                (tenant_id, user_id, agent_id, workspace_id),
            ).fetchall()
        return [_record_from_row(row) for row in rows]

    async def delete(
        self,
        name: str,
        tenant_id: str,
        user_id: str = "",
        agent_id: str = "",
        workspace_id: str = "",
    ) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                DELETE FROM mcp_servers
                WHERE name = ?
                  AND tenant_id = ?
                  AND (user_id = '' OR user_id = ?)
                  AND (agent_id = '' OR agent_id = ?)
                  AND (workspace_id = '' OR workspace_id = ?)
                """,
                (_name(name), tenant_id, user_id, agent_id, workspace_id),
            )


def _record_from_row(row) -> MCPServerRecord:
    return MCPServerRecord(
        name=str(row["name"]),
        command=str(row["command"]),
        transport=str(row["transport"] or "stdio"),
        url=str(row["url"] or ""),
        headers=_decode_headers(row["headers_json"]),
        execution_mode=str(row["execution_mode"] or "trusted_control_plane"),
        sandbox_profile=str(row["sandbox_profile"] or ""),
        auth_required=bool(int(row["auth_required"] or 0)),
        auth_url=str(row["auth_url"] or ""),
        auth_status=str(row["auth_status"] or ""),
        auth_message=str(row["auth_message"] or ""),
        enabled=bool(int(row["enabled"])),
        agent_id=str(row["agent_id"] or ""),
        tenant_id=str(row["tenant_id"] or ""),
        user_id=str(row["user_id"] or ""),
        workspace_id=str(row["workspace_id"] or ""),
        created_at=float(row["created_at"]),
        updated_at=float(row["updated_at"]),
    )


def server_record_for_scope(
    *,
    name: str,
    workspace,
    command: str = "",
    transport: str = "stdio",
    url: str = "",
    headers: dict[str, str] | None = None,
    execution_mode: str = "trusted_control_plane",
    sandbox_profile: str = "",
    auth_required: bool = False,
    auth_url: str = "",
    auth_status: str = "",
    auth_message: str = "",
    enabled: bool = True,
) -> MCPServerRecord:
    return MCPServerRecord(
        name=_name(name),
        command=str(command or "").strip(),
        transport=_transport(transport),
        url=str(url or "").strip(),
        headers=_headers(headers),
        execution_mode=str(execution_mode or "trusted_control_plane"),
        sandbox_profile=str(sandbox_profile or ""),
        auth_required=bool(auth_required),
        auth_url=str(auth_url or "").strip(),
        auth_status=str(auth_status or ""),
        auth_message=str(auth_message or ""),
        enabled=bool(enabled),
        tenant_id=workspace.tenant_id,
        user_id=workspace.user_id,
        agent_id=workspace.agent_id,
        workspace_id=workspace.workspace_id,
    )


def _key(record: MCPServerRecord) -> tuple[str, str, str, str, str]:
    return (record.tenant_id, record.user_id, record.agent_id, record.workspace_id, record.name)


def _matches(record: MCPServerRecord, tenant_id: str, user_id: str, agent_id: str, workspace_id: str) -> bool:
    return (
        record.tenant_id == tenant_id
        and record.user_id in ("", user_id)
        and record.agent_id in ("", agent_id)
        and record.workspace_id in ("", workspace_id)
    )


def _name(value: str) -> str:
    return str(value or "default").strip() or "default"


def _transport(value: str) -> str:
    return str(value or "stdio").strip() or "stdio"


def _headers(value: dict[str, str] | None) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(key): str(item) for key, item in value.items()}


def _decode_headers(value) -> dict[str, str]:
    try:
        parsed = json.loads(str(value or "{}"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {str(key): str(item) for key, item in parsed.items()}
