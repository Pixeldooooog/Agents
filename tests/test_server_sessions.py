import asyncio
from dataclasses import replace
from pathlib import Path

from agents.kernel.context.workspace import WorkspaceContext
from agents.kernel.specs import AgentSpec
from agents.kernel.capabilities.sandbox import InMemorySandboxStore, SandboxLeaseRecord
from agents.kernel.state.identity import TenantRecord, UserRecord
from agents.kernel.capabilities.memory import MemoryRecord, MemoryScope
from agents.kernel.state.runs import RunStatus
from agents.kernel.runtime import RuntimeCheckpoint
from agents.kernel.schema import RuntimeEvent
from agents.kernel.governance import CredentialRef
from agents.kernel.hooks import SessionHookRegistry
from agents.kernel.mcp_config import MCPServerRecord
from agents.kernel.session_state import SessionStateRecord
from agents.kernel.state import AgentProfile
from agents.kernel.state.workspaces import WorkspaceRecord
from agents.kernel.teams import TeamRecord
from agents.kernel.governance.tracing import InMemoryTraceStore, RuntimeTraceRecorder, TraceStatus
from agents.platform import create_durable_persistence, create_ephemeral_persistence, create_platform_persistence, create_terminal_persistence
from agents.platform.sessions import RunService, create_checkpoint_store, create_run_store


def test_server_run_service_records_lifecycle_events():
    service = RunService()
    spec = AgentSpec.from_overrides(agent_id="agent-1", user_id="user-1")

    async def execute():
        run = await service.start(spec)
        await service.record_event(run.run_id, RuntimeEvent(type="text_delta", payload={"delta": "ok"}))
        await service.finish(run.run_id)
        return await service.store.load_run(run.run_id)

    record = asyncio.run(execute())

    assert record.status == RunStatus.FINISHED
    assert [event.type for event in record.events] == ["run_created", "text_delta"]
    assert record.events[0].payload["run_id"] == record.run_id


def test_server_run_service_records_non_sdk_file_history_snapshots(tmp_path):
    service = RunService()
    spec = replace(
        AgentSpec.from_overrides(agent_id="agent-1", workspace_path=str(tmp_path)),
        metadata={"claude_config_dir": str(tmp_path / ".claude")},
    )

    async def execute():
        run = await service.start(spec)
        await service.record_event(
            run.run_id,
            RuntimeEvent(
                type="file_history_write",
                name="filesystem.write",
                payload={
                    "path": "notes.md",
                    "operation": "update",
                    "tool_name": "Write",
                    "canonical_tool": "filesystem.write",
                    "checkpoint_pending": True,
                },
            ),
        )
        await service.record_event(
            run.run_id,
            RuntimeEvent(
                type="tool_result",
                name="Write",
                payload={
                    "tool_call_id": "call-1",
                    "raw": {
                        "filePath": "notes.md",
                        "type": "update",
                        "originalFile": "old content\n",
                        "content": "new content\n",
                    },
                },
            ),
        )
        return await service.store.load_run(run.run_id)

    record = asyncio.run(execute())
    snapshots = [event for event in record.events if event.type == "file-history-snapshot"]

    assert [event.payload["isSnapshotUpdate"] for event in snapshots] == [False, True]
    assert snapshots[0].payload["messageId"] == record.run_id
    tracked = snapshots[-1].payload["snapshot"]["trackedFileBackups"]
    backup = tracked["notes.md"]
    assert backup["backupFileName"]
    backup_path = Path(snapshots[-1].payload["backupRoot"]) / backup["backupFileName"]
    assert backup_path.read_text(encoding="utf-8") == "old content\n"


def test_server_run_service_skips_sdk_file_history_snapshots(tmp_path):
    service = RunService()
    spec = replace(
        AgentSpec.from_overrides(agent_id="agent-1", workspace_path=str(tmp_path)),
        metadata={"sdk_session_id": "sdk-session", "claude_config_dir": str(tmp_path / ".claude")},
    )

    async def execute():
        run = await service.start(spec)
        await service.record_event(
            run.run_id,
            RuntimeEvent(
                type="tool_result",
                name="Write",
                payload={
                    "tool_call_id": "call-1",
                    "raw": {"filePath": "notes.md", "type": "update", "originalFile": "old"},
                },
            ),
        )
        return await service.store.load_run(run.run_id)

    record = asyncio.run(execute())

    assert [event.type for event in record.events] == ["run_created", "tool_result"]


