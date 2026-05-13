import asyncio

from agents.kernel.specs import AgentSpec
from agents.kernel.governance.audit import ApprovalAuditRecord, SQLiteApprovalAuditStore
from agents.kernel.hooks import SQLiteHookStore, SessionHookRegistry
from agents.kernel.mcp_config import MCPServerRecord, SQLiteMCPConfigStore
from agents.kernel.session_state import SessionStateRecord, SQLiteSessionStateStore
from agents.kernel.state.identity import SQLiteIdentityStore, TenantRecord, UserRecord
from agents.kernel.capabilities.memory import MemoryRecord, MemoryScope, SQLiteMemoryStore
from agents.kernel.persistence import SQLiteDatabase
from agents.kernel.state.runs import RunStatus, SQLiteRunStore
from agents.kernel.runtime import RuntimeCheckpoint, SQLiteCheckpointStore
from agents.kernel.schema import Message, RuntimeEvent, ToolCall
from agents.kernel.governance import CredentialRef, SQLiteCredentialRefStore
from agents.kernel.governance.approval_grants import APPROVAL_ALLOW_FOR_RUN, approval_grant_key
from agents.kernel.state import AgentProfile, SQLiteAgentProfileStore
from agents.kernel.state.workspaces import SQLiteWorkspaceStore, WorkspaceRecord
from agents.kernel.governance.tracing import SQLiteTraceStore, TraceSpan, TraceStatus
from agents.kernel.teams import SQLiteTeamStore, TeamMessageRecord, TeamRecord


def test_sqlite_run_store_persists_records_and_events(tmp_path):
    store = SQLiteRunStore(SQLiteDatabase(tmp_path / "agents.db"))
    spec = AgentSpec.from_overrides(agent_id="agent-1", user_id="user-1", permission_profile="ask")

    async def execute():
        run = await store.create_run(spec, run_id="run-1")
        await store.append_event(
            run.run_id,
            RuntimeEvent(type="tool_approval_required", name="echo", payload={"approval_id": "call-1"}),
        )
        await store.set_status(run.run_id, RunStatus.AWAITING_APPROVAL)
        return await SQLiteRunStore(SQLiteDatabase(tmp_path / "agents.db")).load_run("run-1")

    record = asyncio.run(execute())

    assert record.status == RunStatus.AWAITING_APPROVAL
    assert record.user_id == "user-1"
    assert record.events[0].type == "tool_approval_required"
    assert record.to_agent_spec().tool_permissions.mode == "ask"


def test_sqlite_run_store_lists_scoped_runs(tmp_path):
    store = SQLiteRunStore(SQLiteDatabase(tmp_path / "agents.db"))
    first = AgentSpec.from_overrides(tenant_id="tenant-1", user_id="user-1", agent_id="agent-1")
    second = AgentSpec.from_overrides(tenant_id="tenant-2", user_id="user-2", agent_id="agent-2")

    async def execute():
        await store.create_run(first, run_id="run-1")
        await store.create_run(second, run_id="run-2")
        await store.set_status("run-1", RunStatus.FINISHED)
        await store.set_status("run-2", RunStatus.ERROR)
        by_tenant = await store.list_runs(tenant_id="tenant-1")
        limited = await store.list_runs(limit=1)
        return by_tenant, limited

    by_tenant, limited = asyncio.run(execute())

    assert [run.run_id for run in by_tenant] == ["run-1"]
    assert len(limited) == 1


def test_sqlite_checkpoint_store_persists_pending_tools(tmp_path):
    call = ToolCall(id="call-1", name="echo", arguments={"text": "hi"})
    store = SQLiteCheckpointStore(SQLiteDatabase(tmp_path / "agents.db"))

    async def execute():
        await store.save(
            RuntimeCheckpoint(
                run_id="run-1",
                step="approval_required",
                iteration=2,
                messages=[Message.from_text("assistant", "", tool_calls=[call])],
                events=[
                    RuntimeEvent(
                        type="tool_approval_required",
                        name="echo",
                        payload={"approval_id": "call-1"},
                    )
                ],
                pending_tool_calls=[call],
                tool_approvals={"call-1": True},
                tool_approval_scopes={"call-1": APPROVAL_ALLOW_FOR_RUN},
                tool_approval_grants={approval_grant_key(call): True},
            )
        )
        return await SQLiteCheckpointStore(SQLiteDatabase(tmp_path / "agents.db")).load("run-1")

    checkpoint = asyncio.run(execute())

    assert checkpoint.step == "approval_required"
    assert checkpoint.iteration == 2
    assert checkpoint.pending_tool_calls[0].name == "echo"
    assert checkpoint.tool_approvals == {"call-1": True}
    assert checkpoint.tool_approval_scopes == {"call-1": "allow_for_run"}
    assert checkpoint.tool_approval_grants == {approval_grant_key(call): True}


