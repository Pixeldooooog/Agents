import asyncio
import subprocess
from pathlib import Path
from types import SimpleNamespace

from agents.interfaces.bridge.active import active_task_running
from agents.interfaces.bridge import ndjson
from agents.interfaces.bridge.sessions import TerminalSessionStore
from agents.interfaces.bridge.slash import handle_slash_command
from agents.kernel.capabilities.memory import InMemoryMemoryStore, MemoryRecord, MemoryScope
from agents.kernel.capabilities.sandbox.local import LocalSandboxProvider
from agents.kernel.capabilities.tools import ToolRuntimeContext
from agents.kernel.context.workspace import WorkspaceContext
from agents.kernel.governance import SandboxPolicy
from agents.kernel.governance.audit import InMemoryApprovalAuditStore
from agents.kernel.mcp_config import InMemoryMCPConfigStore
from agents.kernel.runtime import AgentResult, AgentRuntime, AgentSession, InMemoryCheckpointStore, RuntimeCheckpoint, ScriptedModelClient, StaticToolPermissionPolicy
from agents.kernel.schema import Message, RuntimeEvent, ToolCall
from agents.kernel.capabilities.tools.registry import ToolRegistry
from agents.kernel.schema import ModelResponse
from agents.kernel.session_state import InMemorySessionStateStore
from agents.kernel.specs import AgentSpec
from agents.kernel.state import AgentProfile, InMemoryAgentProfileStore
from agents.kernel.tasks import InMemoryTaskQueue, InMemoryTaskStore, TaskStatus, TaskStepStatus
from agents.platform import create_terminal_persistence
from agents.platform.profiles import enabled_tools, permission_settings, settings_for_terminal, workspace_path


async def run_slash(state, text, emitted):
    await handle_slash_command(
        state,
        text,
        make_session=ndjson._make_session,
        close_session_model_client=ndjson._close_session_model_client,
        write=emitted.append,
    )


def test_terminal_runtime_settings_include_server_root_for_chat_profile():
    settings = settings_for_terminal("chat", None)

    assert settings.server.ROOT_PATH
    assert settings.agent.MAX_TOOL_ITERATIONS == 0


def test_terminal_runtime_settings_can_bind_workspace_root(tmp_path):
    settings = settings_for_terminal("coding", None, workspace_root=tmp_path)

    assert settings.server.ROOT_PATH == str(tmp_path.resolve())


def test_terminal_runtime_settings_accept_terminal_db_override(monkeypatch, tmp_path):
    db_path = tmp_path / "terminal.db"
    monkeypatch.setenv("AGENTS_TERMINAL_DB_PATH", str(db_path))

    settings = settings_for_terminal("coding", None, workspace_root=tmp_path)

    assert settings.agent.DB_PATH == str(db_path)