def test_server_run_service_marks_error_status():
    service = RunService()
    spec = AgentSpec.from_overrides(agent_id="agent-1")

    async def execute():
        run = await service.start(spec)
        await service.finish(run.run_id, "broken")
        return await service.store.load_run(run.run_id)

    record = asyncio.run(execute())

    assert record.status == RunStatus.ERROR


def test_server_run_service_releases_sandbox_leases_on_finish():
    sandbox_store = InMemorySandboxStore()
    service = RunService(sandbox_store=sandbox_store)
    spec = AgentSpec.from_overrides(agent_id="agent-1")

    async def execute():
        run = await service.start(spec)
        await sandbox_store.save_lease(
            SandboxLeaseRecord(
                lease_id="sandbox-%s" % run.run_id,
                provider="local",
                tenant_id=run.tenant_id,
                user_id=run.user_id,
                agent_id=run.agent_id,
                workspace_id=run.workspace_id,
                run_id=run.run_id,
            )
        )
        await service.finish(run.run_id)
        leases = await sandbox_store.list_leases_for_run(run.run_id)
        return leases

    leases = asyncio.run(execute())

    assert leases[0].status == "released"


def test_server_run_service_marks_approval_status():
    service = RunService()
    spec = AgentSpec.from_overrides(agent_id="agent-1")

    async def execute():
        run = await service.start(spec)
        await service.pause_for_approval(run.run_id)
        return await service.store.load_run(run.run_id)

    record = asyncio.run(execute())

    assert record.status == RunStatus.AWAITING_APPROVAL


def test_server_run_service_records_trace_spans():
    trace_store = InMemoryTraceStore()
    service = RunService(trace_recorder=RuntimeTraceRecorder(trace_store))
    spec = AgentSpec.from_overrides(agent_id="agent-1", user_id="user-1")

    async def execute():
        run = await service.start(spec)
        await service.record_event(
            run.run_id,
            RuntimeEvent(
                type="tool_start",
                name="echo",
                payload={"id": "call-1", "name": "echo", "arguments": {"text": "hi"}},
            ),
        )
        await service.record_event(
            run.run_id,
            RuntimeEvent(
                type="tool_result",
                name="echo",
                payload={
                    "tool_call_id": "call-1",
                    "content": "ok",
                    "is_error": False,
                    "raw": {"_meta": {"sandbox": {"lease_id": "sandbox_run-1", "provider": "local"}}},
                },
            ),
        )
        await service.finish(run.run_id)
        return run.run_id, await trace_store.list_for_run(run.run_id)

    run_id, spans = asyncio.run(execute())
    by_id = {span.span_id: span for span in spans}

    assert by_id[f"{run_id}:run"].status == TraceStatus.DONE
    assert by_id[f"{run_id}:run"].ended_at is not None
    assert by_id[f"{run_id}:tool:call-1"].status == TraceStatus.DONE
    assert by_id[f"{run_id}:tool:call-1"].attributes["tool_result"]["content"] == "ok"
    assert by_id[f"{run_id}:tool:call-1"].attributes["sandbox"]["lease_id"] == "sandbox_run-1"


def test_server_run_service_records_approval_trace_state():
    trace_store = InMemoryTraceStore()
    service = RunService(trace_recorder=RuntimeTraceRecorder(trace_store))
    spec = AgentSpec.from_overrides(agent_id="agent-1")

    async def execute():
        run = await service.start(spec)
        await service.record_event(
            run.run_id,
            RuntimeEvent(type="tool_approval_required", name="echo", payload={"approval_id": "call-1"}),
        )
        await service.pause_for_approval(run.run_id)
        waiting_root = await trace_store.load_span(f"{run.run_id}:run")
        await service.mark_running(run.run_id)
        await service.record_event(
            run.run_id,
            RuntimeEvent(
                type="tool_approval_decision",
                name="echo",
                payload={"approval_id": "call-1", "approved": False},
            ),
        )
        await service.finish(run.run_id)
        return run.run_id, waiting_root, await trace_store.list_for_run(run.run_id)

    run_id, waiting_root, spans = asyncio.run(execute())
    by_id = {span.span_id: span for span in spans}

    assert waiting_root.status == TraceStatus.WAITING
    assert waiting_root.ended_at is None
    assert by_id[f"{run_id}:run"].status == TraceStatus.DONE
    assert by_id[f"{run_id}:approval:call-1"].status == TraceStatus.CANCELED


