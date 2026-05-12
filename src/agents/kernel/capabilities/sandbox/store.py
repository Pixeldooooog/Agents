from __future__ import annotations

import time
from dataclasses import replace
from typing import Dict, List, Optional, Protocol

from agents.kernel.persistence import SQLiteDatabase, json_dumps

from .records import (
    SandboxEventRecord,
    SandboxLeaseRecord,
    SandboxWorkspaceSnapshotRecord,
    event_from_row as _event_from_row,
    lease_from_row as _lease_from_row,
    snapshot_from_row as _snapshot_from_row,
)


class SandboxStore(Protocol):
    async def save_lease(self, lease: SandboxLeaseRecord) -> None:
        raise NotImplementedError()

    async def load_lease(self, lease_id: str) -> Optional[SandboxLeaseRecord]:
        raise NotImplementedError()

    async def mark_released(self, lease_id: str) -> None:
        raise NotImplementedError()

    async def mark_released_for_run(self, run_id: str) -> None:
        raise NotImplementedError()

    async def list_leases_for_run(self, run_id: str) -> List[SandboxLeaseRecord]:
        raise NotImplementedError()

    async def record_event(self, event: SandboxEventRecord) -> None:
        raise NotImplementedError()

    async def list_events(self, lease_id: str) -> List[SandboxEventRecord]:
        raise NotImplementedError()

    async def list_events_for_run(self, run_id: str) -> List[SandboxEventRecord]:
        raise NotImplementedError()

    async def save_workspace_snapshot(self, snapshot: SandboxWorkspaceSnapshotRecord) -> None:
        raise NotImplementedError()

    async def list_workspace_snapshots_for_run(self, run_id: str) -> List[SandboxWorkspaceSnapshotRecord]:
        raise NotImplementedError()


class InMemorySandboxStore:
    def __init__(self):
        self._leases: Dict[str, SandboxLeaseRecord] = {}
        self._events: Dict[str, list[SandboxEventRecord]] = {}
        self._snapshots: Dict[str, list[SandboxWorkspaceSnapshotRecord]] = {}

    async def save_lease(self, lease: SandboxLeaseRecord) -> None:
        self._leases[lease.lease_id] = replace(lease, updated_at=time.time())

    async def load_lease(self, lease_id: str) -> Optional[SandboxLeaseRecord]:
        return self._leases.get(lease_id)

    async def mark_released(self, lease_id: str) -> None:
        lease = self._leases.get(lease_id)
        if lease is not None:
            self._leases[lease_id] = lease.with_status("released")

    async def mark_released_for_run(self, run_id: str) -> None:
        for lease_id, lease in list(self._leases.items()):
            if lease.run_id == run_id:
                self._leases[lease_id] = lease.with_status("released")

    async def list_leases_for_run(self, run_id: str) -> List[SandboxLeaseRecord]:
        return sorted(
            [lease for lease in self._leases.values() if lease.run_id == run_id],
            key=lambda lease: lease.created_at,
        )

    async def record_event(self, event: SandboxEventRecord) -> None:
        self._events.setdefault(event.lease_id, []).append(event)

    async def list_events(self, lease_id: str) -> List[SandboxEventRecord]:
        return list(self._events.get(lease_id, []))

    async def list_events_for_run(self, run_id: str) -> List[SandboxEventRecord]:
        events: list[SandboxEventRecord] = []
        for group in self._events.values():
            events.extend(event for event in group if event.run_id == run_id)
        return sorted(events, key=lambda event: event.created_at)

    async def save_workspace_snapshot(self, snapshot: SandboxWorkspaceSnapshotRecord) -> None:
        self._snapshots.setdefault(snapshot.run_id, []).append(snapshot)

    async def list_workspace_snapshots_for_run(self, run_id: str) -> List[SandboxWorkspaceSnapshotRecord]:
        return sorted(self._snapshots.get(run_id, []), key=lambda snapshot: snapshot.created_at)