def test_sqlite_team_store_persists_team_members_and_messages(tmp_path):
    database = SQLiteDatabase(tmp_path / "agents.db")
    store = SQLiteTeamStore(database)
    spec = AgentSpec.from_overrides(
        tenant_id="tenant-1",
        user_id="user-1",
        agent_id="lead",
        workspace_id="workspace-1",
    )

    async def execute():
        team = TeamRecord.create(
            spec=spec,
            team_id="feature",
            name="Feature Team",
            members={"researcher": {"agent_id": "researcher", "role": "research"}},
        )
        other_team = TeamRecord.create(
            spec=AgentSpec.from_overrides(
                tenant_id="tenant-1",
                user_id="user-1",
                agent_id="lead",
                workspace_id="workspace-2",
            ),
            team_id="feature",
            name="Other Workspace Team",
        )
        message = TeamMessageRecord.create(
            spec=spec,
            team_id=team.team_id,
            from_agent="lead",
            to_agent="researcher",
            message="Check the repo.",
        )
        await store.save_team(team)
        await store.save_team(other_team)
        await store.add_message(message)
        reopened = SQLiteTeamStore(SQLiteDatabase(tmp_path / "agents.db"))
        loaded = await reopened.load_team("feature", "tenant-1", user_id="user-1", agent_id="lead", workspace_id="workspace-1")
        other_loaded = await reopened.load_team("feature", "tenant-1", user_id="user-1", agent_id="lead", workspace_id="workspace-2")
        inbox = await reopened.list_messages(
            "tenant-1",
            user_id="user-1",
            agent_id="lead",
            workspace_id="workspace-1",
            team_id="feature",
            to_agent="researcher",
        )
        await reopened.mark_messages_read([inbox[0].message_id])
        read_inbox = await reopened.list_messages(
            "tenant-1",
            user_id="user-1",
            agent_id="lead",
            workspace_id="workspace-1",
            team_id="feature",
            to_agent="researcher",
        )
        return loaded, other_loaded, inbox, read_inbox

    team, other_team, inbox, read_inbox = asyncio.run(execute())

    assert team is not None
    assert other_team is not None
    assert team.members["researcher"]["role"] == "research"
    assert other_team.name == "Other Workspace Team"
    assert inbox[0].message == "Check the repo."
    assert read_inbox == []


def test_sqlite_hook_store_persists_scoped_hooks(tmp_path):
    database = SQLiteDatabase(tmp_path / "agents.db")
    store = SQLiteHookStore(database)
    registry = SessionHookRegistry()
    hook = registry.add(event="pre_tool_use", name="block-shell", action="deny_tool", tool="shell.run", content="blocked")
    registry.mark_ran(hook)

    async def execute():
        await store.save(hook, "tenant-1", user_id="user-1", agent_id="agent-1", workspace_id="workspace-1")
        reopened = SQLiteHookStore(SQLiteDatabase(tmp_path / "agents.db"))
        hooks = await reopened.list_for_scope("tenant-1", user_id="user-1", agent_id="agent-1", workspace_id="workspace-1")
        await reopened.delete(hook.hook_id, "tenant-1", user_id="user-1", agent_id="agent-1", workspace_id="workspace-1")
        after_delete = await reopened.list_for_scope("tenant-1", user_id="user-1", agent_id="agent-1", workspace_id="workspace-1")
        return hooks, after_delete

    hooks, after_delete = asyncio.run(execute())

    assert hooks[0].hook_id == hook.hook_id
    assert hooks[0].metadata["tool"] == "shell.run"
    assert hooks[0].run_count == 1
    assert after_delete == []


def test_sqlite_mcp_config_store_persists_scoped_servers(tmp_path):
    database = SQLiteDatabase(tmp_path / "agents.db")
    store = SQLiteMCPConfigStore(database)
    server = MCPServerRecord(
        name="docs",
        command="python server.py",
        tenant_id="tenant-1",
        user_id="user-1",
        agent_id="agent-1",
        workspace_id="workspace-1",
    )
    other = MCPServerRecord(
        name="docs",
        command="python other.py",
        tenant_id="tenant-1",
        user_id="user-1",
        agent_id="agent-1",
        workspace_id="workspace-2",
    )

    async def execute():
        await store.save(server)
        await store.save(other)
        reopened = SQLiteMCPConfigStore(SQLiteDatabase(tmp_path / "agents.db"))
        servers = await reopened.list_for_scope("tenant-1", user_id="user-1", agent_id="agent-1", workspace_id="workspace-1")
        other_servers = await reopened.list_for_scope("tenant-1", user_id="user-1", agent_id="agent-1", workspace_id="workspace-2")
        await reopened.delete("docs", "tenant-1", user_id="user-1", agent_id="agent-1", workspace_id="workspace-1")
        after_delete = await reopened.list_for_scope("tenant-1", user_id="user-1", agent_id="agent-1", workspace_id="workspace-1")
        return servers, other_servers, after_delete

    servers, other_servers, after_delete = asyncio.run(execute())

    assert servers[0].command == "python server.py"
    assert other_servers[0].command == "python other.py"
    assert after_delete == []