def test_terminal_chat_profile_uses_current_directory_as_workspace(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    assert workspace_path("chat", None) == tmp_path.resolve()


def test_terminal_coding_profile_exposes_task_and_agent_tools():
    tools = enabled_tools("coding", None)
    _, approval_tools = permission_settings("guarded", "coding")

    assert "task.create" in tools
    assert "task.output" in tools
    assert "task.run" in tools
    assert "task.background" in tools
    assert "task.backgrounds" in tools
    assert "schedule.create" in tools
    assert "schedule.list" in tools
    assert "schedule.delete" in tools
    assert "schedule.run" in tools
    assert "agent.profiles" in tools
    assert "agent.save_profile" in tools
    assert "team.create" in tools
    assert "team.members" in tools
    assert "team.send" in tools
    assert "team.inbox" in tools
    assert "team.run_member" in tools
    assert "command.discover" in tools
    assert "command.render" in tools
    assert "command.read" in tools
    assert "command.save" in tools
    assert "command.delete" in tools
    assert "tool.search" in tools
    assert "skill.discover" in tools
    assert "skill.install" in tools
    assert "skill.uninstall" in tools
    assert "skill.use" in tools
    assert "skill.disable" in tools
    assert "plugin.discover" in tools
    assert "plugin.install" in tools
    assert "plugin.uninstall" in tools
    assert "plugin.enable" in tools
    assert "plugin.disable" in tools
    assert "mcp.servers" in tools
    assert "mcp.configure" in tools
    assert "mcp.enable" in tools
    assert "mcp.disable" in tools
    assert "mcp.remove" in tools
    assert "mcp.clear" in tools
    assert "mcp.reload" in tools
    assert "mcp.prompts" in tools
    assert "mcp.get_prompt" in tools
    assert "mcp.resources" in tools
    assert "mcp.read_resource" in tools
    assert "prompt.templates" in tools
    assert "prompt.render" in tools
    assert "prompt.read" in tools
    assert "prompt.save" in tools
    assert "prompt.delete" in tools
    assert "session.status" in tools
    assert "session.summary" in tools
    assert "session.export" in tools
    assert "context.trace" in tools
    assert "context.messages" in tools
    assert "context.compact" in tools
    assert "context.rewind" in tools
    assert "permission.status" in tools
    assert "permission.sources" in tools
    assert "permission.explain" in tools
    assert "permission.add_rule" in tools
    assert "permission.remove_rule" in tools
    assert "hook.events" in tools
    assert "hook.list" in tools
    assert "hook.add" in tools
    assert "hook.delete" in tools
    assert "memory.list" in tools
    assert "memory.add" in tools
    assert "todo.write" in tools
    assert "plan.enter" in tools
    assert "plan.exit" in tools
    assert "workflow.templates" in tools
    assert "workflow.read" in tools
    assert "workflow.save" in tools
    assert "workflow.delete" in tools
    assert "workflow.validate" in tools
    assert "workflow.run" in tools
    assert "workflow.run_saved" in tools
    assert "agent.run" in tools
    assert "plan.exit" in approval_tools
    assert "command.save" in approval_tools
    assert "command.delete" in approval_tools
    assert "prompt.save" in approval_tools
    assert "prompt.delete" in approval_tools
    assert "context.compact" in approval_tools
    assert "context.rewind" in approval_tools
    assert "session.export" in approval_tools
    assert "skill.install" in approval_tools
    assert "skill.uninstall" in approval_tools
    assert "skill.use" in approval_tools
    assert "skill.disable" in approval_tools
    assert "plugin.install" in approval_tools
    assert "plugin.uninstall" in approval_tools
    assert "plugin.enable" in approval_tools
    assert "plugin.disable" in approval_tools
    assert "mcp.configure" in approval_tools
    assert "mcp.enable" in approval_tools
    assert "mcp.disable" in approval_tools
    assert "mcp.remove" in approval_tools
    assert "mcp.clear" in approval_tools
    assert "mcp.reload" in approval_tools
    assert "permission.add_rule" in approval_tools
    assert "permission.remove_rule" in approval_tools
    assert "memory.add" in approval_tools
    assert "hook.add" in approval_tools
    assert "hook.delete" in approval_tools
    assert "task.run" in approval_tools
    assert "schedule.create" in approval_tools
    assert "schedule.delete" in approval_tools
    assert "schedule.run" in approval_tools
    assert "workflow.save" in approval_tools
    assert "workflow.delete" in approval_tools
    assert "workflow.run" in approval_tools
    assert "workflow.run_saved" in approval_tools
    assert "task.background" in approval_tools
    assert "agent.save_profile" in approval_tools
    assert "team.run_member" in approval_tools
    assert "agent.run" in approval_tools


def test_ndjson_bridge_exposes_todo_and_plan_commands(tmp_path):
    tool_context = SimpleNamespace(
        todos=[
            {"content": "Add todo command", "status": "in_progress", "activeForm": "Adding todo command"},
            {"content": "Run checks", "status": "pending", "activeForm": "Running checks"},
        ],
        plan_mode=False,
        plan_text="",
        plan_allowed_prompts=[],
    )
    state = ndjson.BridgeState(
        args=SimpleNamespace(),
        profile="coding",
        permission="guarded",
        active_workspace=tmp_path,
        active_tools=[],
        permission_mode="auto",
        approval_tools=[],
        settings=SimpleNamespace(),
        persistence=SimpleNamespace(),
        model_profiles=[],
        session=SimpleNamespace(
            runtime=SimpleNamespace(protocol="openai-chat", model="gpt-test"),
            messages=[],
            workspace=SimpleNamespace(),
            tool_context=tool_context,
        ),
        session_store=TerminalSessionStore(tmp_path / "sessions"),
        session_id="session-test",
        event_offsets={},
    )
    emitted = []

    asyncio.run(run_slash(state, "/todo", emitted))
    asyncio.run(run_slash(state, "/plan enter", emitted))
    asyncio.run(run_slash(state, "/plan exit Implement todo and plan commands", emitted))
    asyncio.run(run_slash(state, "/todo clear", emitted))

    assert emitted[0]["type"] == "todo"
    assert dict(emitted[0]["todo"])["1. Add todo command"] == "in_progress · Adding todo command"
    assert emitted[1] == {"type": "notice", "message": "entered plan mode"}
    assert dict(emitted[2]["plan"])["mode"] == "plan"
    assert emitted[3] == {"type": "notice", "message": "exited plan mode"}
    assert dict(emitted[4]["plan"])["last_plan"] == "Implement todo and plan commands"
    assert emitted[5] == {"type": "notice", "message": "todos cleared"}
    assert emitted[6] == {"type": "todo", "todo": [["todos", "empty"]]}


def test_ndjson_bridge_includes_workspace_prompt_commands_in_help(tmp_path):
    commands_dir = tmp_path / ".agents" / "commands"
    commands_dir.mkdir(parents=True)
    (commands_dir / "review.md").write_text(
        "---\n"
        "description: Review a path\n"
        "aliases: inspect\n"
        "---\n"
        "Review {arguments}\n",
        encoding="utf-8",
    )
    state = ndjson.BridgeState(
        args=SimpleNamespace(),
        profile="coding",
        permission="guarded",
        active_workspace=tmp_path,
        active_tools=[],
        permission_mode="auto",
        approval_tools=[],
        settings=SimpleNamespace(),
        persistence=SimpleNamespace(),
        model_profiles=[],
        session=SimpleNamespace(
            runtime=SimpleNamespace(protocol="openai-chat", model="gpt-test"),
            messages=[],
            workspace=SimpleNamespace(),
            tool_context=SimpleNamespace(workspace=SimpleNamespace(path=tmp_path)),
        ),
        session_store=TerminalSessionStore(tmp_path / "sessions"),
        session_id="session-test",
        event_offsets={},
    )
    emitted = []

    asyncio.run(run_slash(state, "/commands", emitted))

    rows = {command["name"]: command for command in emitted[0]["commands"]}
    assert rows["/review"]["source"] == "workspace"
    assert rows["/review"]["aliases"] == ["/inspect"]


def test_ndjson_bridge_manages_workspace_prompt_commands(tmp_path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="terminal",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path, allow_file_write=True)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    state = ndjson.BridgeState(
        args=SimpleNamespace(),
        profile="coding",
        permission="guarded",
        active_workspace=tmp_path,
        active_tools=[],
        permission_mode="auto",
        approval_tools=[],
        settings=SimpleNamespace(),
        persistence=SimpleNamespace(),
        model_profiles=[],
        session=SimpleNamespace(
            runtime=SimpleNamespace(protocol="openai-chat", model="gpt-test"),
            messages=[],
            workspace=workspace,
            tool_context=context,
        ),
        session_store=TerminalSessionStore(tmp_path / "sessions"),
        session_id="session-test",
        event_offsets={},
    )
    emitted = []

    asyncio.run(run_slash(state, "/commands save review -- Review {arguments}", emitted))
    asyncio.run(run_slash(state, "/commands read review", emitted))
    asyncio.run(run_slash(state, "/commands render review src", emitted))
    asyncio.run(run_slash(state, "/commands delete review", emitted))

    assert emitted[0] == {"type": "notice", "message": "command saved: /review"}
    assert emitted[1]["type"] == "commands"
    assert any(command["name"] == "/review" for command in emitted[1]["commands"])
    assert emitted[2]["type"] == "prompt"
    assert ["name", "/review"] in emitted[2]["prompt"]
    assert emitted[3] == {"type": "prompt", "prompt": [["command", "/review"], ["prompt", "Review src"]]}
    assert emitted[4] == {"type": "notice", "message": "command deleted: /review"}
    assert emitted[5]["type"] == "commands"
    assert all(command.get("name") != "/review" for command in emitted[5]["commands"])


def test_ndjson_bridge_renders_workspace_prompt_command_for_direct_slash(tmp_path):
    commands_dir = tmp_path / ".agents" / "commands"
    commands_dir.mkdir(parents=True)
    (commands_dir / "review.md").write_text(
        "---\n"
        "description: Review a path\n"
        "aliases: inspect\n"
        "---\n"
        "Review {arguments}\n",
        encoding="utf-8",
    )
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="terminal",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    context = ToolRuntimeContext(workspace=workspace, sandbox=SandboxPolicy.for_workspace(workspace.path))
    state = ndjson.BridgeState(
        args=SimpleNamespace(),
        profile="coding",
        permission="guarded",
        active_workspace=tmp_path,
        active_tools=[],
        permission_mode="auto",
        approval_tools=[],
        settings=SimpleNamespace(),
        persistence=SimpleNamespace(),
        model_profiles=[],
        session=SimpleNamespace(tool_context=context),
        session_store=TerminalSessionStore(tmp_path / "sessions"),
        session_id="session-test",
        event_offsets={},
    )

    assert ndjson._render_workspace_command_prompt(state, "/review src/agents") == "Review src/agents"
    assert ndjson._render_workspace_command_prompt(state, "/inspect tests") == "Review tests"
    assert ndjson._render_workspace_command_prompt(state, "/help") is None
    assert ndjson._render_workspace_command_prompt(state, "/missing") is None


def test_ndjson_bridge_does_not_replay_approval_request_after_resume(monkeypatch, tmp_path):
    class ApprovalSession:
        async def stream(self, text, run_id=None):
            yield RuntimeEvent(
                type="tool_approval_required",
                name="filesystem.write",
                payload={
                    "approval_id": "call-1",
                    "tool_call": {"id": "call-1", "name": "filesystem.write", "arguments": {"path": "out.txt"}},
                },
            )
            yield RuntimeEvent(
                type="done",
                name="assistant",
                payload={"status": "awaiting_approval", "content": "tool approval required", "event_count": 2},
            )

        async def resume_stream(self, run_id, approvals=None, approval_scopes=None):
            yield RuntimeEvent(
                type="tool_approval_decision",
                name="filesystem.write",
                payload={"approval_id": "call-1", "approved": True, "scope": "allow_once"},
            )
            yield RuntimeEvent(type="text_delta", name="assistant", payload={"delta": "created"})
            yield RuntimeEvent(
                type="done",
                name="assistant",
                payload={
                    "content": "created",
                    "messages": [Message.from_text("assistant", "created").to_dict()],
                    "event_count": 4,
                    "status": "finished",
                },
            )

        async def resume(self, run_id, approvals=None, approval_scopes=None):
            raise AssertionError("ndjson bridge should prefer streaming resume")

    emitted = []
    monkeypatch.setattr(ndjson, "_write", emitted.append)
    state = ndjson.BridgeState(
        args=SimpleNamespace(),
        profile="coding",
        permission="guarded",
        active_workspace=None,
        active_tools=[],
        permission_mode="auto",
        approval_tools=[],
        settings=SimpleNamespace(),
        persistence=SimpleNamespace(),
        model_profiles=[],
        session=ApprovalSession(),
        session_store=TerminalSessionStore(tmp_path / "sessions"),
        session_id="session-test",
        event_offsets={},
    )

    async def run_flow():
        await ndjson._run_turn(state, "write file", "run-1")
        await ndjson._run_approval(
            state,
            {
                "run_id": "run-1",
                "approvals": {"call-1": True},
                "approval_scopes": {"call-1": "allow_once"},
            },
        )

    asyncio.run(run_flow())

    assert state.event_offsets["run-1"] == 4
    resume_event_types = [
        payload["event"]["type"]
        for payload in emitted
        if payload.get("type") == "runtime_event" and payload["event"]["type"] != "done"
    ][1:]
    assert resume_event_types == ["tool_approval_decision", "text_delta"]


def test_ndjson_bridge_handles_compact_command(tmp_path):
    class CompactSession:
        def compact(self, target_tokens=None):
            return {
                "before_messages": 8,
                "after_messages": 3,
                "dropped_messages": 5,
                "before_tokens": 1200,
                "after_tokens": 260,
            }

    emitted = []
    state = ndjson.BridgeState(
        args=SimpleNamespace(),
        profile="coding",
        permission="guarded",
        active_workspace=None,
        active_tools=[],
        permission_mode="auto",
        approval_tools=[],
        settings=SimpleNamespace(),
        persistence=SimpleNamespace(),
        model_profiles=[],
        session=CompactSession(),
        session_store=TerminalSessionStore(tmp_path / "sessions"),
        session_id="session-test",
        event_offsets={},
    )

    asyncio.run(run_slash(state, "/compact 260", emitted))

    assert emitted == [
        {"type": "notice", "message": "compacted 5 messages"},
        {
            "type": "context",
            "context": {
                "before_messages": "8",
                "after_messages": "3",
                "dropped_messages": "5",
                "before_tokens": "1200",
                "after_tokens": "260",
            },
        },
    ]


def test_ndjson_bridge_lists_and_drops_context_messages(tmp_path):
    messages = [
        Message.from_text("system", "prompt"),
        Message.from_text("user", "old question"),
        Message.from_text("assistant", "old answer"),
        Message.from_text("user", "new question"),
    ]
    state = ndjson.BridgeState(
        args=SimpleNamespace(),
        profile="coding",
        permission="guarded",
        active_workspace=tmp_path,
        active_tools=[],
        permission_mode="auto",
        approval_tools=[],
        settings=SimpleNamespace(),
        persistence=SimpleNamespace(),
        model_profiles=[],
        session=SimpleNamespace(
            runtime=SimpleNamespace(protocol="scripted", model="context"),
            messages=list(messages),
            _estimate_tokens=lambda value: len(value),
        ),
        session_store=TerminalSessionStore(tmp_path / "sessions"),
        session_id="session-test",
        event_offsets={},
    )
    emitted = []

    asyncio.run(run_slash(state, "/context messages", emitted))
    asyncio.run(run_slash(state, "/context drop 2", emitted))

    assert emitted[0]["type"] == "context_messages"
    assert "user · old question" in emitted[0]["messages"][1][1]
    assert emitted[1] == {"type": "notice", "message": "dropped 2 context messages"}
    assert emitted[2]["type"] == "context"
    assert [message.content_text() for message in state.session.messages] == ["prompt", "new question"]


def test_ndjson_bridge_saves_pending_approval_session_snapshot(monkeypatch, tmp_path):
    call = ToolCall(id="call-1", name="filesystem.write", arguments={"path": "out.txt"})
    approval_event = RuntimeEvent(
        type="tool_approval_required",
        name="filesystem.write",
        payload={
            "approval_id": "call-1",
            "tool_call": call.to_dict(),
        },
    )

    class ApprovalSession:
        def __init__(self):
            self.messages = [Message.from_text("system", "prompt")]

        async def stream(self, text, run_id=None):
            self.messages = [
                Message.from_text("system", "prompt"),
                Message.from_text("user", text),
                Message.from_text("assistant", "", tool_calls=[call]),
            ]
            yield approval_event
            yield RuntimeEvent(
                type="done",
                name="assistant",
                payload={
                    "status": "awaiting_approval",
                    "content": "tool approval required",
                    "event_count": 2,
                    "messages": [message.to_dict() for message in self.messages],
                },
            )

    async def seed_checkpoint(store):
        await store.save(
            RuntimeCheckpoint(
                run_id="run-approval",
                step="approval_required",
                iteration=0,
                messages=[Message.from_text("user", "write it"), Message.from_text("assistant", "", tool_calls=[call])],
                events=[approval_event],
                pending_tool_calls=[call],
            )
        )

    emitted = []
    monkeypatch.setattr(ndjson, "_write", emitted.append)
    checkpoint_store = InMemoryCheckpointStore()
    asyncio.run(seed_checkpoint(checkpoint_store))
    session_store = TerminalSessionStore(tmp_path / "sessions")
    state = ndjson.BridgeState(
        args=SimpleNamespace(),
        profile="coding",
        permission="guarded",
        active_workspace=tmp_path,
        active_tools=[],
        permission_mode="auto",
        approval_tools=[],
        settings=SimpleNamespace(),
        persistence=SimpleNamespace(checkpoints=checkpoint_store),
        model_profiles=[],
        session=ApprovalSession(),
        session_store=session_store,
        session_id="session-approval",
        event_offsets={},
    )

    asyncio.run(ndjson._run_turn(state, "write it", "run-approval"))

    record = session_store.load("session-approval")
    assert record is not None
    assert record.pending_run_id == "run-approval"
    assert record.pending_approval["type"] == "tool_approval_required"
    assert record.checkpoint is not None
    assert record.checkpoint.pending_tool_calls == [call]


def test_ndjson_bridge_resume_restores_pending_approval_checkpoint(tmp_path):
    call = ToolCall(id="call-1", name="filesystem.write", arguments={"path": "out.txt"})
    approval_event = RuntimeEvent(
        type="tool_approval_required",
        name="filesystem.write",
        payload={"approval_id": "call-1", "tool_call": call.to_dict()},
    )
    checkpoint = RuntimeCheckpoint(
        run_id="run-approval",
        step="approval_required",
        iteration=0,
        messages=[Message.from_text("user", "write it"), Message.from_text("assistant", "", tool_calls=[call])],
        events=[approval_event],
        pending_tool_calls=[call],
    )
    store = TerminalSessionStore(tmp_path / "sessions")
    store.save(
        "session-approval",
        [Message.from_text("system", "prompt"), Message.from_text("user", "write it")],
        profile="coding",
        model="scripted · approval",
        workspace_path=str(tmp_path),
        pending_run_id="run-approval",
        pending_approval=approval_event.to_dict(),
        checkpoint=checkpoint,
    )
    checkpoint_store = InMemoryCheckpointStore()
    emitted = []
    state = ndjson.BridgeState(
        args=SimpleNamespace(),
        profile="coding",
        permission="guarded",
        active_workspace=tmp_path,
        active_tools=[],
        permission_mode="auto",
        approval_tools=[],
        settings=SimpleNamespace(),
        persistence=SimpleNamespace(checkpoints=checkpoint_store),
        model_profiles=[],
        session=SimpleNamespace(
            runtime=SimpleNamespace(protocol="scripted", model="approval"),
            messages=[],
            _estimate_tokens=lambda messages: 0,
        ),
        session_store=store,
        session_id="session-new",
        event_offsets={},
    )

    asyncio.run(run_slash(state, "/resume session-approval", emitted))
    restored_checkpoint = asyncio.run(checkpoint_store.load("run-approval"))

    assert restored_checkpoint is not None
    assert restored_checkpoint.pending_tool_calls == [call]
    runtime_event = next(payload for payload in emitted if payload.get("type") == "runtime_event")
    assert runtime_event["event"]["type"] == "tool_approval_required"
    assert runtime_event["event"]["payload"]["run_id"] == "run-approval"


def test_ndjson_bridge_restored_pending_approval_can_complete(tmp_path):
    call = ToolCall(id="call-1", name="echo", arguments={"text": "hi"})
    approval_event = RuntimeEvent(
        type="tool_approval_required",
        name="echo",
        payload={"approval_id": "call-1", "tool_call": call.to_dict()},
    )
    checkpoint = RuntimeCheckpoint(
        run_id="run-approval",
        step="approval_required",
        iteration=0,
        messages=[Message.from_text("user", "say hi"), Message.from_text("assistant", "", tool_calls=[call])],
        events=[approval_event],
        pending_tool_calls=[call],
    )
    session_store = TerminalSessionStore(tmp_path / "sessions")
    session_store.save(
        "session-approval",
        checkpoint.messages,
        profile="coding",
        model="scripted · approval",
        workspace_path=str(tmp_path),
        pending_run_id="run-approval",
        pending_approval=approval_event.to_dict(),
        checkpoint=checkpoint,
    )
    checkpoint_store = InMemoryCheckpointStore()
    audit_store = InMemoryApprovalAuditStore()
    tools = ToolRegistry()
    tools.register("echo", "Echo", {}, lambda text: text)
    runtime = AgentRuntime(
        model_client=ScriptedModelClient([ModelResponse(message=Message.from_text("assistant", "restored approval done"))]),
        tools=tools,
        protocol="scripted",
        model="approval",
        permission_policy=StaticToolPermissionPolicy(approval_required_tools={"echo"}),
        checkpoint_store=checkpoint_store,
    )
    state = ndjson.BridgeState(
        args=SimpleNamespace(),
        profile="coding",
        permission="guarded",
        active_workspace=tmp_path,
        active_tools=[],
        permission_mode="auto",
        approval_tools=[],
        settings=SimpleNamespace(),
        persistence=SimpleNamespace(checkpoints=checkpoint_store, approval_audit=audit_store),
        model_profiles=[],
        session=AgentSession(runtime=runtime),
        session_store=session_store,
        session_id="session-new",
        event_offsets={},
    )
    emitted = []

    async def execute():
        await run_slash(state, "/resume session-approval", emitted)
        await ndjson.run_approval(
            state,
            {
                "run_id": "run-approval",
                "approvals": {"call-1": True},
                "approval_scopes": {"call-1": "allow_once"},
            },
            emitted.append,
        )

    asyncio.run(execute())

    event_types = [payload["event"]["type"] for payload in emitted if payload.get("type") == "runtime_event"]
    assert event_types == [
        "tool_approval_required",
        "tool_approval_decision",
        "tool_start",
        "tool_result",
        "tool_use_summary",
        "done",
    ]
    summary_event = next(
        payload["event"]
        for payload in emitted
        if payload.get("type") == "runtime_event" and payload["event"]["type"] == "tool_use_summary"
    )
    assert summary_event["payload"]["summary"] == "Ran echo"
    assert summary_event["payload"]["preceding_tool_use_ids"] == ["call-1"]
    assert emitted[-1] == {"type": "turn_finished", "status": "finished", "run_id": "run-approval"}
    assert state.session.messages[-1].content_text() == "restored approval done"
    audits = asyncio.run(audit_store.list_for_run("run-approval"))
    assert len(audits) == 1
    assert audits[0].approval_id == "call-1"
    assert audits[0].tool_name == "echo"
    assert audits[0].approved is True

    asyncio.run(run_slash(state, "/permissions audit run-approval", emitted))
    assert emitted[-1]["type"] == "permissions"
    assert emitted[-1]["permissions"][0][0] == "call-1"
    assert "echo · allow_once" in emitted[-1]["permissions"][0][1]


def test_ndjson_bridge_lists_and_resumes_saved_sessions(tmp_path):
    class Runtime:
        protocol = "scripted"
        model = "test-model"

    class Session:
        runtime = Runtime()

        def __init__(self):
            self.messages = [Message.from_text("system", "new")]
            self.context_window = SimpleNamespace(system_prompt="new")

    store = TerminalSessionStore(tmp_path / "sessions")
    store.save(
        "session-abc",
        [Message.from_text("system", "saved"), Message.from_text("user", "hello")],
        profile="coding",
        model="scripted · test-model",
        workspace_path=str(tmp_path),
    )
    emitted = []
    state = ndjson.BridgeState(
        args=SimpleNamespace(),
        profile="coding",
        permission="guarded",
        active_workspace=tmp_path,
        active_tools=[],
        permission_mode="auto",
        approval_tools=[],
        settings=SimpleNamespace(),
        persistence=SimpleNamespace(),
        model_profiles=[],
        session=Session(),
        session_store=store,
        session_id="session-new",
        event_offsets={},
    )

    asyncio.run(run_slash(state, "/sessions", emitted))
    asyncio.run(run_slash(state, "/resume session-abc", emitted))

    assert emitted[0]["type"] == "sessions"
    assert emitted[0]["sessions"][0]["id"] == "session-abc"
    assert emitted[1] == {
        "type": "session_resumed",
        "session_id": "session-abc",
        "messages": [{"role": "user", "content": "hello"}],
    }
    assert emitted[2]["type"] == "notice"
    assert emitted[3]["type"] == "status"
    assert state.session_id == "session-abc"
    assert [message.content_text() for message in state.session.messages] == ["saved", "hello"]
    assert state.session.context_window.system_prompt == "saved"


def test_ndjson_bridge_deletes_saved_session(tmp_path):
    store = TerminalSessionStore(tmp_path / "sessions")
    store.save(
        "session-delete",
        [Message.from_text("user", "old")],
        profile="coding",
        model="scripted · old",
        workspace_path=str(tmp_path),
    )
    state = ndjson.BridgeState(
        args=SimpleNamespace(),
        profile="coding",
        permission="guarded",
        active_workspace=tmp_path,
        active_tools=[],
        permission_mode="auto",
        approval_tools=[],
        settings=SimpleNamespace(),
        persistence=SimpleNamespace(),
        model_profiles=[],
        session=SimpleNamespace(),
        session_store=store,
        session_id="session-current",
        event_offsets={},
    )
    emitted = []

    asyncio.run(run_slash(state, "/sessions delete session-delete", emitted))

    assert emitted[0] == {"type": "notice", "message": "session deleted: session-delete"}
    assert emitted[1]["type"] == "sessions"
    assert emitted[1]["sessions"] == []
    assert store.load("session-delete") is None


def test_ndjson_bridge_exports_forks_and_rewinds_session(tmp_path):
    runtime = AgentRuntime(
        model_client=ScriptedModelClient([]),
        tools=ToolRegistry(),
        protocol="scripted",
        model="session",
        enabled_tools=[],
    )
    session = AgentSession(runtime=runtime)
    session.messages = [
        Message.from_text("system", "base"),
        Message.from_text("user", "first"),
        Message.from_text("assistant", "answer"),
        Message.from_text("user", "second"),
    ]
    state = ndjson.BridgeState(
        args=SimpleNamespace(),
        profile="coding",
        permission="guarded",
        active_workspace=tmp_path,
        active_tools=[],
        permission_mode="auto",
        approval_tools=[],
        settings=SimpleNamespace(),
        persistence=SimpleNamespace(),
        model_profiles=[],
        session=session,
        session_store=TerminalSessionStore(tmp_path / "sessions"),
        session_id="session-current",
        event_offsets={},
    )
    emitted = []

    asyncio.run(run_slash(state, "/export markdown exports/chat.md", emitted))
    asyncio.run(run_slash(state, "/fork 2", emitted))
    forked_id = state.session_id
    asyncio.run(run_slash(state, "/rewind 1", emitted))

    assert emitted[0] == {"type": "notice", "message": "session exported: exports/chat.md"}
    assert "# Session session-current" in (tmp_path / "exports" / "chat.md").read_text(encoding="utf-8")
    assert emitted[2]["type"] == "notice"
    assert emitted[2]["message"].startswith("forked session: ")
    assert emitted[3]["type"] == "session_resumed"
    assert emitted[3]["session_id"] == forked_id
    assert [item["content"] for item in emitted[3]["messages"]] == ["first", "answer"]
    assert state.session_store.load(forked_id) is not None
    assert emitted[5] == {"type": "notice", "message": "rewound 1 message"}
    assert [message.content_text() for message in state.session.messages] == ["base", "first"]


def test_ndjson_bridge_summarizes_current_session(tmp_path):
    runtime = AgentRuntime(
        model_client=ScriptedModelClient([]),
        tools=ToolRegistry(),
        protocol="scripted",
        model="session",
        enabled_tools=[],
    )
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="terminal",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    context = ToolRuntimeContext(workspace=workspace, sandbox=SandboxPolicy.for_workspace(workspace.path))
    session = AgentSession(runtime=runtime, workspace=workspace, tool_context=context)
    session.messages.append(Message.from_text("user", "summarize this work"))
    state = ndjson.BridgeState(
        args=SimpleNamespace(),
        profile="coding",
        permission="guarded",
        active_workspace=tmp_path,
        active_tools=[],
        permission_mode="auto",
        approval_tools=[],
        settings=SimpleNamespace(),
        persistence=SimpleNamespace(),
        model_profiles=[],
        session=session,
        session_store=TerminalSessionStore(tmp_path / "sessions"),
        session_id="session-current",
        event_offsets={},
    )
    emitted = []

    asyncio.run(run_slash(state, "/summary", emitted))

    assert emitted[0]["type"] == "session"
    rows = dict(emitted[0]["session"])
    assert "user: summarize this work" in rows["summary"]
    assert rows["messages"] == "1 / 1"
    assert rows["roles"] == "user=1"


def test_ndjson_bridge_lists_capability_catalogs(tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "focus.json").write_text(
        '{"name":"focus","version":"1.0.0","description":"Focus skill","tools":["filesystem.read"]}',
        encoding="utf-8",
    )
    plugin_dir = tmp_path / ".agents" / "plugins" / "planner" / ".codex-plugin"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin.json").write_text(
        '{"name":"planner","version":"0.1.0","description":"Planning plugin"}',
        encoding="utf-8",
    )
    memories = InMemoryMemoryStore()
    asyncio.run(
        memories.save(
            MemoryRecord.create(
                tenant_id="tenant",
                user_id="user",
                agent_id="terminal",
                workspace_id="workspace",
                scope=MemoryScope.WORKSPACE,
                content="remember this project preference",
            )
        )
    )
    state = ndjson.BridgeState(
        args=SimpleNamespace(),
        profile="coding",
        permission="guarded",
        active_workspace=tmp_path,
        active_tools=["filesystem.read", "mcp_docs_search"],
        permission_mode="auto",
        approval_tools=[],
        settings=SimpleNamespace(
            agent=SimpleNamespace(SKILLS="focus"),
            server=SimpleNamespace(ROOT_PATH=str(tmp_path)),
            mcp=SimpleNamespace(
                SERVER_NAME="docs",
                SERVER_COMMAND="python server.py",
                EXECUTION_MODE="trusted_control_plane",
                SANDBOX_PROFILE="",
            ),
        ),
        persistence=SimpleNamespace(memories=memories),
        model_profiles=[],
        session=SimpleNamespace(
            workspace=SimpleNamespace(
                tenant_id="tenant",
                user_id="user",
                agent_id="terminal",
                workspace_id="workspace",
            )
        ),
        session_store=TerminalSessionStore(tmp_path / "sessions"),
        session_id="session-test",
        event_offsets={},
    )
    emitted = []

    asyncio.run(run_slash(state, "/skills", emitted))
    asyncio.run(run_slash(state, "/mcp", emitted))
    asyncio.run(run_slash(state, "/memory", emitted))
    asyncio.run(run_slash(state, "/plugins", emitted))
    asyncio.run(run_slash(state, "/capabilities", emitted))

    assert emitted[0]["type"] == "skills"
    assert emitted[0]["skills"][0][0] == "focus"
    assert "configured" in emitted[0]["skills"][0][1]
    assert emitted[1]["type"] == "mcp"
    assert ["server", "docs"] in emitted[1]["mcp"]
    assert ["tools", "1"] in emitted[1]["mcp"]
    assert emitted[2]["type"] == "memory"
    assert "remember this project preference" in emitted[2]["memory"][0][1]
    assert emitted[3]["type"] == "plugins"
    assert emitted[3]["plugins"][0][0] == "planner"
    assert "Planning plugin" in emitted[3]["plugins"][0][1]
    assert emitted[4]["type"] == "capabilities"
    capability_rows = dict(emitted[4]["capabilities"])
    assert capability_rows["skills"] == "1 visible"
    assert capability_rows["plugins"] == "1 visible"
    assert capability_rows["mcp"] == "docs · 1 tools"


