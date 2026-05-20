from __future__ import annotations

from typing import Dict, Optional

from agents.kernel.specs import AgentSpec
from agents.kernel.state.runs.types import RunRecord, RunStatus
from agents.kernel.schema import RuntimeEvent


class InMemoryRunStore:
    def __init__(self):
        self._runs: Dict[str, RunRecord] = {}

    async def create_run(self, spec: AgentSpec, run_id: str = "") -> RunRecord:
        record = RunRecord.from_spec(spec, run_id=run_id)
        self._runs[record.run_id] = record
        return record

    async def load_run(self, run_id: str) -> Optional[RunRecord]:
        return self._runs.get(run_id)

    async def append_event(self, run_id: str, event: RuntimeEvent) -> Optional[RunRecord]:
        record = self._runs.get(run_id)
        if record is None:
            return None
        updated = record.with_event(event)
        self._runs[run_id] = updated
        return updated

    async def set_status(self, run_id: str, status: RunStatus) -> Optional[RunRecord]:
        record = self._runs.get(run_id)
        if record is None:
            return None
        updated = record.with_status(status)
        self._runs[run_id] = updated
        return updated

    async def update_metadata(self, run_id: str, metadata: dict[str, str], *, replace_all: bool = False) -> Optional[RunRecord]:
        record = self._runs.get(run_id)
        if record is None:
            return None
        updated = record.with_metadata(metadata, replace_all=replace_all)
        self._runs[run_id] = updated
        return updated

    async def list_runs(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        tenant_id: str = "",
        user_id: str = "",
        agent_id: str = "",
    ) -> list[RunRecord]:
        records = list(self._runs.values())
        if tenant_id:
            records = [record for record in records if record.tenant_id == tenant_id]
        if user_id:
            records = [record for record in records if record.user_id == user_id]
        if agent_id:
            records = [record for record in records if record.agent_id == agent_id]
        records.sort(key=lambda item: item.updated_at, reverse=True)
        start = max(0, offset)
        return records[start : start + max(1, min(limit, 200))]