def test_sqlite_session_state_store_persists_scoped_planning_state(tmp_path):
    database = SQLiteDatabase(tmp_path / "agents.db")
    store = SQLiteSessionStateStore(database)
    record = SessionStateRecord(
        tenant_id="tenant-1",
        user_id="user-1",
        agent_id="agent-1",
        workspace_id="workspace-1",
        todos=[{"content": "Run checks", "status": "pending", "activeForm": "Running checks"}],
        plan_mode=True,
        plan_text="Inspect then implement.",
        plan_allowed_prompts=[{"tool": "shell.run", "prompt": "pytest"}],
        system_prompt_override="Persisted prompt.",
        system_prompt_overridden=True,
        permission_profile_override="guarded",
        permission_mode_override="auto",
        permission_restrict_allowed_tools=True,
        permission_allowed_tools_override=["filesystem.read"],
        permission_denied_tools_override=["shell.run"],
        approval_required_tools_override=["shell.run"],
        permission_overridden=True,
        enabled_skills=["focus"],
        enabled_plugins=["planner"],
        skill_tools={"focus": ["filesystem.read"]},
        plugin_tools={"planner": ["todo.write"]},
    )
    other = SessionStateRecord(
        tenant_id="tenant-1",
        user_id="user-1",
        agent_id="agent-1",
        workspace_id="workspace-2",
        todos=[{"content": "Review output", "status": "pending", "activeForm": "Reviewing output"}],
    )

    async def execute():
        await store.save(record)
        await store.save(other)
        reopened = SQLiteSessionStateStore(SQLiteDatabase(tmp_path / "agents.db"))
        loaded = await reopened.load_for_scope("tenant-1", user_id="user-1", agent_id="agent-1", workspace_id="workspace-1")
        other_loaded = await reopened.load_for_scope("tenant-1", user_id="user-1", agent_id="agent-1", workspace_id="workspace-2")
        await reopened.delete("tenant-1", user_id="user-1", agent_id="agent-1", workspace_id="workspace-1")
        after_delete = await reopened.load_for_scope("tenant-1", user_id="user-1", agent_id="agent-1", workspace_id="workspace-1")
        return loaded, other_loaded, after_delete

    loaded, other_loaded, after_delete = asyncio.run(execute())

    assert loaded is not None
    assert loaded.todos[0]["content"] == "Run checks"
    assert loaded.plan_mode is True
    assert loaded.plan_allowed_prompts == [{"tool": "shell.run", "prompt": "pytest"}]
    assert loaded.system_prompt_override == "Persisted prompt."
    assert loaded.system_prompt_overridden is True
    assert loaded.permission_profile_override == "guarded"
    assert loaded.permission_mode_override == "auto"
    assert loaded.permission_restrict_allowed_tools is True
    assert loaded.permission_allowed_tools_override == ["filesystem.read"]
    assert loaded.permission_denied_tools_override == ["shell.run"]
    assert loaded.approval_required_tools_override == ["shell.run"]
    assert loaded.permission_overridden is True
    assert loaded.enabled_skills == ["focus"]
    assert loaded.enabled_plugins == ["planner"]
    assert loaded.skill_tools == {"focus": ["filesystem.read"]}
    assert loaded.plugin_tools == {"planner": ["todo.write"]}
    assert other_loaded is not None
    assert other_loaded.todos[0]["content"] == "Review output"
    assert after_delete is None


def test_sqlite_approval_audit_store_records_decisions(tmp_path):
    database = SQLiteDatabase(tmp_path / "agents.db")
    run_store = SQLiteRunStore(database)
    store = SQLiteApprovalAuditStore(database)
    call = ToolCall(id="call-1", name="echo", arguments={"text": "hi"})

    async def execute():
        await run_store.create_run(AgentSpec.from_overrides(agent_id="agent-1"), run_id="run-1")
        await store.record(
            ApprovalAuditRecord.from_tool_call(
                run_id="run-1",
                call=call,
                approved=False,
                decision="deny",
                reason="not needed",
            )
        )
        return await SQLiteApprovalAuditStore(SQLiteDatabase(tmp_path / "agents.db")).list_for_run("run-1")

    records = asyncio.run(execute())

    assert len(records) == 1
    assert records[0].approval_id == "call-1"
    assert records[0].approved is False
    assert records[0].decision == "deny"
    assert records[0].tool_call["arguments"] == {"text": "hi"}
    assert records[0].impact["tool_name"] == "echo"


