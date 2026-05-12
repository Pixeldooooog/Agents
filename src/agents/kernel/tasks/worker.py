from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List, Optional, Protocol

from agents.kernel.persistence import SQLiteDatabase, json_dict, json_dumps
from agents.kernel.tasks.runner import TaskExecutionResult, TaskRunner


@dataclass(frozen=True)
class TaskQueueItem:
    task_id: str
    created_at: float = field(default_factory=time.time)
    metadata: dict[str, str] = field(default_factory=dict)
    tenant_id: str = ""
    user_id: str = ""
    agent_id: str = ""
    workspace_id: str = ""


class TaskQueue(Protocol):
    async def enqueue(
        self,
        task_id: str,
        metadata: dict[str, str] | None = None,
        *,
        tenant_id: str = "",
        user_id: str = "",
        agent_id: str = "",
        workspace_id: str = "",
    ) -> TaskQueueItem:
        raise NotImplementedError()

    async def dequeue(
        self,
        *,
        tenant_id: str = "",
        user_id: str = "",
        agent_id: str = "",
        workspace_id: str = "",
    ) -> Optional[TaskQueueItem]:
        raise NotImplementedError()

    async def items(
        self,
        *,
        tenant_id: str = "",
        user_id: str = "",
        agent_id: str = "",
        workspace_id: str = "",
    ) -> List[TaskQueueItem]:
        raise NotImplementedError()

    async def size(
        self,
        *,
        tenant_id: str = "",
        user_id: str = "",
        agent_id: str = "",
        workspace_id: str = "",
    ) -> int:
        raise NotImplementedError()


class InMemoryTaskQueue:
    def __init__(self):
        self._items: List[TaskQueueItem] = []

    async def enqueue(
        self,
        task_id: str,
        metadata: dict[str, str] | None = None,
        *,
        tenant_id: str = "",
        user_id: str = "",
        agent_id: str = "",
        workspace_id: str = "",
    ) -> TaskQueueItem:
        item = TaskQueueItem(
            task_id=task_id,
            metadata=dict(metadata or {}),
            tenant_id=str(tenant_id or ""),
            user_id=str(user_id or ""),
            agent_id=str(agent_id or ""),
            workspace_id=str(workspace_id or ""),
        )
        self._items.append(item)
        return item

    async def dequeue(
        self,
        *,
        tenant_id: str = "",
        user_id: str = "",
        agent_id: str = "",
        workspace_id: str = "",
    ) -> Optional[TaskQueueItem]:
        for index, item in enumerate(self._items):
            if _matches_scope(item, tenant_id, user_id, agent_id, workspace_id):
                return self._items.pop(index)
        return None

    async def items(
        self,
        *,
        tenant_id: str = "",
        user_id: str = "",
        agent_id: str = "",
        workspace_id: str = "",
    ) -> List[TaskQueueItem]:
        return [item for item in self._items if _matches_scope(item, tenant_id, user_id, agent_id, workspace_id)]

    async def size(
        self,
        *,
        tenant_id: str = "",
        user_id: str = "",
        agent_id: str = "",
        workspace_id: str = "",
    ) -> int:
        return len(await self.items(tenant_id=tenant_id, user_id=user_id, agent_id=agent_id, workspace_id=workspace_id))