def test_ndjson_bridge_manages_workspace_workflows(tmp_path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="terminal",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path, allow_file_write=True)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    runtime = AgentRuntime(
        model_client=ScriptedModelClient([]),
        tools=ToolRegistry(),
        protocol="scripted",
        model="workflow",
        enabled_tools=[],
    )
    state = ndjson.BridgeState(
        args=SimpleNamespace(),
        profile="coding",
        permission="guarded",
        active_workspace=tmp_path,
        active_tools=[],
        permission_mode="auto",
        approval_tools=[],
        settings=SimpleNamespace(),
        persistence=SimpleNamespace(),
        model_profiles=[],
        session=AgentSession(runtime=runtime, workspace=workspace, tool_context=context),
        session_store=TerminalSessionStore(tmp_path / "sessions"),
        session_id="session-test",
        event_offsets={},
    )
    emitted = []
    workflow_json = (
        '{"workflow_id":"gate","nodes":[{"node_id":"approve","kind":"human_approval",'
        '"name":"Approve release","prompt":"ship it?"}]}'
    )

    asyncio.run(run_slash(state, "/workflows", emitted))
    asyncio.run(run_slash(state, "/workflows save gate %s" % workflow_json, emitted))
    asyncio.run(run_slash(state, "/workflows read gate", emitted))
    asyncio.run(run_slash(state, "/workflows validate gate", emitted))
    asyncio.run(run_slash(state, "/workflows run gate", emitted))
    asyncio.run(run_slash(state, "/workflows delete gate", emitted))

    assert emitted[0] == {"type": "workflows", "workflows": [["workflows", "none saved"]]}
    assert emitted[1] == {"type": "notice", "message": "workflow saved: gate"}
    assert emitted[2]["type"] == "workflows"
    assert emitted[2]["workflows"][0][0] == "gate"
    assert "1 node" in emitted[2]["workflows"][0][1]
    assert emitted[3]["type"] == "workflows"
    assert ["workflow_id", "gate"] in emitted[3]["workflows"]
    assert ["order", "approve"] in emitted[4]["workflows"]
    assert emitted[5] == {"type": "notice", "message": "workflow gate: awaiting_approval"}
    assert ["approve", "human_approval · awaiting_approval · ship it?"] in emitted[6]["workflows"]
    assert emitted[7] == {"type": "notice", "message": "workflow deleted: gate"}
    assert emitted[8] == {"type": "workflows", "workflows": [["workflows", "none saved"]]}