def test_sqlite_trace_store_persists_run_spans(tmp_path):
    database = SQLiteDatabase(tmp_path / "agents.db")
    run_store = SQLiteRunStore(database)
    store = SQLiteTraceStore(database)

    async def execute():
        await run_store.create_run(AgentSpec.from_overrides(agent_id="agent-1"), run_id="run-1")
        span = TraceSpan.start(
            run_id="run-1",
            span_id="span-1",
            kind="tool",
            name="echo",
            parent_span_id="run-1:run",
            attributes={"tool_call": {"id": "call-1"}},
        )
        await store.save_span(span)
        await store.save_span(
            span.finish(TraceStatus.DONE, attributes={"tool_result": {"content": "ok"}})
        )
        return await SQLiteTraceStore(SQLiteDatabase(tmp_path / "agents.db")).list_for_run("run-1")

    spans = asyncio.run(execute())

    assert len(spans) == 1
    assert spans[0].span_id == "span-1"
    assert spans[0].status == TraceStatus.DONE
    assert spans[0].ended_at is not None
    assert spans[0].attributes["tool_call"] == {"id": "call-1"}
    assert spans[0].attributes["tool_result"] == {"content": "ok"}


def test_sqlite_identity_store_persists_tenants_and_users(tmp_path):
    database = SQLiteDatabase(tmp_path / "agents.db")
    store = SQLiteIdentityStore(database)

    async def execute():
        await store.save_tenant(TenantRecord(tenant_id="tenant-1", display_name="Tenant"))
        await store.save_user(
            UserRecord(
                tenant_id="tenant-1",
                user_id="user-1",
                display_name="User",
                roles=["admin"],
                metadata={"source": "test"},
            )
        )
        reopened = SQLiteIdentityStore(SQLiteDatabase(tmp_path / "agents.db"))
        return await reopened.load_tenant("tenant-1"), await reopened.list_users("tenant-1")

    tenant, users = asyncio.run(execute())

    assert tenant.display_name == "Tenant"
    assert users[0].user_id == "user-1"
    assert users[0].roles == ["admin"]
    assert users[0].metadata == {"source": "test"}


def test_sqlite_agent_profile_store_persists_redacted_specs(tmp_path):
    database = SQLiteDatabase(tmp_path / "agents.db")
    store = SQLiteAgentProfileStore(database)
    spec = AgentSpec.from_overrides(
        tenant_id="tenant-1",
        user_id="user-1",
        agent_id="agent-1",
        protocol="openai-chat",
        api_key="secret",
        permission_profile="ask",
    )

    async def execute():
        await store.save(AgentProfile.from_spec(spec, name="Researcher"))
        reopened = SQLiteAgentProfileStore(SQLiteDatabase(tmp_path / "agents.db"))
        return await reopened.load("tenant-1", "user-1", "agent-1")

    profile = asyncio.run(execute())

    assert profile.name == "Researcher"
    assert profile.spec["model"]["protocol"] == "openai-chat"
    assert "api_key" not in profile.spec["model"]
    assert profile.to_agent_spec().tool_permissions.mode == "ask"


def test_sqlite_workspace_memory_and_credential_refs_persist(tmp_path):
    database = SQLiteDatabase(tmp_path / "agents.db")
    workspace_store = SQLiteWorkspaceStore(database)
    memory_store = SQLiteMemoryStore(database)
    credential_store = SQLiteCredentialRefStore(database)

    async def execute():
        await workspace_store.save(
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
            workspace_id="workspace-1",
            scope=MemoryScope.WORKSPACE,
            content="User prefers concise answers.",
        )
        credential = CredentialRef.create(
            tenant_id="tenant-1",
            user_id="user-1",
            agent_id="agent-1",
            provider="openai",
            name="default",
            secret_ref="vault://tenant-1/openai/default",
        )
        await memory_store.save(memory)
        await credential_store.save(credential)

        reopened_database = SQLiteDatabase(tmp_path / "agents.db")
        return (
            await SQLiteWorkspaceStore(reopened_database).load("tenant-1", "user-1", "agent-1", "workspace-1"),
            await SQLiteMemoryStore(reopened_database).list_for_context("tenant-1", "user-1", "agent-1", "workspace-1"),
            await SQLiteCredentialRefStore(reopened_database).list_for_scope("tenant-1", "user-1", "agent-1"),
        )

    workspace, memories, credentials = asyncio.run(execute())

    assert workspace.workspace_id == "workspace-1"
    assert memories[0].content == "User prefers concise answers."
    assert memories[0].scope == MemoryScope.WORKSPACE
    assert credentials[0].secret_ref == "vault://tenant-1/openai/default"
