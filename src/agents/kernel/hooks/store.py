from __future__ import annotations

from typing import Any, List, Optional, Protocol

from agents.kernel.hooks.registry import HookRecord
from agents.kernel.persistence import SQLiteDatabase, json_dict, json_dumps


class HookStore(Protocol):
    async def save(
        self,
        hook: HookRecord,
        tenant_id: str,
        user_id: str = "",
        agent_id: str = "",
        workspace_id: str = "",
    ) -> None:
        raise NotImplementedError()

    async def list_for_scope(
        self,
        tenant_id: str,
        user_id: str = "",
        agent_id: str = "",
        workspace_id: str = "",
    ) -> List[HookRecord]:
        raise NotImplementedError()

    async def delete(
        self,
        hook_id: str,
        tenant_id: str,
        user_id: str = "",
        agent_id: str = "",
        workspace_id: str = "",
    ) -> None:
        raise NotImplementedError()


async def hydrate_hook_registry(registry: Any, store: Optional[HookStore], workspace: Any) -> None:
    if store is None:
        return
    hooks = await store.list_for_scope(
        workspace.tenant_id,
        user_id=workspace.user_id,
        agent_id=workspace.agent_id,
        workspace_id=workspace.workspace_id,
    )
    registry.replace_all(hooks)


async def save_hook_record(hook: HookRecord, store: Optional[HookStore], workspace: Any) -> None:
    if store is None:
        return
    await store.save(
        hook,
        workspace.tenant_id,
        user_id=workspace.user_id,
        agent_id=workspace.agent_id,
        workspace_id=workspace.workspace_id,
    )


async def delete_hook_record(hook_id: str, store: Optional[HookStore], workspace: Any) -> None:
    if store is None:
        return
    await store.delete(
        hook_id,
        workspace.tenant_id,
        user_id=workspace.user_id,
        agent_id=workspace.agent_id,
        workspace_id=workspace.workspace_id,
    )


class InMemoryHookStore:
    def __init__(self):
        self._hooks: dict[tuple[str, str, str, str, str], HookRecord] = {}

    async def save(
        self,
        hook: HookRecord,
        tenant_id: str,
        user_id: str = "",
        agent_id: str = "",
        workspace_id: str = "",
    ) -> None:
        self._hooks[(tenant_id, user_id, agent_id, workspace_id, hook.hook_id)] = hook

    async def list_for_scope(
        self,
        tenant_id: str,
        user_id: str = "",
        agent_id: str = "",
        workspace_id: str = "",
    ) -> List[HookRecord]:
        records = [
            hook
            for scope, hook in self._hooks.items()
            if _scope_matches(scope, tenant_id, user_id, agent_id, workspace_id)
        ]
        return sorted(records, key=lambda hook: (hook.updated_at, hook.hook_id), reverse=True)

    async def delete(
        self,
        hook_id: str,
        tenant_id: str,
        user_id: str = "",
        agent_id: str = "",
        workspace_id: str = "",
    ) -> None:
        for scope in list(self._hooks):
            if scope[-1] == hook_id and _scope_matches(scope, tenant_id, user_id, agent_id, workspace_id):
                self._hooks.pop(scope, None)


class SQLiteHookStore:
    def __init__(self, database: SQLiteDatabase):
        self.database = database

    async def save(
        self,
        hook: HookRecord,
        tenant_id: str,
        user_id: str = "",
        agent_id: str = "",
        workspace_id: str = "",
    ) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO hooks (
                    hook_id, tenant_id, user_id, agent_id, workspace_id, event,
                    name, action, content, enabled, metadata_json, created_at,
                    updated_at, last_run_at, run_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(hook_id) DO UPDATE SET
                    tenant_id = excluded.tenant_id,
                    user_id = excluded.user_id,
                    agent_id = excluded.agent_id,
                    workspace_id = excluded.workspace_id,
                    event = excluded.event,
                    name = excluded.name,
                    action = excluded.action,
                    content = excluded.content,
                    enabled = excluded.enabled,
                    metadata_json = excluded.metadata_json,
                    updated_at = excluded.updated_at,
                    last_run_at = excluded.last_run_at,
                    run_count = excluded.run_count
                """,
                (
                    hook.hook_id,
                    tenant_id,
                    user_id,
                    agent_id,
                    workspace_id,
                    hook.event,
                    hook.name,
                    hook.action,
                    hook.content,
                    1 if hook.enabled else 0,
                    json_dumps(hook.metadata),
                    hook.created_at,
                    hook.updated_at,
                    hook.last_run_at,
                    hook.run_count,
                ),
            )

    async def list_for_scope(
        self,
        tenant_id: str,
        user_id: str = "",
        agent_id: str = "",
        workspace_id: str = "",
    ) -> List[HookRecord]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM hooks
                WHERE tenant_id = ?
                  AND (user_id = '' OR user_id = ?)
                  AND (agent_id = '' OR agent_id = ?)
                  AND (workspace_id = '' OR workspace_id = ?)
                ORDER BY updated_at DESC, hook_id ASC
                """,
                (tenant_id, user_id, agent_id, workspace_id),
            ).fetchall()
        return [_hook_from_row(row) for row in rows]

    async def delete(
        self,
        hook_id: str,
        tenant_id: str,
        user_id: str = "",
        agent_id: str = "",
        workspace_id: str = "",
    ) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                DELETE FROM hooks
                WHERE hook_id = ?
                  AND tenant_id = ?
                  AND (user_id = '' OR user_id = ?)
                  AND (agent_id = '' OR agent_id = ?)
                  AND (workspace_id = '' OR workspace_id = ?)
                """,
                (hook_id, tenant_id, user_id, agent_id, workspace_id),
            )


def _hook_from_row(row) -> HookRecord:
    return HookRecord(
        hook_id=str(row["hook_id"]),
        event=str(row["event"]),
        name=str(row["name"]),
        action=str(row["action"]),
        content=str(row["content"] or ""),
        enabled=bool(int(row["enabled"])),
        metadata={key: str(value) for key, value in json_dict(row["metadata_json"]).items()},
        created_at=float(row["created_at"]),
        updated_at=float(row["updated_at"]),
        last_run_at=float(row["last_run_at"] or 0),
        run_count=int(row["run_count"] or 0),
    )


def _scope_matches(scope: tuple[str, str, str, str, str], tenant_id: str, user_id: str, agent_id: str, workspace_id: str) -> bool:
    return (
        scope[0] == tenant_id
        and scope[1] in ("", user_id)
        and scope[2] in ("", agent_id)
        and scope[3] in ("", workspace_id)
    )