def test_ndjson_bridge_manages_scheduled_tasks(tmp_path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="terminal",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path)
    store = InMemoryTaskStore()
    spec = AgentSpec.from_overrides(
        tenant_id="tenant",
        user_id="user",
        agent_id="terminal",
        workspace_id="workspace",
        workspace_path=str(tmp_path),
    )
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
        task_store=store,
        agent_spec=spec,
    )
    runtime = AgentRuntime(
        model_client=ScriptedModelClient([]),
        tools=ToolRegistry(),
        protocol="scripted",
        model="schedule",
        enabled_tools=[],
    )
    state = ndjson.BridgeState(
        args=SimpleNamespace(),
        profile="coding",
        permission="guarded",
        active_workspace=tmp_path,
        active_tools=[],
        permission_mode="auto",
        approval_tools=[],
        settings=SimpleNamespace(),
        persistence=SimpleNamespace(tasks=store),
        model_profiles=[],
        session=AgentSession(runtime=runtime, workspace=workspace, tool_context=context),
        session_store=TerminalSessionStore(tmp_path / "sessions"),
        session_id="session-test",
        event_offsets={},
    )
    emitted = []

    asyncio.run(run_slash(state, "/schedules", emitted))
    asyncio.run(run_slash(state, "/schedules create Daily repo check -- 0 9 * * * -- Check repo", emitted))
    short_id = emitted[2]["schedules"][0][0]
    asyncio.run(run_slash(state, "/schedules run %s" % short_id, emitted))
    asyncio.run(run_slash(state, "/schedules delete %s" % short_id, emitted))

    assert emitted[0] == {"type": "schedules", "schedules": [["schedules", "none"]]}
    assert emitted[1] == {"type": "notice", "message": "schedule created: %s" % short_id}
    assert emitted[2]["schedules"][0][1] == "enabled · 0 9 * * * · Daily repo check"
    assert emitted[3]["type"] == "notice"
    assert emitted[3]["message"].startswith("schedule queued: ")
    assert "last: task_" in emitted[4]["schedules"][0][1]
    assert emitted[5]["type"] == "tasks"
    assert "Daily repo check" in emitted[5]["tasks"][0][1]
    assert emitted[6] == {"type": "notice", "message": "schedule deleted: %s" % short_id}
    assert emitted[7] == {"type": "schedules", "schedules": [["schedules", "none"]]}


def test_ndjson_bridge_manages_session_hooks(tmp_path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="terminal",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=SandboxPolicy.for_workspace(workspace.path),
        sandbox_client=LocalSandboxProvider().acquire(workspace, SandboxPolicy.for_workspace(workspace.path)),
    )
    state = ndjson.BridgeState(
        args=SimpleNamespace(),
        profile="coding",
        permission="guarded",
        active_workspace=tmp_path,
        active_tools=[],
        permission_mode="auto",
        approval_tools=[],
        settings=SimpleNamespace(),
        persistence=SimpleNamespace(),
        model_profiles=[],
        session=SimpleNamespace(
            runtime=SimpleNamespace(protocol="scripted", model="hooks"),
            messages=[],
            workspace=workspace,
            tool_context=context,
        ),
        session_store=TerminalSessionStore(tmp_path / "sessions"),
        session_id="session-test",
        event_offsets={},
    )
    emitted = []

    asyncio.run(run_slash(state, "/hooks", emitted))
    asyncio.run(run_slash(state, "/hooks add pre_tool_use deny_tool Block tool=shell.run -- Shell blocked.", emitted))
    short_id = emitted[2]["hooks"][0][0]
    asyncio.run(run_slash(state, "/hooks delete %s" % short_id, emitted))

    assert emitted[0] == {"type": "hooks", "hooks": [["hooks", "none"]]}
    assert emitted[1] == {"type": "notice", "message": "hook added: %s" % short_id}
    assert emitted[2]["hooks"][0][1] == "enabled · pre_tool_use · deny_tool · Block · shell.run"
    assert emitted[3] == {"type": "notice", "message": "hook deleted: %s" % short_id}
    assert emitted[4] == {"type": "hooks", "hooks": [["hooks", "none"]]}


def test_ndjson_bridge_configures_reloads_and_clears_mcp(monkeypatch, tmp_path):
    tools = ToolRegistry()
    runtime = AgentRuntime(
        model_client=ScriptedModelClient([]),
        tools=tools,
        protocol="scripted",
        model="mcp",
        enabled_tools=[],
    )
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="terminal",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    settings = SimpleNamespace(
        mcp=SimpleNamespace(
            SERVER_NAME="",
            SERVER_COMMAND="",
            CLIENT_TIMEOUT=30.0,
            EXECUTION_MODE="trusted_control_plane",
            SANDBOX_PROFILE="",
        )
    )
    tool_context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=SandboxPolicy.for_workspace(workspace.path),
        agent_spec=AgentSpec.from_overrides(),
        settings=settings,
        mcp_config_store=InMemoryMCPConfigStore(),
    )
    state = ndjson.BridgeState(
        args=SimpleNamespace(),
        profile="coding",
        permission="guarded",
        active_workspace=tmp_path,
        active_tools=[],
        permission_mode="auto",
        approval_tools=[],
        settings=settings,
        persistence=SimpleNamespace(),
        model_profiles=[],
        session=AgentSession(runtime=runtime, workspace=workspace, tool_context=tool_context),
        session_store=TerminalSessionStore(tmp_path / "sessions"),
        session_id="session-test",
        event_offsets={},
    )

    async def fake_load_configured_mcp(settings, registry, roots=None, records=None, oauth_authenticator=None):
        registry.register(
            "mcp__docs__search",
            "Search docs",
            {},
            lambda query: query,
            metadata={
                "source": "mcp",
                "server": settings.mcp.SERVER_NAME,
                "risk": "medium",
                "mcp_info": {"server": "docs", "remote_name": "search"},
            },
        )
        registry.register(
            "mcp_docs_search",
            "Search docs",
            {},
            lambda query: query,
            metadata={
                "source": "mcp",
                "server": settings.mcp.SERVER_NAME,
                "risk": "medium",
                "alias_of": "mcp__docs__search",
                "mcp_info": {"server": "docs", "remote_name": "search"},
            },
        )
        return [SimpleNamespace(server=SimpleNamespace(name="docs", transport="stdio", url="", headers={}, execution_mode="", auth_required=False))]

    monkeypatch.setattr("agents.kernel.capabilities.mcp_loading.load_configured_mcp", fake_load_configured_mcp)
    emitted = []

    asyncio.run(run_slash(state, "/mcp set docs -- python server.py", emitted))
    asyncio.run(run_slash(state, "/mcp disable docs", emitted))
    asyncio.run(run_slash(state, "/mcp enable docs", emitted))
    asyncio.run(run_slash(state, "/mcp reload", emitted))

    assert emitted[0] == {"type": "notice", "message": "mcp configured: docs"}
    assert emitted[1]["type"] == "mcp"
    assert ["server", "docs"] in emitted[1]["mcp"]
    assert ["command", "python server.py"] in emitted[1]["mcp"]
    assert emitted[2] == {"type": "notice", "message": "mcp disabled: docs"}
    assert emitted[3] == {"type": "mcp", "mcp": [["server", "not configured"]]}
    assert emitted[4] == {"type": "notice", "message": "mcp enabled: docs"}
    assert emitted[5]["type"] == "mcp"
    assert ["server", "docs"] in emitted[5]["mcp"]
    assert emitted[6] == {"type": "notice", "message": "mcp reloaded: 1 tool"}
    assert emitted[7]["type"] == "mcp"
    assert ["tools", "1"] in emitted[7]["mcp"]
    assert emitted[8]["type"] == "tools"
    assert state.active_tools == ["mcp__docs__search"]
    assert runtime.enabled_tools == ["mcp__docs__search"]

    asyncio.run(run_slash(state, "/mcp clear", emitted))

    assert emitted[9] == {"type": "notice", "message": "mcp cleared · removed 1 tool"}
    assert emitted[10] == {"type": "mcp", "mcp": [["server", "not configured"]]}
    assert state.active_tools == []
    assert runtime.enabled_tools == []


def test_ndjson_bridge_enables_and_disables_plugin_tools(tmp_path):
    plugin_dir = tmp_path / ".agents" / "plugins" / "planner"
    manifest_dir = plugin_dir / ".codex-plugin"
    manifest_dir.mkdir(parents=True)
    (plugin_dir / "prompt.md").write_text("Use planner plugin guidance.", encoding="utf-8")
    (manifest_dir / "plugin.json").write_text(
        '{"name":"planner","version":"0.1.0","description":"Planning plugin","tools":["echo"],"prompt_fragments":["prompt.md"]}',
        encoding="utf-8",
    )
    tools = ToolRegistry()
    tools.register("echo", "Echo", {}, lambda text: text)
    runtime = AgentRuntime(
        model_client=ScriptedModelClient([]),
        tools=tools,
        protocol="scripted",
        model="plugins",
        enabled_tools=[],
    )
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="coder",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path)
    state_store = InMemorySessionStateStore()
    tool_context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
        session_state_store=state_store,
    )
    session = AgentSession(runtime=runtime, system_prompt="Base prompt.", workspace=workspace, tool_context=tool_context)
    state = ndjson.BridgeState(
        args=SimpleNamespace(),
        profile="coding",
        permission="guarded",
        active_workspace=tmp_path,
        active_tools=[],
        permission_mode="auto",
        approval_tools=[],
        settings=SimpleNamespace(server=SimpleNamespace(ROOT_PATH=str(tmp_path))),
        persistence=SimpleNamespace(),
        model_profiles=[],
        session=session,
        session_store=TerminalSessionStore(tmp_path / "sessions"),
        session_id="session-test",
        event_offsets={},
    )
    emitted = []

    asyncio.run(run_slash(state, "/plugins enable planner", emitted))

    assert emitted[0] == {"type": "notice", "message": "plugin enabled: planner"}
    assert emitted[1]["type"] == "plugins"
    assert "enabled" in dict(emitted[1]["plugins"])["planner"]
    assert emitted[2]["type"] == "tools"
    assert state.active_tools == ["echo"]
    assert runtime.enabled_tools == ["echo"]
    persisted = asyncio.run(state_store.load_for_scope("tenant", user_id="user", agent_id="coder", workspace_id="workspace"))
    assert persisted.enabled_plugins == ["planner"]
    assert "## plugins: plugin.planner.0" in session.system_prompt
    assert "Use planner plugin guidance." in session.system_prompt

    asyncio.run(run_slash(state, "/plugins disable planner", emitted))

    assert emitted[3] == {"type": "notice", "message": "plugin disabled: planner"}
    assert emitted[4]["type"] == "plugins"
    assert "available" in dict(emitted[4]["plugins"])["planner"]
    assert emitted[5]["type"] == "tools"
    assert state.active_tools == []
    assert runtime.enabled_tools == []
    persisted = asyncio.run(state_store.load_for_scope("tenant", user_id="user", agent_id="coder", workspace_id="workspace"))
    assert persisted.enabled_plugins == []