def test_server_run_store_factory_uses_file_store(tmp_path):
    class AgentConfig:
        RUN_STORE = "file"
        RUN_ROOT = "runs"

    class ServerConfig:
        ROOT_PATH = tmp_path

    class Settings:
        agent = AgentConfig()
        server = ServerConfig()

    store = create_run_store(Settings())
    spec = AgentSpec.from_overrides(agent_id="agent-1")

    async def execute():
        run = await store.create_run(spec, run_id="run-1")
        return await store.load_run(run.run_id)

    record = asyncio.run(execute())

    assert record.run_id == "run-1"
    assert (tmp_path / "runs" / "run-1.json").exists()


def test_server_store_factory_uses_sqlite(tmp_path):
    class AgentConfig:
        RUN_STORE = "sqlite"
        DB_PATH = "agents.db"

    class ServerConfig:
        ROOT_PATH = tmp_path

    class Settings:
        agent = AgentConfig()
        server = ServerConfig()

    run_store = create_run_store(Settings())
    checkpoint_store = create_checkpoint_store(Settings())
    spec = AgentSpec.from_overrides(agent_id="agent-1")

    async def execute():
        run = await run_store.create_run(spec, run_id="run-1")
        await checkpoint_store.save(
            RuntimeCheckpoint(
                run_id=run.run_id,
                step="finished",
                iteration=0,
                messages=[],
            )
        )
        return await run_store.load_run(run.run_id), await checkpoint_store.load(run.run_id)

    record, checkpoint = asyncio.run(execute())

    assert record.run_id == "run-1"
    assert checkpoint.step == "finished"
    assert (tmp_path / "agents.db").exists()


def test_server_persistence_container_uses_sqlite_stores(tmp_path):
    class AgentConfig:
        RUN_STORE = "sqlite"
        DB_PATH = "agents.db"

    class ServerConfig:
        ROOT_PATH = tmp_path

    class Settings:
        agent = AgentConfig()
        server = ServerConfig()

    persistence = create_platform_persistence(Settings())

    async def execute():
        await persistence.identities.save_tenant(TenantRecord(tenant_id="tenant-1"))
        await persistence.identities.save_user(UserRecord(tenant_id="tenant-1", user_id="user-1"))
        spec = AgentSpec.from_overrides(tenant_id="tenant-1", user_id="user-1", agent_id="agent-1")
        await persistence.agent_profiles.save(AgentProfile.from_spec(spec, name="Agent"))
        await persistence.workspaces.save(
            WorkspaceRecord(
                tenant_id="tenant-1",
                user_id="user-1",
                agent_id="agent-1",
                workspace_id="workspace-1",
                path=str(tmp_path / "workspaces" / "workspace-1"),
            )
        )
        memory = MemoryRecord.create(
            tenant_id="tenant-1",
            user_id="user-1",
            agent_id="agent-1",
            scope=MemoryScope.AGENT,
            content="remember this",
        )
        credential = CredentialRef.create(
            tenant_id="tenant-1",
            user_id="user-1",
            agent_id="agent-1",
            provider="openai",
            name="default",
            secret_ref="vault://secret",
        )
        await persistence.memories.save(memory)
        await persistence.credentials.save(credential)
        task = await persistence.tasks.create_task(spec, title="Task", input="Do work")
        await persistence.task_queue.enqueue(
            task.task_id,
            metadata={"source": "server"},
            tenant_id="tenant-1",
            user_id="user-1",
            agent_id="agent-1",
        )
        await persistence.teams.save_team(
            TeamRecord.create(
                spec=spec,
                team_id="feature",
                name="Feature Team",
                members={"researcher": {"agent_id": "researcher", "role": "research"}},
            )
        )
        hook = SessionHookRegistry().add(event="pre_tool_use", name="block-shell", action="deny_tool", tool="shell.run")
        await persistence.hooks.save(hook, "tenant-1", user_id="user-1", agent_id="agent-1")
        await persistence.mcp_configs.save(
            MCPServerRecord(name="docs", command="python server.py", tenant_id="tenant-1", user_id="user-1", agent_id="agent-1")
        )
        await persistence.session_states.save(
            SessionStateRecord(
                tenant_id="tenant-1",
                user_id="user-1",
                agent_id="agent-1",
                workspace_id="workspace-1",
                todos=[{"content": "Run checks", "status": "pending", "activeForm": "Running checks"}],
            )
        )
        return (
            await persistence.identities.load_user("tenant-1", "user-1"),
            await persistence.agent_profiles.load("tenant-1", "user-1", "agent-1"),
            await persistence.workspaces.load("tenant-1", "user-1", "agent-1", "workspace-1"),
            await persistence.memories.list_for_context("tenant-1", "user-1", "agent-1"),
            await persistence.credentials.list_for_scope("tenant-1", "user-1", "agent-1"),
            await persistence.tasks.load_task(task.task_id),
            await persistence.task_queue.items(tenant_id="tenant-1", user_id="user-1", agent_id="agent-1"),
            await persistence.teams.load_team("feature", "tenant-1", user_id="user-1", agent_id="agent-1", workspace_id=""),
            await persistence.hooks.list_for_scope("tenant-1", user_id="user-1", agent_id="agent-1"),
            await persistence.mcp_configs.list_for_scope("tenant-1", user_id="user-1", agent_id="agent-1"),
            await persistence.session_states.load_for_scope("tenant-1", user_id="user-1", agent_id="agent-1", workspace_id="workspace-1"),
        )

    user, profile, workspace, memories, credentials, task, task_queue, team, hooks, mcp_servers, session_state = asyncio.run(execute())

    assert user.user_id == "user-1"
    assert profile.name == "Agent"
    assert workspace.workspace_id == "workspace-1"
    assert memories[0].content == "remember this"
    assert credentials[0].secret_ref == "vault://secret"
    assert task.title == "Task"
    assert task_queue[0].metadata["source"] == "server"
    assert team.name == "Feature Team"
    assert hooks[0].metadata["tool"] == "shell.run"
    assert mcp_servers[0].command == "python server.py"
    assert session_state.todos[0]["content"] == "Run checks"


