from __future__ import annotations

from agents.kernel.specs import AgentSpec
from agents.kernel.capabilities.sandbox import InMemorySandboxStore, SandboxStore
from agents.kernel.state.runs import InMemoryRunStore, RunRecord, RunStatus, RunStore
from agents.kernel.schema import RuntimeEvent
from agents.kernel.governance.tracing import InMemoryTraceStore, RuntimeTraceRecorder
from agents.platform.sessions.file_history import (
    file_history_events_after_record,
    file_history_events_before_record,
)


class RunService:
    def __init__(
        self,
        store: RunStore | None = None,
        trace_recorder: RuntimeTraceRecorder | None = None,
        sandbox_store: SandboxStore | None = None,
    ):
        self.store = store or InMemoryRunStore()
        self.trace_recorder = trace_recorder or RuntimeTraceRecorder(InMemoryTraceStore())
        self.sandbox_store = sandbox_store or InMemorySandboxStore()

    async def start(self, spec: AgentSpec) -> RunRecord:
        record = await self.store.create_run(spec)
        record = await self.store.set_status(record.run_id, RunStatus.RUNNING) or record
        await self.trace_recorder.start_run(record)
        await self.record_event(record.run_id, run_created_event(record.run_id))
        return record

    async def record_event(self, run_id: str, event: RuntimeEvent) -> None:
        record = await self.store.load_run(run_id)
        for generated in file_history_events_before_record(record, event):
            await self._append_event(run_id, generated)
        await self.store.append_event(run_id, event)
        await self.trace_recorder.record_runtime_event(run_id, event)
        record = await self.store.load_run(run_id)
        for generated in file_history_events_after_record(record, event):
            await self._append_event(run_id, generated)

    async def record_events(self, run_id: str, events: list[RuntimeEvent]) -> None:
        for event in events:
            await self.record_event(run_id, event)

    async def _append_event(self, run_id: str, event: RuntimeEvent) -> None:
        await self.store.append_event(run_id, event)
        await self.trace_recorder.record_runtime_event(run_id, event)

    async def mark_running(self, run_id: str) -> None:
        await self.store.set_status(run_id, RunStatus.RUNNING)
        await self.trace_recorder.mark_run_running(run_id)

    async def pause_for_approval(self, run_id: str) -> None:
        await self.store.set_status(run_id, RunStatus.AWAITING_APPROVAL)
        await self.trace_recorder.mark_run_waiting(run_id)

    async def finish(self, run_id: str, error: str = "") -> None:
        status = RunStatus.ERROR if error else RunStatus.FINISHED
        await self.store.set_status(run_id, status)
        await self.sandbox_store.mark_released_for_run(run_id)
        await self.trace_recorder.finish_run(run_id, error=error)

    async def load_run(self, run_id: str) -> RunRecord | None:
        return await self.store.load_run(run_id)

    async def update_metadata(
        self,
        run_id: str,
        metadata: dict[str, str],
        *,
        replace_all: bool = False,
    ) -> RunRecord | None:
        return await self.store.update_metadata(run_id, metadata, replace_all=replace_all)

    async def list_runs(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        tenant_id: str = "",
        user_id: str = "",
        agent_id: str = "",
    ) -> list[RunRecord]:
        return await self.store.list_runs(
            limit=limit,
            offset=offset,
            tenant_id=tenant_id,
            user_id=user_id,
            agent_id=agent_id,
        )


def run_created_event(run_id: str) -> RuntimeEvent:
    return RuntimeEvent(type="run_created", name="run", payload={"run_id": run_id})