def test_ndjson_bridge_installs_and_uninstalls_local_plugin(tmp_path):
    source = tmp_path / "source-plugin"
    manifest_dir = source / ".codex-plugin"
    manifest_dir.mkdir(parents=True)
    (manifest_dir / "plugin.json").write_text(
        '{"name":"planner","version":"0.1.0","description":"Planning plugin"}',
        encoding="utf-8",
    )
    state = ndjson.BridgeState(
        args=SimpleNamespace(),
        profile="coding",
        permission="guarded",
        active_workspace=tmp_path,
        active_tools=[],
        permission_mode="auto",
        approval_tools=[],
        settings=SimpleNamespace(server=SimpleNamespace(ROOT_PATH=str(tmp_path))),
        persistence=SimpleNamespace(),
        model_profiles=[],
        session=SimpleNamespace(),
        session_store=TerminalSessionStore(tmp_path / "sessions"),
        session_id="session-test",
        event_offsets={},
    )
    emitted = []

    asyncio.run(run_slash(state, f"/plugins install {source}", emitted))

    installed = tmp_path / ".agents" / "plugins" / "planner" / ".codex-plugin" / "plugin.json"
    assert emitted[0] == {"type": "notice", "message": "plugin installed: planner"}
    assert emitted[1]["type"] == "plugins"
    assert "Planning plugin" in dict(emitted[1]["plugins"])["planner"]
    assert installed.exists()

    asyncio.run(run_slash(state, "/plugins uninstall planner", emitted))

    assert emitted[2] == {"type": "notice", "message": "plugin uninstalled: planner"}
    assert emitted[3] == {"type": "plugins", "plugins": [["plugins", "none configured"]]}
    assert not installed.exists()


def test_ndjson_bridge_manages_terminal_memory(tmp_path):
    memories = InMemoryMemoryStore()
    state = ndjson.BridgeState(
        args=SimpleNamespace(),
        profile="coding",
        permission="guarded",
        active_workspace=tmp_path,
        active_tools=[],
        permission_mode="auto",
        approval_tools=[],
        settings=SimpleNamespace(),
        persistence=SimpleNamespace(memories=memories),
        model_profiles=[],
        session=SimpleNamespace(
            workspace=SimpleNamespace(
                tenant_id="tenant",
                user_id="user",
                agent_id="terminal",
                workspace_id="workspace",
            )
        ),
        session_store=TerminalSessionStore(tmp_path / "sessions"),
        session_id="session-test",
        event_offsets={},
    )
    emitted = []

    asyncio.run(run_slash(state, "/memory add workspace prefer terse implementation notes", emitted))

    assert emitted[0]["type"] == "notice"
    assert emitted[0]["message"].startswith("memory saved: ")
    assert emitted[1]["type"] == "memory"
    memory_id = emitted[1]["memory"][0][0]
    assert "workspace · prefer terse implementation notes" in emitted[1]["memory"][0][1]
    records = asyncio.run(memories.list_for_context("tenant", "user", agent_id="terminal", workspace_id="workspace"))
    assert records[0].scope == MemoryScope.WORKSPACE
    assert records[0].metadata["source"] == "terminal"

    asyncio.run(run_slash(state, f"/memory edit {memory_id} prefer direct implementation notes", emitted))

    assert emitted[2]["type"] == "notice"
    assert emitted[2]["message"] == "memory updated: %s" % memory_id
    assert emitted[3]["type"] == "memory"
    assert "prefer direct implementation notes" in emitted[3]["memory"][0][1]

    asyncio.run(run_slash(state, f"/memory forget {memory_id}", emitted))

    assert emitted[4]["type"] == "notice"
    assert emitted[4]["message"] == "memory forgotten: %s" % memory_id
    assert emitted[5]["type"] == "memory"
    assert emitted[5]["memory"] == [["memory", "none visible to this session"]]


def test_terminal_persistence_survives_memory_command_reopen(monkeypatch, tmp_path):
    db_path = tmp_path / "terminal.db"
    monkeypatch.setenv("AGENTS_TERMINAL_DB_PATH", str(db_path))
    settings = settings_for_terminal("coding", None, workspace_root=tmp_path)
    persistence = create_terminal_persistence(settings, workspace_path=str(tmp_path))
    state = ndjson.BridgeState(
        args=SimpleNamespace(),
        profile="coding",
        permission="guarded",
        active_workspace=tmp_path,
        active_tools=[],
        permission_mode="auto",
        approval_tools=[],
        settings=settings,
        persistence=persistence,
        model_profiles=[],
        session=SimpleNamespace(
            workspace=SimpleNamespace(
                tenant_id="tenant",
                user_id="user",
                agent_id="terminal",
                workspace_id="workspace",
            )
        ),
        session_store=TerminalSessionStore(tmp_path / "sessions"),
        session_id="session-test",
        event_offsets={},
    )
    emitted = []

    asyncio.run(run_slash(state, "/memory add workspace persist terminal memory", emitted))
    reopened = create_terminal_persistence(settings, workspace_path=str(tmp_path))
    records = asyncio.run(reopened.memories.list_for_context("tenant", "user", agent_id="terminal", workspace_id="workspace"))

    assert db_path.exists()
    assert records[0].content == "persist terminal memory"
    assert records[0].scope == MemoryScope.WORKSPACE


def test_ndjson_bridge_enables_skill_for_current_session(tmp_path):
    skills_dir = tmp_path / "skills"
    prompts_dir = tmp_path / "prompts"
    skills_dir.mkdir()
    prompts_dir.mkdir()
    (prompts_dir / "focus.md").write_text("Focus on tool management.", encoding="utf-8")
    (skills_dir / "focus.json").write_text(
        '{"name":"focus","description":"Focus skill","prompt_fragments":["prompts/focus.md"],"tools":["echo"]}',
        encoding="utf-8",
    )
    tools = ToolRegistry()
    tools.register("echo", "Echo", {}, lambda text: text)
    runtime = AgentRuntime(
        model_client=ScriptedModelClient([]),
        tools=tools,
        protocol="scripted",
        model="skills",
        enabled_tools=[],
    )
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="coder",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path)
    state_store = InMemorySessionStateStore()
    tool_context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
        session_state_store=state_store,
    )
    session = AgentSession(runtime=runtime, system_prompt="Base prompt.", workspace=workspace, tool_context=tool_context)
    state = ndjson.BridgeState(
        args=SimpleNamespace(),
        profile="coding",
        permission="guarded",
        active_workspace=tmp_path,
        active_tools=[],
        permission_mode="auto",
        approval_tools=[],
        settings=SimpleNamespace(agent=SimpleNamespace(SKILLS=""), server=SimpleNamespace(ROOT_PATH=str(tmp_path))),
        persistence=SimpleNamespace(),
        model_profiles=[],
        session=session,
        session_store=TerminalSessionStore(tmp_path / "sessions"),
        session_id="session-test",
        event_offsets={},
    )
    emitted = []

    asyncio.run(run_slash(state, "/skills use focus", emitted))

    assert emitted[0] == {"type": "notice", "message": "skill enabled: focus"}
    assert emitted[1]["type"] == "skills"
    assert "configured" in emitted[1]["skills"][0][1]
    assert state.active_tools == ["echo"]
    assert runtime.enabled_tools == ["echo"]
    persisted = asyncio.run(state_store.load_for_scope("tenant", user_id="user", agent_id="coder", workspace_id="workspace"))
    assert persisted.enabled_skills == ["focus"]
    assert "## skills: skill.focus.0" in session.system_prompt
    assert "Focus on tool management." in session.system_prompt
    assert any(item.id == "skill.focus.0" and item.included for item in session.context_trace)

    asyncio.run(run_slash(state, "/skills disable focus", emitted))

    assert emitted[2] == {"type": "notice", "message": "skill disabled: focus"}
    assert emitted[3]["type"] == "skills"
    assert "available" in emitted[3]["skills"][0][1]
    assert emitted[4]["type"] == "tools"
    assert state.active_tools == []
    assert runtime.enabled_tools == []
    persisted = asyncio.run(state_store.load_for_scope("tenant", user_id="user", agent_id="coder", workspace_id="workspace"))
    assert persisted.enabled_skills == []


def test_ndjson_bridge_lists_rich_tool_catalog(tmp_path):
    tools = ToolRegistry()
    tools.register("filesystem.read", "Read a file from the current workspace.", {}, lambda: "ok", metadata={"risk": "low"})
    tools.register(
        "shell.run",
        "Run a shell command with sandbox policy checks.",
        {},
        lambda: "ok",
        metadata={"risk": "high", "requires_process": True, "writes_files": True},
    )
    tools.register(
        "skill.search",
        "Search installed skill manifests.",
        {},
        lambda: "ok",
        metadata={"source": "skill", "risk": "medium"},
    )
    state = ndjson.BridgeState(
        args=SimpleNamespace(),
        profile="coding",
        permission="guarded",
        active_workspace=tmp_path,
        active_tools=["filesystem.read", "shell.run", "skill.search"],
        permission_mode="auto",
        approval_tools=[],
        settings=SimpleNamespace(),
        persistence=SimpleNamespace(),
        model_profiles=[],
        session=SimpleNamespace(runtime=SimpleNamespace(tools=tools)),
        session_store=TerminalSessionStore(tmp_path / "sessions"),
        session_id="session-test",
        event_offsets={},
    )
    emitted = []

    asyncio.run(run_slash(state, "/tools", emitted))

    assert emitted[0]["type"] == "tools"
    rows = dict(emitted[0]["tools"])
    assert "enabled · builtin · risk low" in rows["filesystem.read"]
    assert "Read a file" in rows["filesystem.read"]
    assert "risk high" in rows["shell.run"]
    assert "process" in rows["shell.run"]
    assert "writes" in rows["shell.run"]
    assert "enabled · skill · risk medium" in rows["skill.search"]


def test_ndjson_bridge_explains_permission_sources(tmp_path):
    state = ndjson.BridgeState(
        args=SimpleNamespace(),
        profile="coding",
        permission="guarded",
        active_workspace=tmp_path,
        active_tools=["filesystem.read", "filesystem.write", "shell.run"],
        permission_mode="auto",
        approval_tools=["filesystem.write", "shell.run"],
        settings=SimpleNamespace(
            agent=SimpleNamespace(
                SANDBOX_PROFILE="coding",
                SANDBOX_PROVIDER="local",
                SANDBOX_ALLOWED_COMMANDS="git,python3",
            ),
            mcp=SimpleNamespace(EXECUTION_MODE="trusted_control_plane"),
        ),
        persistence=SimpleNamespace(),
        model_profiles=[],
        session=SimpleNamespace(),
        session_store=TerminalSessionStore(tmp_path / "sessions"),
        session_id="session-test",
        event_offsets={},
    )
    emitted = []

    asyncio.run(run_slash(state, "/permissions", emitted))

    assert emitted[0]["type"] == "permissions"
    rows = dict(emitted[0]["permissions"])
    assert rows["profile"] == "guarded"
    assert rows["runtime_mode"] == "auto"
    assert rows["approval_required"] == "filesystem.write, shell.run"
    assert rows["high_risk_tools"] == "shell.run"
    assert rows["sandbox_profile"] == "coding"
    assert rows["sandbox_allowed_commands"] == "git, python3"
    assert rows["mcp_execution_mode"] == "trusted_control_plane"

    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="terminal",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    spec = AgentSpec.from_overrides(
        tenant_id="tenant",
        user_id="user",
        agent_id="terminal",
        workspace_id="workspace",
        workspace_path=str(tmp_path),
        approval_required_tools=["shell.run"],
    )
    state.session = SimpleNamespace(
        tool_context=ToolRuntimeContext(
            workspace=workspace,
            sandbox=SandboxPolicy.for_workspace(workspace.path),
            agent_spec=spec,
            settings=state.settings,
        )
    )
    asyncio.run(run_slash(state, "/permissions sources", emitted))

    assert emitted[1]["type"] == "permissions"
    source_rows = dict(emitted[1]["permissions"])
    assert source_rows["agent_spec:ask"] == "shell.run"
    assert ["settings.agent", "SANDBOX_ALLOWED_COMMANDS=git,python3"] in emitted[1]["permissions"]


