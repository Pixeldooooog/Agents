from __future__ import annotations

import time
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Optional, Protocol
from uuid import uuid4

from agents.kernel.persistence import SQLiteDatabase, json_dict, json_dumps
from agents.kernel.specs import AgentSpec


@dataclass(frozen=True)
class ScheduleRecord:
    schedule_id: str
    title: str
    input: str
    schedule: str
    enabled: bool = True
    agent_id: str = ""
    tenant_id: str = ""
    user_id: str = ""
    workspace_id: str = ""
    metadata: dict[str, str] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    last_run_task_id: str = ""
    last_run_at: float = 0.0

    @classmethod
    def create(
        cls,
        *,
        spec: AgentSpec,
        title: str,
        input: str,
        schedule: str,
        enabled: bool = True,
        schedule_id: str = "",
        metadata: dict[str, str] | None = None,
    ) -> "ScheduleRecord":
        resolved = spec.with_workspace_defaults()
        return cls(
            schedule_id=schedule_id or "sched_%s" % uuid4().hex[:12],
            title=title,
            input=input,
            schedule=schedule,
            enabled=bool(enabled),
            agent_id=resolved.agent_id or resolved.workspace.agent_id,
            tenant_id=resolved.workspace.tenant_id,
            user_id=resolved.workspace.user_id,
            workspace_id=resolved.workspace.workspace_id,
            metadata=dict(metadata or {}),
        )

    @property
    def short_id(self) -> str:
        return short_schedule_id(self.schedule_id)

    def with_last_run(self, task_id: str) -> "ScheduleRecord":
        return replace(self, last_run_task_id=str(task_id or ""), last_run_at=time.time(), updated_at=time.time())

    def with_update(self) -> "ScheduleRecord":
        return replace(self, updated_at=time.time())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schedule_id": self.schedule_id,
            "short_id": self.short_id,
            "title": self.title,
            "input": self.input,
            "schedule": self.schedule,
            "enabled": self.enabled,
            "agent_id": self.agent_id,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "workspace_id": self.workspace_id,
            "metadata": dict(self.metadata),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_run_task_id": self.last_run_task_id,
            "last_run_at": self.last_run_at,
        }


class ScheduleStore(Protocol):
    async def save(self, schedule: ScheduleRecord) -> None:
        raise NotImplementedError()

    async def load(self, schedule_id: str) -> Optional[ScheduleRecord]:
        raise NotImplementedError()

    async def list_for_scope(
        self,
        tenant_id: str,
        user_id: str = "",
        agent_id: str = "",
        workspace_id: str = "",
    ) -> List[ScheduleRecord]:
        raise NotImplementedError()

    async def delete(self, schedule_id: str) -> None:
        raise NotImplementedError()


class InMemoryScheduleStore:
    def __init__(self):
        self._schedules: Dict[str, ScheduleRecord] = {}

    async def save(self, schedule: ScheduleRecord) -> None:
        self._schedules[schedule.schedule_id] = schedule.with_update()

    async def load(self, schedule_id: str) -> Optional[ScheduleRecord]:
        return self._schedules.get(schedule_id)

    async def list_for_scope(
        self,
        tenant_id: str,
        user_id: str = "",
        agent_id: str = "",
        workspace_id: str = "",
    ) -> List[ScheduleRecord]:
        return sorted(
            [
                schedule
                for schedule in self._schedules.values()
                if _schedule_matches(schedule, tenant_id, user_id, agent_id, workspace_id)
            ],
            key=lambda schedule: (schedule.updated_at, schedule.schedule_id),
            reverse=True,
        )

    async def delete(self, schedule_id: str) -> None:
        self._schedules.pop(schedule_id, None)


class SQLiteScheduleStore:
    def __init__(self, database: SQLiteDatabase):
        self.database = database

    async def save(self, schedule: ScheduleRecord) -> None:
        record = schedule.with_update()
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO schedules (
                    schedule_id, title, input, schedule, enabled, agent_id, tenant_id,
                    user_id, workspace_id, metadata_json, created_at, updated_at,
                    last_run_task_id, last_run_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(schedule_id) DO UPDATE SET
                    title = excluded.title,
                    input = excluded.input,
                    schedule = excluded.schedule,
                    enabled = excluded.enabled,
                    agent_id = excluded.agent_id,
                    tenant_id = excluded.tenant_id,
                    user_id = excluded.user_id,
                    workspace_id = excluded.workspace_id,
                    metadata_json = excluded.metadata_json,
                    updated_at = excluded.updated_at,
                    last_run_task_id = excluded.last_run_task_id,
                    last_run_at = excluded.last_run_at
                """,
                (
                    record.schedule_id,
                    record.title,
                    record.input,
                    record.schedule,
                    1 if record.enabled else 0,
                    record.agent_id,
                    record.tenant_id,
                    record.user_id,
                    record.workspace_id,
                    json_dumps(record.metadata),
                    record.created_at,
                    record.updated_at,
                    record.last_run_task_id,
                    record.last_run_at,
                ),
            )

    async def load(self, schedule_id: str) -> Optional[ScheduleRecord]:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM schedules WHERE schedule_id = ?", (schedule_id,)).fetchone()
        return _schedule_from_row(row) if row is not None else None

    async def list_for_scope(
        self,
        tenant_id: str,
        user_id: str = "",
        agent_id: str = "",
        workspace_id: str = "",
    ) -> List[ScheduleRecord]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM schedules
                WHERE tenant_id = ?
                  AND (user_id = '' OR user_id = ?)
                  AND (agent_id = '' OR agent_id = ?)
                  AND (workspace_id = '' OR workspace_id = ?)
                ORDER BY updated_at DESC, schedule_id ASC
                """,
                (tenant_id, user_id, agent_id, workspace_id),
            ).fetchall()
        return [_schedule_from_row(row) for row in rows]

    async def delete(self, schedule_id: str) -> None:
        with self.database.connect() as connection:
            connection.execute("DELETE FROM schedules WHERE schedule_id = ?", (schedule_id,))


def short_schedule_id(schedule_id: str) -> str:
    return str(schedule_id).replace("sched_", "", 1)[:12]


def _schedule_matches(schedule: ScheduleRecord, tenant_id: str, user_id: str, agent_id: str, workspace_id: str) -> bool:
    return (
        schedule.tenant_id == tenant_id
        and schedule.user_id in ("", user_id)
        and schedule.agent_id in ("", agent_id)
        and schedule.workspace_id in ("", workspace_id)
    )


def _schedule_from_row(row) -> ScheduleRecord:
    return ScheduleRecord(
        schedule_id=str(row["schedule_id"]),
        title=str(row["title"]),
        input=str(row["input"]),
        schedule=str(row["schedule"]),
        enabled=bool(int(row["enabled"])),
        agent_id=str(row["agent_id"] or ""),
        tenant_id=str(row["tenant_id"] or ""),
        user_id=str(row["user_id"] or ""),
        workspace_id=str(row["workspace_id"] or ""),
        metadata={key: str(value) for key, value in json_dict(row["metadata_json"]).items()},
        created_at=float(row["created_at"]),
        updated_at=float(row["updated_at"]),
        last_run_task_id=str(row["last_run_task_id"] or ""),
        last_run_at=float(row["last_run_at"] or 0),
    )