def test_persistence_profiles_split_terminal_and_server_storage(tmp_path):
    class AgentConfig:
        RUN_STORE = "sqlite"
        DB_PATH = "agents.db"

    class ServerConfig:
        ROOT_PATH = tmp_path

    class Settings:
        agent = AgentConfig()
        server = ServerConfig()

    workspace_path = tmp_path / "repo"
    workspace_path.mkdir()
    workspace = WorkspaceContext(
        tenant_id="tenant-1",
        user_id="user-1",
        agent_id="agent-1",
        workspace_id="workspace-1",
        root=tmp_path,
        path=workspace_path,
    )

    terminal = create_ephemeral_persistence(Settings(), workspace_path=str(workspace_path))
    terminal_durable = create_terminal_persistence(Settings(), workspace_path=str(workspace_path))
    server = create_durable_persistence(Settings())

    terminal_root = terminal.artifact_blobs.run_artifact_root(workspace, "run-1")
    server_root = server.artifact_blobs.run_artifact_root(workspace, "run-1")

    assert terminal.runs.__class__.__name__ == "InMemoryRunStore"
    assert terminal.artifacts.__class__.__name__ == "InMemoryArtifactStore"
    assert terminal_root.as_posix().endswith("/runs/run-1/artifacts")
    assert ".agents/projects/" in terminal_root.as_posix()

    assert terminal_durable.runs.__class__.__name__ == "SQLiteRunStore"
    assert terminal_durable.memories.__class__.__name__ == "SQLiteMemoryStore"
    assert terminal_durable.session_states.__class__.__name__ == "SQLiteSessionStateStore"
    assert terminal_durable.task_queue.__class__.__name__ == "SQLiteTaskQueue"
    assert terminal_durable.artifact_blobs.run_artifact_root(workspace, "run-1").as_posix().endswith("/runs/run-1/artifacts")
    assert ".agents/projects/" in terminal_durable.artifact_blobs.run_artifact_root(workspace, "run-1").as_posix()

    assert server.runs.__class__.__name__ == "SQLiteRunStore"
    assert server.artifacts.__class__.__name__ == "SQLiteArtifactStore"
    assert server_root == tmp_path / ".agents" / "server" / "artifacts" / "tenant-1" / "user-1" / "agent-1" / "workspace-1" / "runs" / "run-1" / "artifacts"