def test_ndjson_bridge_switches_runtime_permission_policy(tmp_path):
    tools = ToolRegistry()
    tools.register("echo", "Echo", {}, lambda text: text)
    runtime = AgentRuntime(
        model_client=ScriptedModelClient([]),
        tools=tools,
        protocol="scripted",
        model="permission",
        enabled_tools=["echo"],
    )
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="coder",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    tool_context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=SandboxPolicy.for_workspace(workspace.path),
        agent_spec=AgentSpec.from_overrides(
            tenant_id="tenant",
            user_id="user",
            agent_id="coder",
            workspace_id="workspace",
            workspace_path=str(tmp_path),
            enabled_tools=["echo"],
        ),
    )
    state = ndjson.BridgeState(
        args=SimpleNamespace(),
        profile="coding",
        permission="auto",
        active_workspace=tmp_path,
        active_tools=["echo"],
        permission_mode="auto",
        approval_tools=[],
        settings=SimpleNamespace(
            agent=SimpleNamespace(SANDBOX_PROFILE="coding", SANDBOX_PROVIDER="local", SANDBOX_ALLOWED_COMMANDS=""),
            mcp=SimpleNamespace(EXECUTION_MODE=""),
        ),
        persistence=SimpleNamespace(),
        model_profiles=[],
        session=AgentSession(
            runtime=runtime,
            workspace=workspace,
            tool_context=tool_context,
        ),
        session_store=TerminalSessionStore(tmp_path / "sessions"),
        session_id="session-test",
        event_offsets={},
    )
    emitted = []

    asyncio.run(run_slash(state, "/permissions ask", emitted))
    ask_decision = asyncio.run(runtime.tool_orchestrator.permission_policy.authorize(ToolCall(id="call-1", name="echo", arguments={})))
    asyncio.run(run_slash(state, "/permissions deny", emitted))
    deny_decision = asyncio.run(runtime.tool_orchestrator.permission_policy.authorize(ToolCall(id="call-2", name="echo", arguments={})))
    asyncio.run(run_slash(state, "/permissions auto", emitted))
    asyncio.run(run_slash(state, "/permissions deny echo", emitted))
    rule_denied = asyncio.run(runtime.tool_orchestrator.permission_policy.authorize(ToolCall(id="call-3", name="echo", arguments={})))
    asyncio.run(run_slash(state, "/permissions remove deny echo", emitted))
    rule_removed = asyncio.run(runtime.tool_orchestrator.permission_policy.authorize(ToolCall(id="call-4", name="echo", arguments={})))

    assert emitted[0] == {"type": "notice", "message": "permission switched: ask -> ask"}
    assert emitted[1]["type"] == "permissions"
    assert ask_decision.requires_approval is True
    assert ask_decision.allowed is False
    assert emitted[2] == {"type": "notice", "message": "permission switched: deny -> deny"}
    assert deny_decision.allowed is False
    assert deny_decision.requires_approval is False
    assert emitted[4] == {"type": "notice", "message": "permission switched: auto -> auto"}
    assert emitted[6] == {"type": "notice", "message": "permission rule added: deny echo"}
    assert rule_denied.allowed is False
    assert rule_denied.metadata["rule"] == "deny"
    assert emitted[8] == {"type": "notice", "message": "permission rule removed: echo"}
    assert rule_removed.allowed is True


def test_ndjson_bridge_summarizes_compiled_prompt(tmp_path):
    state = ndjson.BridgeState(
        args=SimpleNamespace(),
        profile="coding",
        permission="guarded",
        active_workspace=tmp_path,
        active_tools=[],
        permission_mode="auto",
        approval_tools=[],
        settings=SimpleNamespace(),
        persistence=SimpleNamespace(),
        model_profiles=[],
        session=SimpleNamespace(
            system_prompt="## system: system.user_configured\nBase prompt.\n\n## skills: skill.focus.0\nFocus.",
            context_trace=[
                SimpleNamespace(id="system.user_configured", layer=SimpleNamespace(value="system"), included=True),
                SimpleNamespace(id="skill.focus.0", layer=SimpleNamespace(value="skills"), included=True),
                SimpleNamespace(id="memory.old", layer=SimpleNamespace(value="memory"), included=False),
            ],
        ),
        session_store=TerminalSessionStore(tmp_path / "sessions"),
        session_id="session-test",
        event_offsets={},
    )
    emitted = []

    asyncio.run(run_slash(state, "/prompt", emitted))

    assert emitted[0]["type"] == "prompt"
    rows = dict(emitted[0]["prompt"])
    assert rows["included_fragments"] == "2"
    assert rows["dropped_fragments"] == "1"
    assert rows["layers"] == "skills:1, system:1"
    assert rows["dropped"] == "memory.old"
    assert "Base prompt" in rows["preview"]


def test_ndjson_bridge_shows_and_updates_session_prompt(tmp_path):
    runtime = AgentRuntime(
        model_client=ScriptedModelClient([]),
        tools=ToolRegistry(),
        protocol="scripted",
        model="prompt",
    )
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="terminal",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    context = ToolRuntimeContext(workspace=workspace, sandbox=SandboxPolicy.for_workspace(workspace.path, allow_file_write=True))
    session = AgentSession(runtime=runtime, system_prompt="Original prompt.", workspace=workspace, tool_context=context)
    state = ndjson.BridgeState(
        args=SimpleNamespace(),
        profile="coding",
        permission="guarded",
        active_workspace=tmp_path,
        active_tools=[],
        permission_mode="auto",
        approval_tools=[],
        settings=SimpleNamespace(),
        persistence=SimpleNamespace(),
        model_profiles=[],
        session=session,
        session_store=TerminalSessionStore(tmp_path / "sessions"),
        session_id="session-test",
        event_offsets={},
    )
    emitted = []

    asyncio.run(run_slash(state, "/prompt show", emitted))
    asyncio.run(run_slash(state, "/prompt set Updated current session prompt.", emitted))

    assert emitted[0] == {"type": "prompt", "prompt": [["system_prompt", "Original prompt."]]}
    assert emitted[1] == {"type": "notice", "message": "session prompt updated"}
    assert emitted[2]["type"] == "prompt"
    assert session.system_prompt == "Updated current session prompt."
    assert session.messages[0].content_text() == "Updated current session prompt."
    saved = state.session_store.load("session-test")
    assert saved is not None
    assert saved.messages[0].content_text() == "Updated current session prompt."


def test_ndjson_bridge_saves_uses_and_deletes_prompt_templates(tmp_path):
    runtime = AgentRuntime(
        model_client=ScriptedModelClient([]),
        tools=ToolRegistry(),
        protocol="scripted",
        model="prompt",
    )
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="terminal",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    context = ToolRuntimeContext(workspace=workspace, sandbox=SandboxPolicy.for_workspace(workspace.path, allow_file_write=True))
    session = AgentSession(runtime=runtime, system_prompt="Original prompt.", workspace=workspace, tool_context=context)
    state = ndjson.BridgeState(
        args=SimpleNamespace(),
        profile="coding",
        permission="guarded",
        active_workspace=tmp_path,
        active_tools=[],
        permission_mode="auto",
        approval_tools=[],
        settings=SimpleNamespace(),
        persistence=SimpleNamespace(),
        model_profiles=[],
        session=session,
        session_store=TerminalSessionStore(tmp_path / "sessions"),
        session_id="session-test",
        event_offsets={},
    )
    emitted = []

    asyncio.run(run_slash(state, "/prompt save reviewer Review carefully before editing.", emitted))
    asyncio.run(run_slash(state, "/prompt render reviewer src/agents", emitted))
    asyncio.run(run_slash(state, "/prompt use reviewer", emitted))
    asyncio.run(run_slash(state, "/prompt delete reviewer", emitted))

    template_path = tmp_path / ".agents" / "prompts" / "reviewer.md"
    assert emitted[0] == {"type": "notice", "message": "prompt saved: reviewer"}
    assert emitted[1]["type"] == "prompt"
    assert dict(emitted[1]["prompt"])["reviewer"] == "Review carefully before editing."
    assert emitted[2] == {"type": "prompt", "prompt": [["template", "reviewer"], ["prompt", "Review carefully before editing."]]}
    assert emitted[3] == {"type": "notice", "message": "prompt loaded: reviewer"}
    assert emitted[4]["type"] == "prompt"
    assert session.system_prompt == "Review carefully before editing."
    assert session.messages[0].content_text() == "Review carefully before editing."
    assert emitted[5] == {"type": "notice", "message": "prompt deleted: reviewer"}
    assert emitted[6] == {"type": "prompt", "prompt": [["templates", "none"]]}
    assert not template_path.exists()


def test_ndjson_bridge_prompt_save_respects_runtime_deny_policy(tmp_path):
    tools = ToolRegistry()
    tools.register("prompt.save", "Save prompt template.", {}, lambda name, content, overwrite=False: {"name": name})
    runtime = AgentRuntime(
        model_client=ScriptedModelClient([]),
        tools=tools,
        protocol="scripted",
        model="prompt",
        permission_policy=StaticToolPermissionPolicy(denied_tools={"prompt.save"}),
    )
    state = ndjson.BridgeState(
        args=SimpleNamespace(),
        profile="coding",
        permission="guarded",
        active_workspace=tmp_path,
        active_tools=[],
        permission_mode="auto",
        approval_tools=[],
        settings=SimpleNamespace(),
        persistence=SimpleNamespace(),
        model_profiles=[],
        session=SimpleNamespace(runtime=runtime, system_prompt="Base prompt."),
        session_store=TerminalSessionStore(tmp_path / "sessions"),
        session_id="session-test",
        event_offsets={},
    )
    emitted = []

    asyncio.run(run_slash(state, "/prompt save reviewer Review carefully before editing.", emitted))

    assert emitted[0]["type"] == "error"
    assert "prompt save failed: tool denied by policy" in emitted[0]["message"]
    assert not (tmp_path / ".agents" / "prompts" / "reviewer.md").exists()


def test_ndjson_bridge_prompt_save_explicit_slash_auto_approves_ask_policy(tmp_path):
    def save_prompt(name, content, overwrite=False):
        target = tmp_path / ".agents" / "prompts" / ("%s.md" % name)
        target.parent.mkdir(parents=True, exist_ok=True)
        text = str(content or "")
        target.write_text(text, encoding="utf-8")
        return {"name": name, "path": str(target), "bytes": len(text.encode("utf-8"))}

    tools = ToolRegistry()
    tools.register("prompt.save", "Save prompt template.", {}, save_prompt)
    runtime = AgentRuntime(
        model_client=ScriptedModelClient([]),
        tools=tools,
        protocol="scripted",
        model="prompt",
        permission_policy=StaticToolPermissionPolicy(approval_required_tools={"prompt.save"}),
    )
    state = ndjson.BridgeState(
        args=SimpleNamespace(),
        profile="coding",
        permission="guarded",
        active_workspace=tmp_path,
        active_tools=[],
        permission_mode="ask",
        approval_tools=["prompt.save"],
        settings=SimpleNamespace(),
        persistence=SimpleNamespace(),
        model_profiles=[],
        session=SimpleNamespace(runtime=runtime, system_prompt="Base prompt."),
        session_store=TerminalSessionStore(tmp_path / "sessions"),
        session_id="session-test",
        event_offsets={},
    )
    emitted = []

    asyncio.run(run_slash(state, "/prompt save reviewer Review carefully before editing.", emitted))

    assert emitted[0] == {"type": "notice", "message": "prompt saved: reviewer"}
    assert emitted[1]["type"] == "prompt"
    assert dict(emitted[1]["prompt"])["reviewer"] == "Review carefully before editing."


