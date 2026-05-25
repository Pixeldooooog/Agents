from __future__ import annotations

import time
from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional, Protocol

from agents.kernel.persistence import SQLiteDatabase, json_dumps, json_list


@dataclass(frozen=True)
class MCPAuthTokenRecord:
    name: str
    access_token: str
    token_type: str = "Bearer"
    refresh_token: str = ""
    expires_at: float = 0.0
    scopes: list[str] = field(default_factory=list)
    tenant_id: str = ""
    user_id: str = ""
    agent_id: str = ""
    workspace_id: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def with_update(self) -> "MCPAuthTokenRecord":
        return replace(self, updated_at=time.time())

    def is_expired(self, *, leeway_seconds: float = 0.0) -> bool:
        return bool(self.expires_at and self.expires_at <= time.time() + max(0.0, leeway_seconds))

    def authorization_header(self) -> str:
        token = str(self.access_token or "").strip()
        if not token:
            return ""
        token_type = str(self.token_type or "Bearer").strip() or "Bearer"
        return "%s %s" % (token_type, token)


class MCPAuthTokenStore(Protocol):
    async def save(self, token: MCPAuthTokenRecord) -> None:
        raise NotImplementedError()

    async def get(
        self,
        name: str,
        tenant_id: str,
        user_id: str = "",
        agent_id: str = "",
        workspace_id: str = "",
    ) -> Optional[MCPAuthTokenRecord]:
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


class InMemoryMCPAuthTokenStore:
    def __init__(self):
        self._tokens: Dict[tuple[str, str, str, str, str], MCPAuthTokenRecord] = {}

    async def save(self, token: MCPAuthTokenRecord) -> None:
        record = token.with_update()
        self._tokens[_key(record)] = record

    async def get(
        self,
        name: str,
        tenant_id: str,
        user_id: str = "",
        agent_id: str = "",
        workspace_id: str = "",
    ) -> Optional[MCPAuthTokenRecord]:
        matches = [
            token
            for token in self._tokens.values()
            if token.name == _name(name) and _matches(token, tenant_id, user_id, agent_id, workspace_id)
        ]
        return _most_specific(matches)

    async def delete(
        self,
        name: str,
        tenant_id: str,
        user_id: str = "",
        agent_id: str = "",
        workspace_id: str = "",
    ) -> None:
        for key, token in list(self._tokens.items()):
            if token.name == _name(name) and _matches(token, tenant_id, user_id, agent_id, workspace_id):
                self._tokens.pop(key, None)


class SQLiteMCPAuthTokenStore:
    def __init__(self, database: SQLiteDatabase):
        self.database = database

    async def save(self, token: MCPAuthTokenRecord) -> None:
        record = token.with_update()
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO mcp_auth_tokens (
                    name, access_token, token_type, refresh_token, expires_at, scopes_json,
                    tenant_id, user_id, agent_id, workspace_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(tenant_id, user_id, agent_id, workspace_id, name) DO UPDATE SET
                    access_token = excluded.access_token,
                    token_type = excluded.token_type,
                    refresh_token = excluded.refresh_token,
                    expires_at = excluded.expires_at,
                    scopes_json = excluded.scopes_json,
                    updated_at = excluded.updated_at
                """,
                (
                    record.name,
                    record.access_token,
                    record.token_type,
                    record.refresh_token,
                    float(record.expires_at or 0.0),
                    json_dumps(record.scopes),
                    record.tenant_id,
                    record.user_id,
                    record.agent_id,
                    record.workspace_id,
                    record.created_at,
                    record.updated_at,
                ),
            )

    async def get(
        self,
        name: str,
        tenant_id: str,
        user_id: str = "",
        agent_id: str = "",
        workspace_id: str = "",
    ) -> Optional[MCPAuthTokenRecord]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM mcp_auth_tokens
                WHERE name = ?
                  AND tenant_id = ?
                  AND (user_id = '' OR user_id = ?)
                  AND (agent_id = '' OR agent_id = ?)
                  AND (workspace_id = '' OR workspace_id = ?)
                """,
                (_name(name), tenant_id, user_id, agent_id, workspace_id),
            ).fetchall()
        return _most_specific([_record_from_row(row) for row in rows])

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
                DELETE FROM mcp_auth_tokens
                WHERE name = ?
                  AND tenant_id = ?
                  AND (user_id = '' OR user_id = ?)
                  AND (agent_id = '' OR agent_id = ?)
                  AND (workspace_id = '' OR workspace_id = ?)
                """,
                (_name(name), tenant_id, user_id, agent_id, workspace_id),
            )


async def mcp_authorization_headers_for_scope(
    store: MCPAuthTokenStore | None,
    *,
    names: List[str],
    tenant_id: str,
    user_id: str = "",
    agent_id: str = "",
    workspace_id: str = "",
    leeway_seconds: float = 300.0,
) -> dict[str, str]:
    if store is None:
        return {}
    headers: dict[str, str] = {}
    for name in sorted({_name(item) for item in names if str(item or "").strip()}):
        token = await store.get(
            name,
            tenant_id=tenant_id,
            user_id=user_id,
            agent_id=agent_id,
            workspace_id=workspace_id,
        )
        if token is None or token.is_expired(leeway_seconds=leeway_seconds):
            continue
        header = token.authorization_header()
        if header:
            headers[name] = header
    return headers


def merge_cached_authorization_header(headers: dict[str, str], authorization: str) -> dict[str, str]:
    merged = {str(key): str(value) for key, value in dict(headers or {}).items()}
    if not str(authorization or "").strip():
        return merged
    if any(key.lower() == "authorization" for key in merged):
        return merged
    merged["Authorization"] = str(authorization).strip()
    return merged


def _key(record: MCPAuthTokenRecord) -> tuple[str, str, str, str, str]:
    return (record.tenant_id, record.user_id, record.agent_id, record.workspace_id, record.name)


def _matches(record: MCPAuthTokenRecord, tenant_id: str, user_id: str, agent_id: str, workspace_id: str) -> bool:
    return (
        record.tenant_id == tenant_id
        and record.user_id in ("", user_id)
        and record.agent_id in ("", agent_id)
        and record.workspace_id in ("", workspace_id)
    )


def _most_specific(records: List[MCPAuthTokenRecord]) -> Optional[MCPAuthTokenRecord]:
    if not records:
        return None
    return sorted(
        records,
        key=lambda record: (
            bool(record.workspace_id),
            bool(record.agent_id),
            bool(record.user_id),
            record.updated_at,
        ),
        reverse=True,
    )[0]


def _record_from_row(row) -> MCPAuthTokenRecord:
    return MCPAuthTokenRecord(
        name=str(row["name"]),
        access_token=str(row["access_token"] or ""),
        token_type=str(row["token_type"] or "Bearer"),
        refresh_token=str(row["refresh_token"] or ""),
        expires_at=float(row["expires_at"] or 0.0),
        scopes=[str(item) for item in json_list(row["scopes_json"])],
        tenant_id=str(row["tenant_id"] or ""),
        user_id=str(row["user_id"] or ""),
        agent_id=str(row["agent_id"] or ""),
        workspace_id=str(row["workspace_id"] or ""),
        created_at=float(row["created_at"]),
        updated_at=float(row["updated_at"]),
    )


def _name(value: str) -> str:
    return str(value or "default").strip() or "default"