class SQLiteSandboxStore:
    def __init__(self, database: SQLiteDatabase):
        self.database = database

    async def save_lease(self, lease: SandboxLeaseRecord) -> None:
        record = replace(lease, updated_at=time.time())
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO sandbox_leases (
                    lease_id, provider, tenant_id, user_id, agent_id, workspace_id, run_id, task_id,
                    status, profile_json, metadata_json, created_at, updated_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(lease_id) DO UPDATE SET
                    status = excluded.status,
                    profile_json = excluded.profile_json,
                    metadata_json = excluded.metadata_json,
                    updated_at = excluded.updated_at,
                    expires_at = excluded.expires_at
                """,
                (
                    record.lease_id,
                    record.provider,
                    record.tenant_id,
                    record.user_id,
                    record.agent_id,
                    record.workspace_id,
                    record.run_id,
                    record.task_id,
                    record.status,
                    json_dumps(record.profile),
                    json_dumps(record.metadata),
                    record.created_at,
                    record.updated_at,
                    record.expires_at,
                ),
            )

    async def load_lease(self, lease_id: str) -> Optional[SandboxLeaseRecord]:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM sandbox_leases WHERE lease_id = ?", (lease_id,)).fetchone()
        return _lease_from_row(row) if row is not None else None

    async def mark_released(self, lease_id: str) -> None:
        with self.database.connect() as connection:
            connection.execute(
                "UPDATE sandbox_leases SET status = ?, updated_at = ? WHERE lease_id = ?",
                ("released", time.time(), lease_id),
            )

    async def mark_released_for_run(self, run_id: str) -> None:
        with self.database.connect() as connection:
            connection.execute(
                "UPDATE sandbox_leases SET status = ?, updated_at = ? WHERE run_id = ?",
                ("released", time.time(), run_id),
            )

    async def list_leases_for_run(self, run_id: str) -> List[SandboxLeaseRecord]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM sandbox_leases
                WHERE run_id = ?
                ORDER BY created_at ASC
                """,
                (run_id,),
            ).fetchall()
        return [_lease_from_row(row) for row in rows]

    async def record_event(self, event: SandboxEventRecord) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO sandbox_events (
                    lease_id, event_type, run_id, task_id, tool_call_id, tool_name,
                    status, duration_ms, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.lease_id,
                    event.event_type,
                    event.run_id,
                    event.task_id,
                    event.tool_call_id,
                    event.tool_name,
                    event.status,
                    event.duration_ms,
                    json_dumps(event.payload),
                    event.created_at,
                ),
            )

    async def list_events(self, lease_id: str) -> List[SandboxEventRecord]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM sandbox_events
                WHERE lease_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (lease_id,),
            ).fetchall()
        return [_event_from_row(row) for row in rows]

    async def list_events_for_run(self, run_id: str) -> List[SandboxEventRecord]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM sandbox_events
                WHERE run_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (run_id,),
            ).fetchall()
        return [_event_from_row(row) for row in rows]

    async def save_workspace_snapshot(self, snapshot: SandboxWorkspaceSnapshotRecord) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO sandbox_workspace_snapshots (
                    snapshot_id, lease_id, run_id, task_id, phase, file_count, total_bytes,
                    manifest_json, diff_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(snapshot_id) DO UPDATE SET
                    phase = excluded.phase,
                    file_count = excluded.file_count,
                    total_bytes = excluded.total_bytes,
                    manifest_json = excluded.manifest_json,
                    diff_json = excluded.diff_json,
                    created_at = excluded.created_at
                """,
                (
                    snapshot.snapshot_id,
                    snapshot.lease_id,
                    snapshot.run_id,
                    snapshot.task_id,
                    snapshot.phase,
                    snapshot.file_count,
                    snapshot.total_bytes,
                    json_dumps(snapshot.manifest),
                    json_dumps(snapshot.diff),
                    snapshot.created_at,
                ),
            )

    async def list_workspace_snapshots_for_run(self, run_id: str) -> List[SandboxWorkspaceSnapshotRecord]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM sandbox_workspace_snapshots
                WHERE run_id = ?
                ORDER BY created_at ASC, snapshot_id ASC
                """,
                (run_id,),
            ).fetchall()
        return [_snapshot_from_row(row) for row in rows]