def test_ndjson_bridge_lists_session_agents_and_tasks(tmp_path):
    profiles = InMemoryAgentProfileStore()
    tasks = InMemoryTaskStore()
    spec = AgentSpec.from_overrides(
        protocol="openai-chat",
        model="gpt-test",
        tenant_id="tenant",
        user_id="user",
        agent_id="coder",
        workspace_id="workspace",
        permission_profile="ask",
        skills=["focus"],
    )

    async def seed():
        await profiles.save(AgentProfile.from_spec(spec, name="Coder"))
        return await tasks.create_task(spec, title="Implement task system", input="work")

    task = asyncio.run(seed())
    state = ndjson.BridgeState(
        args=SimpleNamespace(),
        profile="coding",
        permission="guarded",
        active_workspace=tmp_path,
        active_tools=[],
        permission_mode="auto",
        approval_tools=[],
        settings=SimpleNamespace(),
        persistence=SimpleNamespace(agent_profiles=profiles, tasks=tasks),
        model_profiles=[],
        session=SimpleNamespace(
            runtime=SimpleNamespace(protocol="openai-chat", model="gpt-test"),
            messages=[Message.from_text("system", "prompt"), Message.from_text("user", "hello")],
            _estimate_tokens=lambda messages: 12,
            workspace=SimpleNamespace(
                tenant_id="tenant",
                user_id="user",
                agent_id="coder",
                workspace_id="workspace",
            ),
        ),
        session_store=TerminalSessionStore(tmp_path / "sessions"),
        session_id="session-test",
        event_offsets={},
    )
    emitted = []

    asyncio.run(run_slash(state, "/session", emitted))
    asyncio.run(run_slash(state, "/agents", emitted))
    asyncio.run(run_slash(state, "/tasks", emitted))

    session_rows = dict(emitted[0]["session"])
    assert emitted[0]["type"] == "session"
    assert session_rows["session"] == "session-test"
    assert session_rows["messages"] == "1"
    assert session_rows["context_tokens"] == "12"
    assert emitted[1]["type"] == "agents"
    agent_rows = dict(emitted[1]["agents"])
    assert "Coder" in agent_rows["coder"]
    assert "model openai-chat/gpt-test" in agent_rows["coder"]
    assert "skills focus" in agent_rows["coder"]
    assert emitted[2]["type"] == "tasks"
    task_rows = dict(emitted[2]["tasks"])
    task_key = task.task_id.replace("task_", "", 1)[:12]
    assert "created" in task_rows[task_key]
    assert "Implement task system" in task_rows[task_key]


def test_ndjson_bridge_creates_and_cancels_terminal_tasks(tmp_path):
    tasks = InMemoryTaskStore()
    state = ndjson.BridgeState(
        args=SimpleNamespace(),
        profile="coding",
        permission="guarded",
        active_workspace=tmp_path,
        active_tools=["filesystem.read"],
        permission_mode="auto",
        approval_tools=["filesystem.write"],
        settings=SimpleNamespace(),
        persistence=SimpleNamespace(tasks=tasks),
        model_profiles=[],
        session=SimpleNamespace(
            runtime=SimpleNamespace(protocol="openai-chat", model="gpt-test"),
            workspace=SimpleNamespace(
                tenant_id="tenant",
                user_id="user",
                agent_id="coder",
                workspace_id="workspace",
                path=tmp_path,
            ),
        ),
        session_store=TerminalSessionStore(tmp_path / "sessions"),
        session_id="session-test",
        event_offsets={},
    )
    emitted = []

    asyncio.run(run_slash(state, "/tasks create Build tool manager -- Add plugin controls", emitted))

    assert emitted[0]["type"] == "notice"
    task_id = emitted[0]["message"].replace("task created: ", "")
    assert emitted[1]["type"] == "tasks"
    task_rows = dict(emitted[1]["tasks"])
    assert "Build tool manager" in task_rows[task_id]
    records = asyncio.run(tasks.list_tasks("tenant", user_id="user", agent_id="coder"))
    assert records[0].input == "Add plugin controls"
    assert records[0].metadata["source"] == "terminal"
    assert records[0].to_agent_spec().enabled_tools == ["filesystem.read"]
    assert records[0].to_agent_spec().tool_permissions.approval_required_tools == ["filesystem.write"]

    asyncio.run(run_slash(state, f"/tasks cancel {task_id}", emitted))

    assert emitted[2] == {"type": "notice", "message": "task canceled: %s" % task_id}
    assert emitted[3]["type"] == "tasks"
    canceled = asyncio.run(tasks.load_task(records[0].task_id))
    assert canceled is not None
    assert canceled.status == TaskStatus.CANCELED


def test_ndjson_bridge_runs_terminal_task_with_current_session(tmp_path):
    tasks = InMemoryTaskStore()
    tools = ToolRegistry()
    runtime = AgentRuntime(
        model_client=ScriptedModelClient([ModelResponse(message=Message.from_text("assistant", "task done"))]),
        tools=tools,
        protocol="scripted",
        model="task-runner",
        enabled_tools=[],
    )
    session = AgentSession(
        runtime=runtime,
        system_prompt="Task runner.",
        workspace=SimpleNamespace(
            tenant_id="tenant",
            user_id="user",
            agent_id="coder",
            workspace_id="workspace",
            path=tmp_path,
        ),
    )
    state = ndjson.BridgeState(
        args=SimpleNamespace(),
        profile="coding",
        permission="guarded",
        active_workspace=tmp_path,
        active_tools=[],
        permission_mode="auto",
        approval_tools=[],
        settings=SimpleNamespace(),
        persistence=SimpleNamespace(tasks=tasks),
        model_profiles=[],
        session=session,
        session_store=TerminalSessionStore(tmp_path / "sessions"),
        session_id="session-test",
        event_offsets={},
    )
    spec = AgentSpec.from_overrides(tenant_id="tenant", user_id="user", agent_id="coder", workspace_id="workspace")
    task = asyncio.run(tasks.create_task(spec, title="Run task", input="Do the task"))
    task_key = task.task_id.replace("task_", "", 1)[:12]
    emitted = []

    asyncio.run(run_slash(state, f"/tasks run {task_key}", emitted))

    assert emitted[0]["type"] == "turn_started"
    assert emitted[1]["type"] == "runtime_event"
    assert emitted[1]["event"]["type"] == "model_message"
    assert emitted[2]["type"] == "turn_finished"
    assert emitted[2]["status"] == "finished"
    assert emitted[3]["type"] == "tasks"
    finished = asyncio.run(tasks.load_task(task.task_id))
    assert finished is not None
    assert finished.status == TaskStatus.FINISHED
    steps = asyncio.run(tasks.list_steps(task.task_id))
    assert len(steps) == 1
    assert steps[0].status == TaskStepStatus.SUCCEEDED
    assert steps[0].output == "task done"
    assert session.messages[-1].content_text() == "task done"


def test_ndjson_bridge_starts_terminal_task_in_background(tmp_path):
    async def execute():
        tasks = InMemoryTaskStore()
        started = asyncio.Event()
        release = asyncio.Event()

        class BackgroundSession:
            async def send(self, text, run_id=None, task_id=None):
                started.set()
                await release.wait()
                return AgentResult(
                    content="background done",
                    messages=[Message.from_text("user", text), Message.from_text("assistant", "background done")],
                    events=[RuntimeEvent(type="model_message", name="assistant", payload={"content": "background done"})],
                )

            async def aclose(self):
                pass

        class BackgroundFactory:
            async def create(self, task):
                return BackgroundSession()

        state = ndjson.BridgeState(
            args=SimpleNamespace(),
            profile="coding",
            permission="guarded",
            active_workspace=tmp_path,
            active_tools=[],
            permission_mode="auto",
            approval_tools=[],
            settings=SimpleNamespace(),
            persistence=SimpleNamespace(tasks=tasks),
            model_profiles=[],
            session=SimpleNamespace(
                runtime=SimpleNamespace(protocol="openai-chat", model="gpt-test"),
                workspace=SimpleNamespace(
                    tenant_id="tenant",
                    user_id="user",
                    agent_id="coder",
                    workspace_id="workspace",
                    path=tmp_path,
                ),
            ),
            session_store=TerminalSessionStore(tmp_path / "sessions"),
            session_id="session-test",
            event_offsets={},
        )
        state.task_session_factory = BackgroundFactory()
        spec = AgentSpec.from_overrides(tenant_id="tenant", user_id="user", agent_id="coder", workspace_id="workspace")
        task = await tasks.create_task(spec, title="Background task", input="Do background work")
        task_key = task.task_id.replace("task_", "", 1)[:12]
        emitted = []

        await run_slash(state, f"/tasks start {task_key}", emitted)
        handle = state.background_tasks[task.task_id]
        await started.wait()
        running = await tasks.load_task(task.task_id)
        release.set()
        await handle
        finished = await tasks.load_task(task.task_id)
        steps = await tasks.list_steps(task.task_id)
        return emitted, running, finished, steps

    emitted, running, finished, steps = asyncio.run(execute())

    assert emitted[0] == {"type": "notice", "message": "task started in background: %s" % steps[0].task_id.replace("task_", "", 1)[:12]}
    assert running.status == TaskStatus.RUNNING
    assert finished.status == TaskStatus.FINISHED
    assert steps[0].status == TaskStepStatus.SUCCEEDED
    assert steps[0].output == "background done"
    assert emitted[-2]["message"].startswith("background task finished:")
    assert emitted[-1]["type"] == "tasks"


def test_ndjson_bridge_cancel_stops_background_terminal_task(tmp_path):
    async def execute():
        tasks = InMemoryTaskStore()
        started = asyncio.Event()

        class BlockingSession:
            async def send(self, text, run_id=None, task_id=None):
                started.set()
                await asyncio.Event().wait()

            async def aclose(self):
                pass

        class BlockingFactory:
            async def create(self, task):
                return BlockingSession()

        state = ndjson.BridgeState(
            args=SimpleNamespace(),
            profile="coding",
            permission="guarded",
            active_workspace=tmp_path,
            active_tools=[],
            permission_mode="auto",
            approval_tools=[],
            settings=SimpleNamespace(),
            persistence=SimpleNamespace(tasks=tasks),
            model_profiles=[],
            session=SimpleNamespace(
                runtime=SimpleNamespace(protocol="openai-chat", model="gpt-test"),
                workspace=SimpleNamespace(
                    tenant_id="tenant",
                    user_id="user",
                    agent_id="coder",
                    workspace_id="workspace",
                    path=tmp_path,
                ),
            ),
            session_store=TerminalSessionStore(tmp_path / "sessions"),
            session_id="session-test",
            event_offsets={},
        )
        state.task_session_factory = BlockingFactory()
        spec = AgentSpec.from_overrides(tenant_id="tenant", user_id="user", agent_id="coder", workspace_id="workspace")
        task = await tasks.create_task(spec, title="Cancel background", input="Block")
        task_key = task.task_id.replace("task_", "", 1)[:12]
        emitted = []

        await run_slash(state, f"/tasks start {task_key}", emitted)
        handle = state.background_tasks[task.task_id]
        await started.wait()
        await run_slash(state, f"/tasks cancel {task_key}", emitted)
        await handle
        canceled = await tasks.load_task(task.task_id)
        steps = await tasks.list_steps(task.task_id)
        return emitted, canceled, steps

    emitted, canceled, steps = asyncio.run(execute())

    assert canceled.status == TaskStatus.CANCELED
    assert steps[0].status == TaskStepStatus.CANCELED
    assert any(event.get("message", "").startswith("background task canceled:") for event in emitted if event["type"] == "notice")


def test_ndjson_bridge_queues_and_drains_terminal_tasks(tmp_path):
    tasks = InMemoryTaskStore()
    task_queue = InMemoryTaskQueue()
    tools = ToolRegistry()
    runtime = AgentRuntime(
        model_client=ScriptedModelClient([
            ModelResponse(message=Message.from_text("assistant", "first done")),
            ModelResponse(message=Message.from_text("assistant", "second done")),
        ]),
        tools=tools,
        protocol="scripted",
        model="task-runner",
        enabled_tools=[],
    )
    session = AgentSession(
        runtime=runtime,
        system_prompt="Task runner.",
        workspace=SimpleNamespace(
            tenant_id="tenant",
            user_id="user",
            agent_id="coder",
            workspace_id="workspace",
            path=tmp_path,
        ),
    )
    state = ndjson.BridgeState(
        args=SimpleNamespace(),
        profile="coding",
        permission="guarded",
        active_workspace=tmp_path,
        active_tools=[],
        permission_mode="auto",
        approval_tools=[],
        settings=SimpleNamespace(),
        persistence=SimpleNamespace(tasks=tasks, task_queue=task_queue),
        model_profiles=[],
        session=session,
        session_store=TerminalSessionStore(tmp_path / "sessions"),
        session_id="session-test",
        event_offsets={},
    )
    spec = AgentSpec.from_overrides(tenant_id="tenant", user_id="user", agent_id="coder", workspace_id="workspace")
    first = asyncio.run(tasks.create_task(spec, title="First task", input="Do one"))
    second = asyncio.run(tasks.create_task(spec, title="Second task", input="Do two"))
    first_key = first.task_id.replace("task_", "", 1)[:12]
    second_key = second.task_id.replace("task_", "", 1)[:12]
    emitted = []

    asyncio.run(run_slash(state, f"/tasks enqueue {first_key}", emitted))
    asyncio.run(run_slash(state, f"/tasks enqueue {second_key}", emitted))
    asyncio.run(run_slash(state, "/tasks queue", emitted))
    asyncio.run(run_slash(state, "/tasks drain 1", emitted))

    queue_events = [event for event in emitted if event["type"] == "task_queue"]
    assert dict(queue_events[0]["queue"])[first_key] == "#1 · First task · created"
    assert dict(queue_events[1]["queue"])[second_key] == "#2 · Second task · created"
    assert queue_events[-1]["queue"] == [(second_key, "#1 · Second task · created")]
    finished_first = asyncio.run(tasks.load_task(first.task_id))
    queued_second = asyncio.run(tasks.load_task(second.task_id))
    assert finished_first is not None
    assert finished_first.status == TaskStatus.FINISHED
    assert queued_second is not None
    assert queued_second.status == TaskStatus.CREATED

    asyncio.run(run_slash(state, "/tasks drain", emitted))

    assert [event["message"] for event in emitted if event["type"] == "notice" and event["message"].startswith("task queue drained")] == [
        "task queue drained: 1",
        "task queue drained: 1",
    ]
    assert [event for event in emitted if event["type"] == "task_queue"][-1]["queue"] == [("queue", "empty")]
    finished_second = asyncio.run(tasks.load_task(second.task_id))
    assert finished_second is not None
    assert finished_second.status == TaskStatus.FINISHED


