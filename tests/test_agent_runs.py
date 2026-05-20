import asyncio

from agents.kernel.specs import AgentSpec
from agents.kernel.state.runs import InMemoryRunStore, LocalFileRunStore, RunRecord, RunStatus
from agents.kernel.schema import RuntimeEvent


def test_in_memory_run_store_tracks_agent_scope_and_events():
    store = InMemoryRunStore()
    spec = AgentSpec.from_overrides(
        tenant_id="tenant 1",
        user_id="user 1",
        agent_id="agent 1",
        workspace_id="workspace 1",
    )

    async def execute():
        record = await store.create_run(spec, run_id="run-1")
        record = await store.append_event("run-1", RuntimeEvent(type="text_delta", payload={"delta": "ok"}))
        record = await store.set_status("run-1", RunStatus.FINISHED)
        loaded = await store.load_run("run-1")
        return record, loaded

    record, loaded = asyncio.run(execute())

    assert record.status == RunStatus.FINISHED
    assert loaded.agent_id == "agent 1"
    assert loaded.tenant_id == "tenant 1"
    assert loaded.user_id == "user 1"
    assert loaded.workspace_id == "workspace 1"
    assert loaded.events[0].payload["delta"] == "ok"


def test_run_record_serializes_stable_payload():
    record = RunRecord(
        run_id="run-1",
        status=RunStatus.RUNNING,
        events=[RuntimeEvent(type="text_delta", payload={"delta": "ok"})],
    )

    restored = RunRecord.from_dict(record.to_dict())

    assert restored.run_id == "run-1"
    assert restored.status == RunStatus.RUNNING
    assert restored.events[0].type == "text_delta"
    assert restored.events[0].payload == {"delta": "ok"}


def test_run_record_persists_redacted_agent_spec():
    spec = AgentSpec.from_overrides(
        protocol="openai-chat",
        model="gpt-test",
        api_key="secret",
        user_id="user-1",
        agent_id="agent-1",
        permission_profile="ask",
    )

    record = RunRecord.from_spec(spec)
    restored = RunRecord.from_dict(record.to_dict()).to_agent_spec()

    assert record.spec["model"]["protocol"] == "openai-chat"
    assert "api_key" not in record.spec["model"]
    assert restored.workspace.user_id == "user-1"
    assert restored.tool_permissions.mode == "ask"


def test_local_file_run_store_persists_records(tmp_path):
    store = LocalFileRunStore(tmp_path)
    spec = AgentSpec.from_overrides(agent_id="agent-1")

    async def execute():
        run = await store.create_run(spec, run_id="run-1")
        await store.append_event(run.run_id, RuntimeEvent(type="done", payload={"content": "ok"}))
        await store.set_status(run.run_id, RunStatus.FINISHED)
        return await LocalFileRunStore(tmp_path).load_run("run-1")

    loaded = asyncio.run(execute())

    assert loaded is not None
    assert loaded.status == RunStatus.FINISHED
    assert loaded.events[0].payload["content"] == "ok"


def test_run_stores_list_runs_with_scope_filters(tmp_path):
    memory_store = InMemoryRunStore()
    file_store = LocalFileRunStore(tmp_path)
    spec_a = AgentSpec.from_overrides(tenant_id="tenant-a", user_id="user-a", agent_id="agent-a")
    spec_b = AgentSpec.from_overrides(tenant_id="tenant-b", user_id="user-b", agent_id="agent-b")

    async def execute():
        await memory_store.create_run(spec_a, run_id="run-memory-a")
        await memory_store.create_run(spec_b, run_id="run-memory-b")
        await file_store.create_run(spec_a, run_id="run-file-a")
        await file_store.create_run(spec_b, run_id="run-file-b")
        await memory_store.update_metadata("run-memory-a", {"sdk_session_id": "session-a", "sdk_tag": "review"})
        await file_store.update_metadata("run-file-a", {"sdk_session_id": "session-a", "sdk_tag": "review"})
        memory_filtered = await memory_store.list_runs(tenant_id="tenant-a")
        file_filtered = await file_store.list_runs(user_id="user-a")
        memory_limited = await memory_store.list_runs(limit=1)
        file_limited = await file_store.list_runs(limit=1)
        memory_offset = await memory_store.list_runs(limit=1, offset=1)
        file_offset = await file_store.list_runs(limit=1, offset=1)
        return memory_filtered, file_filtered, memory_limited, file_limited, memory_offset, file_offset

    memory_filtered, file_filtered, memory_limited, file_limited, memory_offset, file_offset = asyncio.run(execute())

    assert [item.run_id for item in memory_filtered] == ["run-memory-a"]
    assert [item.run_id for item in file_filtered] == ["run-file-a"]
    assert memory_filtered[0].metadata["sdk_tag"] == "review"
    assert file_filtered[0].metadata["sdk_session_id"] == "session-a"
    assert len(memory_limited) == 1
    assert len(file_limited) == 1
    assert len(memory_offset) == 1
    assert len(file_offset) == 1