class SQLiteTaskQueue:
    def __init__(self, database: SQLiteDatabase):
        self.database = database

    async def enqueue(
        self,
        task_id: str,
        metadata: dict[str, str] | None = None,
        *,
        tenant_id: str = "",
        user_id: str = "",
        agent_id: str = "",
        workspace_id: str = "",
    ) -> TaskQueueItem:
        item = TaskQueueItem(
            task_id=str(task_id),
            metadata={key: str(value) for key, value in dict(metadata or {}).items()},
            tenant_id=str(tenant_id or ""),
            user_id=str(user_id or ""),
            agent_id=str(agent_id or ""),
            workspace_id=str(workspace_id or ""),
        )
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO task_queue_items (
                    task_id, tenant_id, user_id, agent_id, workspace_id,
                    metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.task_id,
                    item.tenant_id,
                    item.user_id,
                    item.agent_id,
                    item.workspace_id,
                    json_dumps(item.metadata),
                    item.created_at,
                ),
            )
        return item

    async def dequeue(
        self,
        *,
        tenant_id: str = "",
        user_id: str = "",
        agent_id: str = "",
        workspace_id: str = "",
    ) -> Optional[TaskQueueItem]:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM task_queue_items
                WHERE (? = '' OR tenant_id = ?)
                  AND (? = '' OR user_id = '' OR user_id = ?)
                  AND (? = '' OR agent_id = '' OR agent_id = ?)
                  AND (? = '' OR workspace_id = '' OR workspace_id = ?)
                ORDER BY created_at ASC, id ASC
                LIMIT 1
                """,
                (tenant_id, tenant_id, user_id, user_id, agent_id, agent_id, workspace_id, workspace_id),
            ).fetchone()
            if row is None:
                return None
            connection.execute("DELETE FROM task_queue_items WHERE id = ?", (row["id"],))
        return _item_from_row(row)

    async def items(
        self,
        *,
        tenant_id: str = "",
        user_id: str = "",
        agent_id: str = "",
        workspace_id: str = "",
    ) -> List[TaskQueueItem]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM task_queue_items
                WHERE (? = '' OR tenant_id = ?)
                  AND (? = '' OR user_id = '' OR user_id = ?)
                  AND (? = '' OR agent_id = '' OR agent_id = ?)
                  AND (? = '' OR workspace_id = '' OR workspace_id = ?)
                ORDER BY created_at ASC, id ASC
                """,
                (tenant_id, tenant_id, user_id, user_id, agent_id, agent_id, workspace_id, workspace_id),
            ).fetchall()
        return [_item_from_row(row) for row in rows]

    async def size(
        self,
        *,
        tenant_id: str = "",
        user_id: str = "",
        agent_id: str = "",
        workspace_id: str = "",
    ) -> int:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS count FROM task_queue_items
                WHERE (? = '' OR tenant_id = ?)
                  AND (? = '' OR user_id = '' OR user_id = ?)
                  AND (? = '' OR agent_id = '' OR agent_id = ?)
                  AND (? = '' OR workspace_id = '' OR workspace_id = ?)
                """,
                (tenant_id, tenant_id, user_id, user_id, agent_id, agent_id, workspace_id, workspace_id),
            ).fetchone()
        return int(row["count"] or 0)


class TaskWorker:
    def __init__(self, queue: TaskQueue, runner: TaskRunner):
        self.queue = queue
        self.runner = runner

    async def run_next(self) -> Optional[TaskExecutionResult]:
        item = await self.queue.dequeue()
        if item is None:
            return None
        return await self.runner.run_task(item.task_id)

    async def run_until_empty(self, limit: int | None = None) -> List[TaskExecutionResult]:
        results: List[TaskExecutionResult] = []
        while limit is None or len(results) < limit:
            result = await self.run_next()
            if result is None:
                break
            results.append(result)
        return results


def _item_from_row(row) -> TaskQueueItem:
    return TaskQueueItem(
        task_id=str(row["task_id"]),
        created_at=float(row["created_at"]),
        metadata={key: str(value) for key, value in json_dict(row["metadata_json"]).items()},
        tenant_id=str(row["tenant_id"] or ""),
        user_id=str(row["user_id"] or ""),
        agent_id=str(row["agent_id"] or ""),
        workspace_id=str(row["workspace_id"] or ""),
    )


def _matches_scope(item: TaskQueueItem, tenant_id: str, user_id: str, agent_id: str, workspace_id: str) -> bool:
    if not any([tenant_id, user_id, agent_id, workspace_id]):
        return True
    return (
        (not tenant_id or item.tenant_id == tenant_id)
        and (not user_id or item.user_id in ("", user_id))
        and (not agent_id or item.agent_id in ("", agent_id))
        and (not workspace_id or item.workspace_id in ("", workspace_id))
    )