def test_ndjson_bridge_saves_current_session_as_agent_profile(tmp_path):
    profiles = InMemoryAgentProfileStore()
    state = ndjson.BridgeState(
        args=SimpleNamespace(),
        profile="coding",
        permission="guarded",
        active_workspace=tmp_path,
        active_tools=["filesystem.read", "shell.run"],
        permission_mode="auto",
        approval_tools=["shell.run"],
        settings=SimpleNamespace(),
        persistence=SimpleNamespace(agent_profiles=profiles),
        model_profiles=[],
        session=SimpleNamespace(
            runtime=SimpleNamespace(protocol="openai-chat", model="gpt-test"),
            workspace=SimpleNamespace(
                tenant_id="tenant",
                user_id="user",
                agent_id="coder",
                workspace_id="workspace",
                path=tmp_path,
            ),
        ),
        session_store=TerminalSessionStore(tmp_path / "sessions"),
        session_id="session-test",
        event_offsets={},
    )
    emitted = []

    asyncio.run(run_slash(state, "/agents save reviewer Reviewer Agent", emitted))

    assert emitted[0] == {"type": "notice", "message": "agent saved: reviewer"}
    assert emitted[1]["type"] == "agents"
    rows = dict(emitted[1]["agents"])
    assert "Reviewer Agent" in rows["reviewer"]
    profile = asyncio.run(profiles.load("tenant", "user", "reviewer"))
    assert profile is not None
    spec = profile.to_agent_spec()
    assert spec.model.protocol == "openai-chat"
    assert spec.model.model == "gpt-test"
    assert spec.enabled_tools == ["filesystem.read", "shell.run"]
    assert spec.permission_profile == "guarded"
    assert spec.tool_permissions.mode == "auto"
    assert spec.tool_permissions.approval_required_tools == ["shell.run"]


def test_ndjson_bridge_switches_to_saved_agent_profile(monkeypatch, tmp_path):
    profiles = InMemoryAgentProfileStore()
    spec = AgentSpec.from_overrides(
        protocol="scripted",
        model="reviewer-model",
        system_prompt="Review carefully.",
        enabled_tools=["echo"],
        tenant_id="tenant",
        user_id="user",
        agent_id="reviewer",
        workspace_id="workspace",
        workspace_path=str(tmp_path),
        permission_profile="ask",
        approval_required_tools=["echo"],
    )
    asyncio.run(profiles.save(AgentProfile.from_spec(spec, name="Reviewer")))
    old_runtime = AgentRuntime(
        model_client=ScriptedModelClient([]),
        tools=ToolRegistry(),
        protocol="scripted",
        model="old-model",
    )
    old_session = AgentSession(
        runtime=old_runtime,
        system_prompt="Old prompt.",
        workspace=SimpleNamespace(
            tenant_id="tenant",
            user_id="user",
            agent_id="terminal",
            workspace_id="workspace",
            path=tmp_path,
        ),
    )
    old_session.messages.append(Message.from_text("user", "keep this"))

    async def fake_create_agent_session_async(settings, *, spec, **kwargs):
        tools = ToolRegistry()
        tools.register("echo", "Echo", {}, lambda text: text)
        runtime = AgentRuntime(
            model_client=ScriptedModelClient([]),
            tools=tools,
            protocol=spec.model.protocol,
            model=spec.model.model,
            enabled_tools=spec.enabled_tools or [],
            permission_policy=StaticToolPermissionPolicy(approval_required_tools=spec.tool_permissions.approval_required_tools),
        )
        return AgentSession(
            runtime=runtime,
            system_prompt=spec.system_prompt or "",
            workspace=SimpleNamespace(
                tenant_id=spec.workspace.tenant_id,
                user_id=spec.workspace.user_id,
                agent_id=spec.workspace.agent_id,
                workspace_id=spec.workspace.workspace_id,
                path=Path(spec.workspace.path),
            ),
        )

    monkeypatch.setattr("agents.interfaces.bridge.slash.create_agent_session_async", fake_create_agent_session_async)
    state = ndjson.BridgeState(
        args=SimpleNamespace(),
        profile="coding",
        permission="guarded",
        active_workspace=tmp_path,
        active_tools=["filesystem.read"],
        permission_mode="auto",
        approval_tools=[],
        settings=SimpleNamespace(),
        persistence=SimpleNamespace(agent_profiles=profiles),
        model_profiles=[],
        session=old_session,
        session_store=TerminalSessionStore(tmp_path / "sessions"),
        session_id="session-test",
        event_offsets={},
    )
    emitted = []

    asyncio.run(run_slash(state, "/agents use reviewer", emitted))

    assert emitted[0] == {"type": "notice", "message": "agent switched: reviewer"}
    assert emitted[1]["type"] == "runtime"
    assert emitted[1]["runtime"]["model"] == "reviewer-model"
    assert emitted[2]["type"] == "tools"
    assert emitted[3]["type"] == "permissions"
    assert state.active_tools == ["echo"]
    assert state.permission == "ask"
    assert state.permission_mode == "ask"
    assert state.approval_tools == ["echo"]
    assert state.session.runtime.model == "reviewer-model"
    assert state.session.system_prompt == "Review carefully."
    assert [message.content_text() for message in state.session.messages] == ["Review carefully.", "keep this"]


def test_ndjson_bridge_cancels_active_turn(monkeypatch, tmp_path):
    started = None

    class Runtime:
        protocol = "scripted"
        model = "slow-model"

    class SlowSession:
        runtime = Runtime()

        def __init__(self):
            self.messages = []

        async def stream(self, text, run_id=None):
            yield RuntimeEvent(type="text_delta", name="assistant", payload={"delta": "working"})
            assert started is not None
            started.set()
            await asyncio.Event().wait()

    emitted = []
    monkeypatch.setattr(ndjson, "_write", emitted.append)
    state = ndjson.BridgeState(
        args=SimpleNamespace(),
        profile="coding",
        permission="guarded",
        active_workspace=tmp_path,
        active_tools=[],
        permission_mode="auto",
        approval_tools=[],
        settings=SimpleNamespace(),
        persistence=SimpleNamespace(),
        model_profiles=[],
        session=SlowSession(),
        session_store=TerminalSessionStore(tmp_path / "sessions"),
        session_id="session-test",
        event_offsets={},
    )

    async def run_flow():
        nonlocal started
        started = asyncio.Event()
        await ndjson._handle_command(state, {"type": "user_message", "text": "slow", "run_id": "run-1"})
        assert active_task_running(state)
        await asyncio.wait_for(started.wait(), timeout=1)

        await ndjson._handle_command(state, {"type": "user_message", "text": "second", "run_id": "run-2"})
        assert emitted[-1] == {"type": "error", "message": "run already active; use /cancel to interrupt"}

        await ndjson._handle_command(state, {"type": "cancel", "run_id": "run-1"})

    asyncio.run(run_flow())

    assert state.active_task is None
    assert state.active_run_id == ""
    assert emitted[0] == {"type": "turn_started", "run_id": "run-1"}
    assert any(payload.get("type") == "runtime_event" and payload["event"]["type"] == "text_delta" for payload in emitted)
    assert emitted[-1] == {"type": "turn_finished", "status": "cancelled", "run_id": "run-1"}


def test_ndjson_bridge_forwards_interrupt_cancel_reason(monkeypatch, tmp_path):
    started = None

    class Runtime:
        protocol = "scripted"
        model = "slow-model"

    class SlowSession:
        runtime = Runtime()

        def __init__(self):
            self.messages = []
            self.cancel_reason = ""

        async def stream(self, text, run_id=None):
            yield RuntimeEvent(type="text_delta", name="assistant", payload={"delta": "working"})
            assert started is not None
            started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError as exc:
                self.cancel_reason = str(exc.args[0]) if exc.args else ""
                raise

    session = SlowSession()
    emitted = []
    monkeypatch.setattr(ndjson, "_write", emitted.append)
    state = ndjson.BridgeState(
        args=SimpleNamespace(),
        profile="coding",
        permission="guarded",
        active_workspace=tmp_path,
        active_tools=[],
        permission_mode="auto",
        approval_tools=[],
        settings=SimpleNamespace(),
        persistence=SimpleNamespace(),
        model_profiles=[],
        session=session,
        session_store=TerminalSessionStore(tmp_path / "sessions"),
        session_id="session-test",
        event_offsets={},
    )

    async def run_flow():
        nonlocal started
        started = asyncio.Event()
        await ndjson._handle_command(state, {"type": "user_message", "text": "slow", "run_id": "run-1"})
        await asyncio.wait_for(started.wait(), timeout=1)
        await ndjson._handle_command(state, {"type": "cancel", "run_id": "run-1", "reason": "interrupt"})

    asyncio.run(run_flow())

    assert session.cancel_reason == "interrupt"
    assert emitted[-1] == {"type": "turn_finished", "status": "cancelled", "run_id": "run-1"}


def test_bridge_turn_approval_validation_error_emits_turn_finished(tmp_path):
    from agents.interfaces.bridge.turns import run_approval

    emitted = []
    state = SimpleNamespace(session_store=TerminalSessionStore(tmp_path / "sessions"))

    asyncio.run(
        run_approval(
            state,
            {
                "run_id": "run-1",
                "approvals": {"call-1": True},
                "approval_scopes": {"call-1": "bad-scope"},
            },
            emitted.append,
        )
    )

    assert emitted[0]["type"] == "error"
    assert emitted[-1] == {"type": "turn_finished", "status": "error", "run_id": "run-1"}


def test_bridge_active_task_exception_emits_turn_finished():
    from agents.interfaces.bridge.active import start_active_task

    emitted = []
    state = SimpleNamespace(active_task=None, active_run_id="")

    async def fail():
        raise RuntimeError("boom")

    async def execute():
        start_active_task(state, "run-1", fail(), emitted.append)
        await state.active_task

    asyncio.run(execute())

    assert emitted == [
        {"type": "error", "message": "boom"},
        {"type": "turn_finished", "status": "error", "run_id": "run-1"},
    ]
    assert state.active_task is None
    assert state.active_run_id == ""


def test_ndjson_bridge_diff_command_reports_git_status(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True, text=True)
    (tmp_path / "new.py").write_text("hello", encoding="utf-8")
    emitted = []
    state = ndjson.BridgeState(
        args=SimpleNamespace(),
        profile="coding",
        permission="guarded",
        active_workspace=tmp_path,
        active_tools=[],
        permission_mode="auto",
        approval_tools=[],
        settings=SimpleNamespace(),
        persistence=SimpleNamespace(),
        model_profiles=[],
        session=SimpleNamespace(),
        session_store=TerminalSessionStore(tmp_path / "sessions"),
        session_id="session-test",
        event_offsets={},
    )

    asyncio.run(run_slash(state, "/diff", emitted))

    assert emitted[0]["type"] == "diff"
    assert ["??", "new.py"] in emitted[0]["diff"]
