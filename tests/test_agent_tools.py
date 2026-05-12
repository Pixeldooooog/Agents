# !/usr/bin/env python
# -*- coding: utf-8 -*-
# =====================================================
# @File   ：test_agent_tools.py
# @Date   ：2026/04/24 00:00
# @Author ：Zegen
#
# 2026/04/24   Create
# =====================================================

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from agents.kernel.context.workspace import WorkspaceContext
from agents.kernel.governance import SandboxPolicy, describe_tool_impact
from agents.kernel.runtime import AgentResult, AgentRuntime, AgentSession
from agents.kernel.schema import Message, RuntimeEvent, ToolCall
from agents.kernel.hooks import InMemoryHookStore
from agents.kernel.mcp_config import InMemoryMCPConfigStore
from agents.kernel.session_state import InMemorySessionStateStore
from agents.kernel.capabilities.memory import InMemoryMemoryStore, MemoryScope
from agents.kernel.capabilities.skills import SkillLoader, SkillRegistry
from agents.kernel.capabilities.sandbox.local import LocalSandboxProvider
from agents.kernel.capabilities.sandbox.types import SandboxCommandResult
from agents.kernel.capabilities.tools.builtin.browser import browser_open
from agents.kernel.capabilities.tools.mcp import (
    MCPPromptArgumentDefinition,
    MCPPromptDefinition,
    MCPResourceDefinition,
    MCPServerConfig,
    MCPToolDefinition,
    MCPToolProvider,
)
from agents.kernel.capabilities.tools import ToolRuntimeContext, register_builtin_tools
from agents.kernel.capabilities.tools.registry import ToolRegistry
from agents.kernel.specs import AgentSpec
from agents.kernel.state import InMemoryAgentProfileStore, InMemoryArtifactStore, LocalArtifactBlobStore
from agents.kernel.tasks import InMemoryScheduleStore, InMemoryTaskStore, TaskEngine, TaskStatus, TaskStepStatus
from agents.kernel.teams import InMemoryTeamStore


def test_tool_registry_registers_specs_and_rejects_duplicates():
    registry = ToolRegistry()
    registry.register(
        "echo",
        "Echo text",
        {"type": "object", "properties": {"text": {"type": "string"}}},
        lambda text: text,
    )

    assert registry.specs()[0].name == "echo"
    with pytest.raises(ValueError):
        registry.register("echo", "Echo again", {}, lambda: "x")


def test_tool_registry_exposes_metadata_in_specs():
    registry = ToolRegistry()
    registry.register("dangerous", "Dangerous", {}, lambda: "ok", metadata={"risk": "high"})

    spec = registry.specs(["dangerous"])[0]

    assert spec.raw["metadata"]["risk"] == "high"


def test_tool_executor_runs_calls_concurrently_and_preserves_order():
    registry = ToolRegistry()
    calls = []

    async def slow(text):
        await asyncio.sleep(0.02)
        calls.append(text)
        return text

    async def fast(text):
        calls.append(text)
        return text

    registry.register("slow", "Slow", {}, slow)
    registry.register("fast", "Fast", {}, fast)

    results = asyncio.run(
        registry.execute_many(
            [
                ToolCall(id="call-1", name="slow", arguments={"text": "first"}),
                ToolCall(id="call-2", name="fast", arguments={"text": "second"}),
            ]
        )
    )

    assert [item.tool_call_id for item in results] == ["call-1", "call-2"]
    assert [item.content for item in results] == ["first", "second"]
    assert calls == ["second", "first"]


def test_tool_executor_runs_state_writes_sequentially():
    registry = ToolRegistry()
    calls = []

    async def slow_write(text):
        await asyncio.sleep(0.02)
        calls.append(text)
        return text

    async def fast_read(text):
        calls.append(text)
        return text

    registry.register("write", "Write state", {}, slow_write, metadata={"writes_state": True})
    registry.register("read", "Read state", {}, fast_read)

    results = asyncio.run(
        registry.execute_many(
            [
                ToolCall(id="call-1", name="write", arguments={"text": "first"}),
                ToolCall(id="call-2", name="read", arguments={"text": "second"}),
            ]
        )
    )

    assert [item.content for item in results] == ["first", "second"]
    assert calls == ["first", "second"]


def test_tool_executor_converts_failures_to_error_results():
    registry = ToolRegistry()

    def fail():
        raise RuntimeError("broken")

    registry.register("fail", "Fail", {}, fail)

    results = asyncio.run(registry.execute_many([ToolCall(id="call-1", name="fail")]))

    assert results[0].is_error is True
    assert "broken" in results[0].content


class FakeMCPClient:
    def __init__(self):
        self.called = []

    async def list_tools(self):
        return [
            MCPToolDefinition(
                name="search",
                description="Search docs",
                parameters={"type": "object", "properties": {"query": {"type": "string"}}},
            )
        ]

    async def call_tool(self, name, arguments):
        self.called.append((name, arguments))
        return {"answer": arguments["query"]}

    async def list_resources(self):
        return [
            MCPResourceDefinition(
                uri="docs://intro",
                name="Intro",
                description="Intro docs",
                mime_type="text/markdown",
            )
        ]

    async def read_resource(self, uri):
        return {"contents": [{"uri": uri, "mimeType": "text/markdown", "text": "Hello docs"}]}

    async def list_prompts(self):
        return [
            MCPPromptDefinition(
                name="review",
                description="Review code",
                arguments=[MCPPromptArgumentDefinition(name="path", description="Path to review", required=True)],
            )
        ]

    async def get_prompt(self, name, arguments=None):
        return {
            "description": "Review code",
            "messages": [{"role": "user", "content": {"type": "text", "text": "Review %s" % arguments["path"]}}],
        }


def test_mcp_provider_loads_tools_with_server_prefix():
    registry = ToolRegistry()
    client = FakeMCPClient()
    provider = MCPToolProvider(
        client=client,
        server=MCPServerConfig(name="docs", execution_mode="trusted_control_plane"),
    )

    asyncio.run(provider.load_tools(registry))
    result = asyncio.run(registry.execute("mcp_docs_search", {"query": "agents"}))

    assert registry.specs(["mcp_docs_search"])[0].name == "mcp_docs_search"
    assert registry.specs(["mcp_docs_search"])[0].raw["metadata"]["execution_mode"] == "trusted_control_plane"
    assert json.loads(result.content)["answer"] == "agents"
    assert client.called == [("search", {"query": "agents"})]


def test_builtin_mcp_resource_tools_list_and_read_resources(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path, allow_file_write=True)
    provider = MCPToolProvider(
        client=FakeMCPClient(),
        server=MCPServerConfig(name="docs", execution_mode="trusted_control_plane"),
    )
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
        mcp_providers=[provider],
        settings=SimpleNamespace(
            mcp=SimpleNamespace(
                SERVER_NAME="docs",
                SERVER_COMMAND="python docs_mcp.py",
                EXECUTION_MODE="trusted_control_plane",
                SANDBOX_PROFILE="",
            )
        ),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    servers = asyncio.run(registry.execute("mcp.servers", {}))
    resources = asyncio.run(registry.execute("mcp.resources", {"server": "docs"}))
    content = asyncio.run(registry.execute("mcp.read_resource", {"server": "docs", "uri": "docs://intro"}))
    configured = asyncio.run(registry.execute("mcp.configure", {"name": "local", "command": "python local_mcp.py"}))
    cleared = asyncio.run(registry.execute("mcp.clear", {}))

    assert servers.raw["configured"]["name"] == "docs"
    assert servers.raw["providers"][0]["name"] == "docs"
    assert resources.raw["resources"][0]["uri"] == "docs://intro"
    assert resources.raw["resources"][0]["server"] == "docs"
    assert content.raw["server"] == "docs"
    assert content.raw["content"]["contents"][0]["text"] == "Hello docs"
    assert configured.raw["configured"]["name"] == "local"
    assert configured.raw["configured"]["command"] == "python local_mcp.py"
    assert cleared.raw["removed_providers"] == 1
    assert context.mcp_providers == []

    impact = describe_tool_impact(ToolCall(id="call-mcp", name="mcp.configure", arguments={"command": "python local_mcp.py"}))
    assert impact.risk == "medium"
    assert impact.operations == ["mcp_server_write"]


def test_builtin_mcp_management_tools_use_shared_config_store(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path)
    store = InMemoryMCPConfigStore()

    def make_registry():
        context = ToolRuntimeContext(
            workspace=workspace,
            sandbox=policy,
            sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
            settings=SimpleNamespace(
                mcp=SimpleNamespace(SERVER_NAME="", SERVER_COMMAND="", EXECUTION_MODE="", SANDBOX_PROFILE="")
            ),
            mcp_config_store=store,
        )
        registry = ToolRegistry()
        register_builtin_tools(registry, context)
        return registry

    first = make_registry()
    second = make_registry()

    async def execute():
        configured = await first.execute("mcp.configure", {"name": "docs", "command": "python server.py"})
        configured_search = await first.execute("mcp.configure", {"name": "search", "command": "python search.py"})
        listed = await second.execute("mcp.servers", {})
        disabled = await second.execute("mcp.disable", {"name": "search"})
        enabled = await second.execute("mcp.enable", {"name": "docs"})
        removed = await second.execute("mcp.remove", {"name": "docs"})
        cleared = await second.execute("mcp.clear", {})
        after_clear = await make_registry().execute("mcp.servers", {})
        return configured, configured_search, listed, disabled, enabled, removed, cleared, after_clear

    configured, configured_search, listed, disabled, enabled, removed, cleared, after_clear = asyncio.run(execute())

    assert configured.raw["configured"]["name"] == "docs"
    assert configured_search.raw["configured"]["name"] == "search"
    assert listed.raw["configured"]["command"] == "python search.py"
    assert {record["name"]: record["enabled"] for record in listed.raw["servers"]} == {"search": True, "docs": False}
    assert disabled.raw["disabled"] == "search"
    assert disabled.raw["configured"]["enabled"] is False
    assert enabled.raw["enabled"] == "docs"
    assert enabled.raw["configured"]["command"] == "python server.py"
    assert removed.raw["removed"] == "docs"
    assert cleared.raw["cleared"] is True
    assert after_clear.raw["configured"]["enabled"] is False


def test_builtin_mcp_prompt_tools_list_and_get_prompt(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path, allow_file_write=True)
    provider = MCPToolProvider(
        client=FakeMCPClient(),
        server=MCPServerConfig(name="docs", execution_mode="trusted_control_plane"),
    )
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
        mcp_providers=[provider],
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    prompts = asyncio.run(registry.execute("mcp.prompts", {"server": "docs", "query": "review"}))
    rendered = asyncio.run(registry.execute("mcp.get_prompt", {"server": "docs", "name": "review", "arguments": {"path": "src"}}))

    assert prompts.raw["prompts"][0]["name"] == "review"
    assert prompts.raw["prompts"][0]["arguments"] == [{"name": "path", "description": "Path to review", "required": True}]
    assert rendered.raw["server"] == "docs"
    assert rendered.raw["content"]["messages"][0]["content"]["text"] == "Review src"


def test_builtin_memory_tools_manage_visible_memories(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path, allow_file_write=True)
    store = InMemoryMemoryStore()
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
        memory_store=store,
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    added = asyncio.run(
        registry.execute(
            "memory.add",
            {"content": "Prefer concise implementation notes", "scope": "workspace"},
        )
    )
    short_id = added.raw["memory"]["short_id"]
    listed = asyncio.run(registry.execute("memory.list", {"query": "concise"}))
    edited = asyncio.run(
        registry.execute(
            "memory.edit",
            {"memory_id": short_id, "content": "Prefer concise verification notes"},
        )
    )
    forgotten = asyncio.run(registry.execute("memory.forget", {"memory_id": short_id}))

    records = asyncio.run(store.list_for_context("tenant", "user", agent_id="agent", workspace_id="workspace"))
    assert added.raw["memory"]["scope"] == MemoryScope.WORKSPACE.value
    assert added.raw["memory"]["metadata"]["source"] == "tool"
    assert listed.raw["memories"][0]["short_id"] == short_id
    assert edited.raw["memory"]["content"] == "Prefer concise verification notes"
    assert forgotten.raw["forgotten"] is True
    assert records == []


def test_builtin_task_tools_manage_tracked_tasks(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path)
    store = InMemoryTaskStore()
    spec = AgentSpec.from_overrides(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
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
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    created = asyncio.run(
        registry.execute(
            "task.create",
            {"title": "Build task tools", "input": "Add model-callable task tools"},
        )
    )
    task_id = created.raw["task"]["task_id"]
    short_id = created.raw["task"]["short_id"]
    listed = asyncio.run(registry.execute("task.list", {}))
    loaded = asyncio.run(registry.execute("task.get", {"task_id": short_id}))
    updated = asyncio.run(registry.execute("task.update", {"task_id": short_id, "status": "running"}))

    assert created.is_error is False
    assert listed.raw["tasks"][0]["task_id"] == task_id
    assert loaded.raw["task"]["title"] == "Build task tools"
    assert updated.raw["task"]["status"] == "running"
    assert asyncio.run(store.load_task(task_id)).status == TaskStatus.RUNNING

    async def add_output():
        engine = TaskEngine(store)
        step = await engine.add_step(task_id, name="terminal", input="work")
        await engine.start_step(step.step_id)
        await engine.finish_step(step.step_id, output="step output")

    asyncio.run(add_output())
    output = asyncio.run(registry.execute("task.output", {"task_id": short_id}))
    stopped = asyncio.run(registry.execute("task.stop", {"task_id": short_id}))

    assert "step output" in output.raw["output"]
    assert stopped.raw["task"]["status"] == "canceled"
    assert asyncio.run(store.load_task(task_id)).status == TaskStatus.CANCELED


def test_builtin_task_run_executes_tracked_task_with_child_session(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path)
    store = InMemoryTaskStore()
    spec = AgentSpec.from_overrides(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        workspace_path=str(tmp_path),
    )
    created_children = []

    class ChildSession:
        async def send(self, text, run_id=None, task_id=None):
            return AgentResult(
                content="executed: %s" % text,
                messages=[Message.from_text("assistant", "executed")],
                events=[RuntimeEvent(type="model_message", name="assistant", payload={"content": "executed"})],
            )

    async def create_child(child_spec, task_id=""):
        created_children.append((child_spec, task_id))
        return ChildSession()

    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
        task_store=store,
        agent_spec=spec,
        agent_session_factory=create_child,
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    ran = asyncio.run(
        registry.execute(
            "task.run",
            {"title": "Run tracked work", "input": "do the work", "step_name": "implement"},
        )
    )
    steps = asyncio.run(store.list_steps(ran.raw["task"]["task_id"]))

    assert ran.is_error is False
    assert ran.raw["task"]["status"] == "finished"
    assert ran.raw["step"]["name"] == "implement"
    assert ran.raw["step"]["output"] == "executed: do the work"
    assert ran.raw["run"]["status"] == "finished"
    assert ran.raw["result"]["content"] == "executed: do the work"
    assert steps[0].status == TaskStepStatus.SUCCEEDED
    assert created_children[0][1] == ran.raw["task"]["task_id"]

    impact = describe_tool_impact(ToolCall(id="call-task-run", name="task.run", arguments={"title": "Run tracked work", "input": "do the work"}))
    assert impact.risk == "high"
    assert impact.operations == ["task_state_write", "subagent"]
    assert "do the work" in impact.diff_preview


def test_builtin_task_background_runs_tracked_task_asynchronously(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path)
    store = InMemoryTaskStore()
    spec = AgentSpec.from_overrides(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        workspace_path=str(tmp_path),
    )

    class ChildSession:
        async def send(self, text, run_id=None, task_id=None):
            await asyncio.sleep(0)
            return AgentResult(
                content="background: %s" % text,
                messages=[Message.from_text("assistant", "background")],
                events=[RuntimeEvent(type="model_message", name="assistant", payload={"content": "background"})],
            )

    async def create_child(child_spec, task_id=""):
        return ChildSession()

    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
        task_store=store,
        agent_spec=spec,
        agent_session_factory=create_child,
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    async def execute():
        started = await registry.execute("task.background", {"title": "Run async", "input": "background work"})
        task_id = started.raw["task"]["task_id"]
        await context.background_tasks[task_id]
        backgrounds = await registry.execute("task.backgrounds", {})
        output = await registry.execute("task.output", {"task_id": task_id})
        return started, backgrounds, output

    started, backgrounds, output = asyncio.run(execute())

    assert started.raw["background"] == {"running": True, "done": False}
    assert backgrounds.raw["background_tasks"][0]["done"] is True
    assert backgrounds.raw["background_tasks"][0]["result"]["status"] == "finished"
    assert "background: background work" in output.raw["output"]

    impact = describe_tool_impact(ToolCall(id="call-bg", name="task.background", arguments={"title": "Run async", "input": "background work"}))
    assert impact.risk == "high"
    assert impact.operations == ["task_state_write", "subagent"]


def test_builtin_schedule_tools_manage_reusable_task_definitions(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path)
    store = InMemoryTaskStore()
    spec = AgentSpec.from_overrides(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
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
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    created = asyncio.run(
        registry.execute(
            "schedule.create",
            {"title": "Daily repo check", "schedule": "0 9 * * *", "input": "Check repository health"},
        )
    )
    short_id = created.raw["schedule"]["short_id"]
    listed = asyncio.run(registry.execute("schedule.list", {}))
    ran = asyncio.run(registry.execute("schedule.run", {"schedule_id": short_id, "background": False}))
    deleted = asyncio.run(registry.execute("schedule.delete", {"schedule_id": short_id}))

    task = asyncio.run(store.load_task(ran.raw["task"]["task_id"]))
    assert created.is_error is False
    assert listed.raw["schedules"][0]["short_id"] == short_id
    assert ran.raw["schedule"]["last_run_task_id"] == ran.raw["task"]["task_id"]
    assert ran.raw["task"]["metadata"]["source"] == "schedule"
    assert ran.raw["task"]["metadata"]["schedule_id"] == created.raw["schedule"]["schedule_id"]
    assert task is not None
    assert task.title == "Daily repo check"
    assert deleted.raw["deleted"] is True
    assert asyncio.run(registry.execute("schedule.list", {})).raw["schedules"] == []

    impact = describe_tool_impact(ToolCall(id="call-schedule", name="schedule.run", arguments={"schedule_id": short_id}))
    assert impact.risk == "high"
    assert impact.operations == ["schedule_run", "task_state_write", "subagent"]


def test_builtin_schedule_tools_use_shared_schedule_store(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path)
    spec = AgentSpec.from_overrides(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        workspace_path=str(tmp_path),
    )
    schedule_store = InMemoryScheduleStore()

    def make_registry():
        context = ToolRuntimeContext(
            workspace=workspace,
            sandbox=policy,
            sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
            schedule_store=schedule_store,
            agent_spec=spec,
        )
        registry = ToolRegistry()
        register_builtin_tools(registry, context)
        return registry

    first = make_registry()
    second = make_registry()

    async def execute():
        created = await first.execute(
            "schedule.create",
            {"title": "Daily repo check", "schedule": "0 9 * * *", "input": "Check repository health"},
        )
        listed = await second.execute("schedule.list", {})
        deleted = await second.execute("schedule.delete", {"schedule_id": created.raw["schedule"]["short_id"]})
        after_delete = await first.execute("schedule.list", {})
        return created, listed, deleted, after_delete

    created, listed, deleted, after_delete = asyncio.run(execute())

    assert listed.raw["schedules"][0]["schedule_id"] == created.raw["schedule"]["schedule_id"]
    assert deleted.raw["deleted"] is True
    assert after_delete.raw["schedules"] == []


def test_builtin_workflow_tools_validate_and_run_task_agent_nodes(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path)
    store = InMemoryTaskStore()
    spec = AgentSpec.from_overrides(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        workspace_path=str(tmp_path),
    )
    created_children = []

    class ChildSession:
        async def send(self, text, run_id=None, task_id=None):
            return AgentResult(
                content="executed: %s" % text,
                messages=[Message.from_text("assistant", "executed")],
                events=[RuntimeEvent(type="model_message", name="assistant", payload={"content": "executed"})],
            )

    async def create_child(child_spec, task_id=""):
        created_children.append((child_spec, task_id))
        return ChildSession()

    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
        task_store=store,
        agent_spec=spec,
        agent_session_factory=create_child,
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)
    nodes = [
        {"node_id": "plan", "kind": "task", "name": "Plan", "input": "write plan"},
        {"node_id": "review", "kind": "agent", "name": "Review", "prompt": "review plan", "agent_id": "reviewer"},
    ]
    edges = [{"source": "plan", "target": "review"}]

    validated = asyncio.run(registry.execute("workflow.validate", {"workflow_id": "wf-1", "nodes": nodes, "edges": edges}))
    ran = asyncio.run(registry.execute("workflow.run", {"workflow_id": "wf-1", "nodes": nodes, "edges": edges}))
    tasks = asyncio.run(store.list_tasks("tenant", user_id="user", agent_id="agent"))

    assert validated.raw["order"] == ["plan", "review"]
    assert ran.raw["status"] == "finished"
    assert [result["node_id"] for result in ran.raw["results"]] == ["plan", "review"]
    assert ran.raw["results"][0]["content"] == "executed: write plan"
    assert ran.raw["results"][1]["content"] == "executed: review plan"
    assert tasks[0].metadata["workflow_node_id"] == "plan"
    assert created_children[0][1] == tasks[0].task_id
    assert created_children[1][0].agent_id == "reviewer"

    impact = describe_tool_impact(ToolCall(id="call-workflow", name="workflow.run", arguments={"nodes": nodes}))
    assert impact.risk == "high"
    assert impact.operations == ["workflow_run", "subagent"]


def test_builtin_workflow_tools_manage_saved_workflows(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path, allow_file_write=True)
    store = InMemoryTaskStore()
    spec = AgentSpec.from_overrides(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        workspace_path=str(tmp_path),
    )
    created_children = []

    class ChildSession:
        async def send(self, text, run_id=None, task_id=None):
            return AgentResult(
                content="executed: %s" % text,
                messages=[Message.from_text("assistant", "executed")],
                events=[RuntimeEvent(type="model_message", name="assistant", payload={"content": "executed"})],
            )

    async def create_child(child_spec, task_id=""):
        created_children.append((child_spec, task_id))
        return ChildSession()

    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
        task_store=store,
        agent_spec=spec,
        agent_session_factory=create_child,
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)
    nodes = [
        {"node_id": "draft", "kind": "task", "name": "Draft", "input": "draft release plan"},
        {
            "node_id": "review",
            "kind": "agent",
            "name": "Review",
            "prompt": "review release plan",
            "agent_id": "reviewer",
            "system_prompt": "Be terse.",
        },
    ]
    edges = [{"source": "draft", "target": "review"}]

    saved = asyncio.run(
        registry.execute(
            "workflow.save",
            {
                "name": "release-plan",
                "workflow_id": "release",
                "nodes": nodes,
                "edges": edges,
                "metadata": {"scope": "release"},
            },
        )
    )
    listed = asyncio.run(registry.execute("workflow.templates", {"query": "release"}))
    read = asyncio.run(registry.execute("workflow.read", {"name": "release-plan"}))
    ran = asyncio.run(registry.execute("workflow.run_saved", {"name": "release-plan"}))
    deleted = asyncio.run(registry.execute("workflow.delete", {"name": "release-plan"}))

    assert saved.raw["path"] == ".agents/workflows/release-plan.json"
    assert saved.raw["workflow"]["node_count"] == 2
    assert listed.raw["workflows"][0]["workflow_id"] == "release"
    assert read.raw["workflow"]["nodes"][1]["system_prompt"] == "Be terse."
    assert ran.raw["status"] == "finished"
    assert [result["node_id"] for result in ran.raw["results"]] == ["draft", "review"]
    assert ran.raw["results"][0]["content"] == "executed: draft release plan"
    assert ran.raw["results"][1]["content"] == "executed: review release plan"
    assert created_children[1][0].agent_id == "reviewer"
    assert deleted.raw["deleted"] is True

    run_impact = describe_tool_impact(ToolCall(id="call-workflow", name="workflow.run_saved", arguments={"name": "release-plan"}))
    save_impact = describe_tool_impact(ToolCall(id="call-workflow-save", name="workflow.save", arguments={"name": "release-plan", "nodes": nodes}))
    assert run_impact.risk == "high"
    assert run_impact.operations == ["workflow_run", "subagent"]
    assert run_impact.paths == [".agents/workflows/release-plan.json"]
    assert save_impact.risk == "medium"
    assert save_impact.operations == ["workflow_write"]
    assert save_impact.writes_files is True


def test_builtin_planning_tools_manage_todos_and_plan_mode(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    todos = [
        {"content": "Inspect runtime", "status": "completed", "activeForm": "Inspecting runtime"},
        {"content": "Add planning tools", "status": "in_progress", "activeForm": "Adding planning tools"},
        {"content": "Run checks", "status": "pending", "activeForm": "Running checks"},
    ]
    written = asyncio.run(registry.execute("todo.write", {"todos": todos}))
    read = asyncio.run(registry.execute("todo.read", {}))
    entered = asyncio.run(registry.execute("plan.enter", {}))
    exited = asyncio.run(
        registry.execute(
            "plan.exit",
            {
                "plan": "1. Add tools\n2. Test runtime",
                "allowedPrompts": [{"tool": "Bash", "prompt": "run tests"}],
            },
        )
    )
    status = asyncio.run(registry.execute("plan.status", {}))

    assert written.is_error is False
    assert written.raw["newTodos"][1]["activeForm"] == "Adding planning tools"
    assert read.raw["summary"] == {"pending": 1, "in_progress": 1, "completed": 1}
    assert entered.raw["mode"] == "plan"
    assert exited.raw["mode"] == "default"
    assert exited.raw["allowedPrompts"] == [{"tool": "Bash", "prompt": "run tests"}]
    assert status.raw["mode"] == "default"
    assert status.raw["plan"] == "1. Add tools\n2. Test runtime"

    impact = describe_tool_impact(
        ToolCall(id="call-plan", name="plan.exit", arguments={"plan": "1. Add tools\n2. Test runtime"})
    )
    assert impact.risk == "medium"
    assert impact.operations == ["plan_state_write"]
    assert "Add tools" in impact.diff_preview

    cleared = asyncio.run(
        registry.execute(
            "todo.write",
            {"todos": [{"content": "Run checks", "status": "completed", "activeForm": "Running checks"}]},
        )
    )
    assert cleared.raw["cleared"] is True
    assert context.todos == []


def test_builtin_planning_tools_persist_session_state(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path)
    store = InMemorySessionStateStore()
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
        session_state_store=store,
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    async def run():
        await registry.execute(
            "todo.write",
            {
                "todos": [
                    {"content": "Persist planning state", "status": "in_progress", "activeForm": "Persisting planning state"},
                ]
            },
        )
        await registry.execute("plan.enter", {})
        await registry.execute("plan.exit", {"plan": "Persist todo and plan state."})
        return await store.load_for_scope("tenant", user_id="user", agent_id="agent", workspace_id="workspace")

    record = asyncio.run(run())

    assert record is not None
    assert record.todos[0]["content"] == "Persist planning state"
    assert record.plan_mode is False
    assert record.plan_text == "Persist todo and plan state."


def test_builtin_meta_tools_search_tools_and_discover_skills(tmp_path: Path):
    (tmp_path / "skills").mkdir()
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "focus.md").write_text("Focus.", encoding="utf-8")
    (tmp_path / "skills" / "focus.json").write_text(
        json.dumps(
            {
                "name": "focus",
                "version": "1.0.0",
                "description": "Focus on repo-specific implementation work.",
                "tools": ["filesystem.read"],
                "prompt_fragments": ["prompts/focus.md"],
            }
        ),
        encoding="utf-8",
    )
    plugin_dir = tmp_path / ".agents" / "plugins" / "planner"
    (plugin_dir / ".codex-plugin").mkdir(parents=True)
    (plugin_dir / "prompt.md").write_text("Use planner plugin guidance.", encoding="utf-8")
    (plugin_dir / ".codex-plugin" / "plugin.json").write_text(
        json.dumps(
            {
                "name": "planner",
                "version": "1.0.0",
                "description": "Planning plugin",
                "tools": ["todo.write"],
                "prompt_fragments": ["prompt.md"],
            }
        ),
        encoding="utf-8",
    )
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path)
    skill_registry = SkillRegistry.load(SkillLoader(tmp_path), ["focus"])
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
        settings=SimpleNamespace(server=SimpleNamespace(ROOT_PATH=str(tmp_path))),
        skill_registry=skill_registry,
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)
    context.enabled_tools = ["tool.search", "skill.discover", "plugin.discover", "filesystem.read"]

    tools = asyncio.run(registry.execute("tool.search", {"query": "file read", "include_all": False}))
    skills = asyncio.run(registry.execute("skill.discover", {"query": "focus", "include_prompt": True}))
    plugins = asyncio.run(registry.execute("plugin.discover", {"query": "planner", "include_prompt": True}))

    assert tools.is_error is False
    assert tools.raw["matches"][0]["name"] == "filesystem.read"
    assert tools.raw["matches"][0]["enabled"] is True
    assert skills.raw["skills"][0]["name"] == "focus"
    assert skills.raw["skills"][0]["enabled"] is True
    assert skills.raw["skills"][0]["prompt_fragments"] == ["prompts/focus.md"]
    assert plugins.raw["plugins"][0]["name"] == "planner"
    assert plugins.raw["plugins"][0]["tools"] == ["todo.write"]
    assert plugins.raw["plugins"][0]["prompts"] == [{"path": "prompt.md", "content": "Use planner plugin guidance."}]


def test_builtin_plugin_tools_install_and_uninstall_local_plugins(tmp_path: Path):
    source_dir = tmp_path / "plugin-source"
    (source_dir / ".codex-plugin").mkdir(parents=True)
    (source_dir / ".codex-plugin" / "plugin.json").write_text(
        json.dumps(
            {
                "name": "helper",
                "version": "1.0.0",
                "description": "Helper plugin",
                "tools": ["filesystem.read"],
            }
        ),
        encoding="utf-8",
    )
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
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
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    installed = asyncio.run(registry.execute("plugin.install", {"source": str(source_dir)}))
    discovered = asyncio.run(registry.execute("plugin.discover", {"query": "helper"}))
    uninstalled = asyncio.run(registry.execute("plugin.uninstall", {"name": "helper"}))

    assert installed.raw["installed"] is True
    assert installed.raw["plugin"]["name"] == "helper"
    assert discovered.raw["plugins"][0]["name"] == "helper"
    assert uninstalled.raw == {"plugin": "helper", "uninstalled": True}
    assert not (tmp_path / ".agents" / "plugins" / "helper").exists()

    impact = describe_tool_impact(ToolCall(id="call-plugin", name="plugin.install", arguments={"source": str(source_dir)}))
    assert impact.risk == "medium"
    assert impact.operations == ["extension_state_write"]
    assert impact.writes_files is True


def test_builtin_skill_tools_install_and_uninstall_skill_packages(tmp_path: Path):
    source_dir = tmp_path / "skill-source"
    source_dir.mkdir()
    (source_dir / "prompt.md").write_text("Use installed skill guidance.", encoding="utf-8")
    (source_dir / "skill.json").write_text(
        json.dumps(
            {
                "name": "installed",
                "version": "1.0.0",
                "description": "Installed skill",
                "tools": ["filesystem.read"],
                "prompt_fragments": ["prompt.md"],
            }
        ),
        encoding="utf-8",
    )
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path, allow_file_write=True)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
        settings=SimpleNamespace(server=SimpleNamespace(ROOT_PATH=str(tmp_path))),
        skill_registry=SkillRegistry([]),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    installed = asyncio.run(registry.execute("skill.install", {"source": str(source_dir)}))
    discovered = asyncio.run(registry.execute("skill.discover", {"query": "installed", "include_prompt": True}))
    loaded = SkillLoader(tmp_path).load("installed")
    uninstalled = asyncio.run(registry.execute("skill.uninstall", {"name": "installed"}))

    assert installed.raw["installed"] is True
    assert installed.raw["skill"]["name"] == "installed"
    assert discovered.raw["skills"][0]["name"] == "installed"
    assert discovered.raw["skills"][0]["prompt_fragments"] == ["prompt.md"]
    assert loaded.prompt_fragments == ["Use installed skill guidance."]
    assert uninstalled.raw == {"skill": "installed", "uninstalled": True}
    assert not (tmp_path / "skills" / "installed").exists()

    impact = describe_tool_impact(ToolCall(id="call-skill-install", name="skill.install", arguments={"source": str(source_dir)}))
    assert impact.risk == "medium"
    assert impact.operations == ["extension_state_write"]
    assert impact.writes_files is True


def test_builtin_prompt_template_tools_manage_local_templates(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
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
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    saved = asyncio.run(registry.execute("prompt.save", {"name": "reviewer", "content": "Review {arguments} for {{focus}}."}))
    templates = asyncio.run(registry.execute("prompt.templates", {"query": "review"}))
    read = asyncio.run(registry.execute("prompt.read", {"name": "reviewer"}))
    rendered = asyncio.run(
        registry.execute(
            "prompt.render",
            {"name": "reviewer", "raw_arguments": "src/agents", "arguments": {"focus": "regressions"}},
        )
    )
    deleted = asyncio.run(registry.execute("prompt.delete", {"name": "reviewer"}))

    assert saved.raw["path"] == ".agents/prompts/reviewer.md"
    assert templates.raw["templates"][0]["name"] == "reviewer"
    assert read.raw["content"] == "Review {arguments} for {{focus}}."
    assert rendered.raw["prompt"] == "Review src/agents for regressions."
    assert deleted.raw["deleted"] is True

    impact = describe_tool_impact(ToolCall(id="call-prompt", name="prompt.save", arguments={"name": "reviewer", "content": "Review carefully."}))
    assert impact.risk == "medium"
    assert impact.operations == ["prompt_write"]
    assert impact.paths == [".agents/prompts/reviewer.md"]


def test_builtin_session_context_tools_inspect_and_compact_session(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
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
    registry = ToolRegistry()
    register_builtin_tools(registry, context)
    runtime = SimpleNamespace(protocol="scripted", model="test-model", enabled_tools=["session.status", "context.messages"])
    trace_item = SimpleNamespace(
        id="system.user_configured",
        layer=SimpleNamespace(value="system"),
        source="settings",
        priority=100,
        tokens=3,
        included=True,
        text="Base prompt.",
    )
    session = AgentSession(
        runtime=runtime,
        system_prompt="Base prompt.",
        max_context_tokens=1000,
        context_trace=[trace_item],
        workspace=workspace,
        tool_context=context,
    )
    session.messages.append(Message.from_text("user", "hello"))

    status = asyncio.run(registry.execute("session.status", {}))
    summary = asyncio.run(registry.execute("session.summary", {"max_messages": 2}))
    trace = asyncio.run(registry.execute("context.trace", {"include_text": True}))
    messages = asyncio.run(registry.execute("context.messages", {"include_system": True}))
    exported = asyncio.run(registry.execute("session.export", {"path": "exports/session.json", "include_system": True}))
    rewound = asyncio.run(registry.execute("context.rewind", {"drop_last": 1}))
    compacted = asyncio.run(registry.execute("context.compact", {"target_tokens": 100}))

    assert context.session is session
    assert status.raw["model"] == {"protocol": "scripted", "model": "test-model"}
    assert status.raw["messages"]["non_system"] == 1
    assert "user: hello" in summary.raw["summary"]
    assert summary.raw["roles"] == {"user": 1}
    assert trace.raw["items"][0]["text"] == "Base prompt."
    assert messages.raw["messages"][0]["role"] == "system"
    assert exported.raw["path"] == "exports/session.json"
    assert "hello" in (tmp_path / "exports" / "session.json").read_text(encoding="utf-8")
    assert rewound.raw["dropped_messages"] == 1
    assert [message.role for message in session.messages] == ["system"]
    assert compacted.raw["before_messages"] >= compacted.raw["after_messages"]

    impact = describe_tool_impact(ToolCall(id="call-context", name="context.compact", arguments={}))
    assert impact.risk == "medium"
    assert impact.operations == ["context_write"]
    summary_impact = describe_tool_impact(ToolCall(id="call-summary", name="session.summary", arguments={}))
    assert summary_impact.risk == "low"
    assert summary_impact.operations == ["context_read"]
    export_impact = describe_tool_impact(ToolCall(id="call-export", name="session.export", arguments={"path": "exports/session.json"}))
    assert export_impact.risk == "medium"
    assert export_impact.operations == ["session_export"]
    assert export_impact.writes_files is True


def test_builtin_permission_tools_report_status_and_explain_decisions(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path)
    spec = AgentSpec.from_overrides(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        workspace_path=str(tmp_path),
        enabled_tools=["shell.run"],
        approval_required_tools=["shell.run"],
    )
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
        agent_spec=spec,
    )
    context.enabled_tools = ["shell.run"]
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    status = asyncio.run(registry.execute("permission.status", {}))
    sources = asyncio.run(registry.execute("permission.sources", {}))
    explained = asyncio.run(
        registry.execute(
            "permission.explain",
            {"tool": "shell.run", "arguments": {"command": "pytest -q"}},
        )
    )

    assert status.raw["profile"] == "auto"
    assert status.raw["approval_required_tools"] == ["shell.run"]
    assert status.raw["rules_by_source"]["agent_spec"]["ask"] == ["shell.run"]
    assert sources.raw["rules_by_source"]["agent_spec"]["ask"] == ["shell.run"]
    assert sources.raw["rules"][0] == {"source": "agent_spec", "behavior": "ask", "tool": "shell.run"}
    assert explained.raw["decision"]["requires_approval"] is True
    assert explained.raw["decision"]["metadata"]["source"] == "agent_spec"
    assert explained.raw["decision"]["metadata"]["rule"] == "ask"
    assert explained.raw["impact"]["risk"] == "high"
    assert explained.raw["impact"]["commands"] == ["pytest -q"]

    deny_result = asyncio.run(registry.execute("permission.add_rule", {"behavior": "deny", "tool": "shell.run"}))
    denied = asyncio.run(registry.execute("permission.explain", {"tool": "shell.run", "arguments": {"command": "pytest -q"}}))
    allow_result = asyncio.run(registry.execute("permission.add_rule", {"behavior": "allow", "tool": "filesystem.read"}))
    remove_allow = asyncio.run(registry.execute("permission.remove_rule", {"behavior": "allow", "tool": "filesystem.read"}))
    remove_deny = asyncio.run(registry.execute("permission.remove_rule", {"tool": "shell.run"}))
    rule_impact = describe_tool_impact(
        ToolCall(id="call-permission", name="permission.add_rule", arguments={"behavior": "deny", "tool": "shell.run"})
    )

    assert deny_result.raw["status"]["denied_tools"] == ["shell.run"]
    assert deny_result.raw["status"]["approval_required_tools"] == []
    assert denied.raw["decision"]["allowed"] is False
    assert denied.raw["decision"]["metadata"]["rule"] == "deny"
    assert allow_result.raw["status"]["restrict_allowed_tools"] is True
    assert allow_result.raw["status"]["allowed_tools"] == ["filesystem.read"]
    assert remove_allow.raw["status"]["restrict_allowed_tools"] is False
    assert remove_deny.raw["removed"] == [{"behavior": "deny", "tool": "shell.run"}]
    assert rule_impact.operations == ["permission_write"]


def test_builtin_hook_tools_manage_session_hooks(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    events = asyncio.run(registry.execute("hook.events", {}))
    added = asyncio.run(
        registry.execute(
            "hook.add",
            {
                "event": "pre_tool_use",
                "name": "block-shell",
                "action": "deny_tool",
                "content": "Shell blocked.",
                "tool": "shell.run",
            },
        )
    )
    short_id = added.raw["hook"]["short_id"]
    listed = asyncio.run(registry.execute("hook.list", {}))
    deleted = asyncio.run(registry.execute("hook.delete", {"hook_id": short_id}))

    assert events.raw["events"] == ["before_request", "after_response", "pre_tool_use", "post_tool_use"]
    assert added.raw["hook"]["metadata"]["source"] == "tool"
    assert added.raw["hook"]["tool"] == "shell.run"
    assert added.raw["hook"]["metadata"]["tool"] == "shell.run"
    assert listed.raw["hooks"][0]["short_id"] == short_id
    assert deleted.raw["deleted"] is True
    assert asyncio.run(registry.execute("hook.list", {})).raw["hooks"] == []

    impact = describe_tool_impact(ToolCall(id="call-hook", name="hook.add", arguments={"event": "before_request", "action": "append_system"}))
    assert impact.risk == "medium"
    assert impact.operations == ["hook_state_write"]


def test_builtin_hook_tools_use_shared_hook_store(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path)
    hook_store = InMemoryHookStore()

    def make_registry():
        context = ToolRuntimeContext(
            workspace=workspace,
            sandbox=policy,
            sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
            hook_store=hook_store,
        )
        registry = ToolRegistry()
        register_builtin_tools(registry, context)
        return registry

    first = make_registry()
    second = make_registry()

    async def execute():
        added = await first.execute(
            "hook.add",
            {"event": "pre_tool_use", "name": "block-shell", "action": "deny_tool", "tool": "shell.run", "content": "blocked"},
        )
        listed = await second.execute("hook.list", {})
        deleted = await second.execute("hook.delete", {"hook_id": added.raw["hook"]["short_id"]})
        after_delete = await first.execute("hook.list", {})
        return added, listed, deleted, after_delete

    added, listed, deleted, after_delete = asyncio.run(execute())

    assert listed.raw["hooks"][0]["hook_id"] == added.raw["hook"]["hook_id"]
    assert listed.raw["hooks"][0]["tool"] == "shell.run"
    assert deleted.raw["deleted"] is True
    assert after_delete.raw["hooks"] == []


def test_builtin_extension_management_tools_enable_skills_and_plugins(tmp_path: Path):
    (tmp_path / "skills").mkdir()
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "focus.md").write_text("Focus on runtime extension work.", encoding="utf-8")
    (tmp_path / "skills" / "focus.json").write_text(
        json.dumps(
            {
                "name": "focus",
                "description": "Focus skill",
                "tools": ["echo"],
                "prompt_fragments": ["prompts/focus.md"],
            }
        ),
        encoding="utf-8",
    )
    plugin_dir = tmp_path / ".agents" / "plugins" / "planner"
    (plugin_dir / ".codex-plugin").mkdir(parents=True)
    (plugin_dir / "prompt.md").write_text("Use planner plugin guidance.", encoding="utf-8")
    (plugin_dir / ".codex-plugin" / "plugin.json").write_text(
        json.dumps(
            {
                "name": "planner",
                "description": "Planning plugin",
                "tools": ["echo"],
                "prompt_fragments": ["prompt.md"],
            }
        ),
        encoding="utf-8",
    )
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path)
    store = InMemorySessionStateStore()
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
        settings=SimpleNamespace(server=SimpleNamespace(ROOT_PATH=str(tmp_path))),
        skill_registry=SkillRegistry([]),
        session_state_store=store,
    )
    registry = ToolRegistry()
    registry.register("echo", "Echo", {}, lambda text="": text)
    register_builtin_tools(registry, context)
    runtime = AgentRuntime(
        model_client=SimpleNamespace(),
        tools=registry,
        protocol="scripted",
        model="test-model",
        enabled_tools=["skill.use", "skill.disable", "plugin.enable", "plugin.disable"],
    )
    AgentSession(runtime=runtime, system_prompt="Base prompt.", workspace=workspace, tool_context=context)
    context.enabled_tools = runtime.enabled_tools

    skill_enabled = asyncio.run(registry.execute("skill.use", {"name": "focus"}))
    tools_after_skill = runtime.enabled_tools
    state_after_skill = asyncio.run(store.load_for_scope("tenant", user_id="user", agent_id="agent", workspace_id="workspace"))
    plugin_enabled = asyncio.run(registry.execute("plugin.enable", {"name": "planner"}))
    state_after_plugin = asyncio.run(store.load_for_scope("tenant", user_id="user", agent_id="agent", workspace_id="workspace"))
    plugin_disabled = asyncio.run(registry.execute("plugin.disable", {"name": "planner"}))
    skill_disabled = asyncio.run(registry.execute("skill.disable", {"name": "focus"}))
    state_after_disable = asyncio.run(store.load_for_scope("tenant", user_id="user", agent_id="agent", workspace_id="workspace"))

    assert skill_enabled.raw["added_tools"] == ["echo"]
    assert "Focus on runtime extension work." in context.session.system_prompt
    assert "Use planner plugin guidance." in context.session.system_prompt
    assert "echo" in tools_after_skill
    assert state_after_skill.enabled_skills == ["focus"]
    assert state_after_skill.skill_tools == {"focus": ["echo"]}
    assert plugin_enabled.raw["plugin"]["name"] == "planner"
    assert state_after_plugin.enabled_plugins == ["planner"]
    assert plugin_disabled.raw["removed_tools"] == []
    assert skill_disabled.raw["removed_tools"] == ["echo"]
    assert state_after_disable.enabled_skills == []
    assert state_after_disable.enabled_plugins == []
    assert "echo" not in runtime.enabled_tools

    impact = describe_tool_impact(ToolCall(id="call-skill", name="skill.use", arguments={"name": "focus"}))
    assert impact.risk == "medium"
    assert impact.operations == ["extension_state_write"]


def test_builtin_agent_profile_tools_list_and_save_profiles(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path)
    store = InMemoryAgentProfileStore()
    spec = AgentSpec.from_overrides(
        protocol="openai-chat",
        model="gpt-test",
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        workspace_path=str(tmp_path),
        enabled_tools=["filesystem.read"],
        permission_profile="auto",
    )
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
        agent_spec=spec,
        agent_profile_store=store,
    )
    context.enabled_tools = ["filesystem.read", "agent.save_profile"]
    registry = ToolRegistry()
    register_builtin_tools(registry, context)
    runtime = AgentRuntime(
        model_client=SimpleNamespace(),
        tools=registry,
        protocol="openai-chat",
        model="gpt-test",
        enabled_tools=context.enabled_tools,
    )
    AgentSession(runtime=runtime, system_prompt="Profile prompt.", workspace=workspace, tool_context=context)

    saved = asyncio.run(registry.execute("agent.save_profile", {"agent_id": "reviewer", "name": "Reviewer"}))
    listed = asyncio.run(registry.execute("agent.profiles", {"query": "review"}))
    loaded = asyncio.run(store.load("tenant", "user", "reviewer"))

    assert saved.raw["profile"]["agent_id"] == "reviewer"
    assert listed.raw["profiles"][0]["name"] == "Reviewer"
    assert loaded.to_agent_spec().system_prompt == "Profile prompt."
    assert loaded.to_agent_spec().enabled_tools == ["filesystem.read", "agent.save_profile"]

    impact = describe_tool_impact(ToolCall(id="call-agent-profile", name="agent.save_profile", arguments={"agent_id": "reviewer"}))
    assert impact.risk == "medium"
    assert impact.operations == ["agent_profile_write"]


def test_builtin_team_tools_manage_session_local_members_and_messages(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="lead",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    context.enabled_tools = ["filesystem.read"]
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    created = asyncio.run(
        registry.execute(
            "team.create",
            {
                "team_id": "feature",
                "name": "Feature Team",
                "members": [
                    {"agent_id": "researcher", "role": "research", "enabled_tools": ["filesystem.read"]},
                    {"agent_id": "reviewer", "role": "review"},
                ],
            },
        )
    )
    members = asyncio.run(registry.execute("team.members", {"team_id": "feature"}))
    sent = asyncio.run(
        registry.execute(
            "team.send",
            {"team_id": "feature", "from_agent": "lead", "to": "researcher", "message": "Check the repo."},
        )
    )
    inbox = asyncio.run(registry.execute("team.inbox", {"team_id": "feature", "agent_id": "researcher", "mark_read": True}))
    inbox_after_read = asyncio.run(registry.execute("team.inbox", {"team_id": "feature", "agent_id": "researcher"}))

    assert created.raw["team"]["team_id"] == "feature"
    assert members.raw["count"] == 2
    assert members.raw["members"][0]["agent_id"] == "researcher"
    assert sent.raw["count"] == 1
    assert inbox.raw["messages"][0]["message"] == "Check the repo."
    assert inbox_after_read.raw["messages"] == []

    impact = describe_tool_impact(ToolCall(id="call-team", name="team.send", arguments={"to": "researcher", "message": "Check the repo."}))
    assert impact.risk == "low"
    assert impact.operations == ["team_state_write"]
    assert "Check the repo" in impact.diff_preview


def test_builtin_team_tools_use_shared_team_store(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="lead",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path)
    team_store = InMemoryTeamStore()

    def make_registry():
        context = ToolRuntimeContext(
            workspace=workspace,
            sandbox=policy,
            sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
            team_store=team_store,
        )
        context.enabled_tools = ["filesystem.read"]
        registry = ToolRegistry()
        register_builtin_tools(registry, context)
        return registry

    first = make_registry()
    second = make_registry()

    async def execute():
        created = await first.execute(
            "team.create",
            {
                "team_id": "feature",
                "members": [{"agent_id": "researcher", "role": "research"}],
            },
        )
        members = await second.execute("team.members", {"team_id": "feature"})
        sent = await second.execute("team.send", {"team_id": "feature", "to": "researcher", "message": "Check the repo."})
        inbox = await first.execute("team.inbox", {"team_id": "feature", "agent_id": "researcher", "mark_read": True})
        after_read = await second.execute("team.inbox", {"team_id": "feature", "agent_id": "researcher"})
        return created, members, sent, inbox, after_read

    created, members, sent, inbox, after_read = asyncio.run(execute())

    assert created.raw["team"]["team_id"] == "feature"
    assert members.raw["members"][0]["agent_id"] == "researcher"
    assert sent.raw["count"] == 1
    assert inbox.raw["messages"][0]["message"] == "Check the repo."
    assert after_read.raw["messages"] == []


def test_builtin_team_run_member_delegates_and_delivers_result(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="lead",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path)
    created_children = []

    class ChildSession:
        async def send(self, prompt, run_id=None, task_id=None):
            return AgentResult(
                content="research result: %s" % prompt,
                messages=[Message.from_text("assistant", "research result")],
            )

    async def create_child(spec, task_id=""):
        created_children.append(spec)
        return ChildSession()

    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
        agent_spec=AgentSpec.from_overrides(
            tenant_id="tenant",
            user_id="user",
            agent_id="lead",
            workspace_id="workspace",
            workspace_path=str(tmp_path),
        ),
        agent_session_factory=create_child,
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)
    asyncio.run(
        registry.execute(
            "team.create",
            {
                "team_id": "feature",
                "members": [
                    {
                        "agent_id": "researcher",
                        "role": "research",
                        "system_prompt": "Research carefully.",
                        "enabled_tools": ["filesystem.read"],
                    }
                ],
            },
        )
    )

    delegated = asyncio.run(
        registry.execute(
            "team.run_member",
            {"team_id": "feature", "agent_id": "researcher", "prompt": "inspect repo", "reply_to": "lead"},
        )
    )
    inbox = asyncio.run(registry.execute("team.inbox", {"team_id": "feature", "agent_id": "lead"}))

    assert delegated.raw["result"]["content"] == "research result: inspect repo"
    assert delegated.raw["delivered"]["type"] == "agent_result"
    assert inbox.raw["messages"][0]["message"] == "research result: inspect repo"
    assert created_children[0].agent_id == "researcher"
    assert created_children[0].system_prompt == "Research carefully."
    assert created_children[0].enabled_tools == ["filesystem.read"]

    impact = describe_tool_impact(ToolCall(id="call-team-run", name="team.run_member", arguments={"agent_id": "researcher", "prompt": "inspect repo"}))
    assert impact.risk == "high"
    assert impact.operations == ["team_state_write", "subagent"]


def test_builtin_command_tools_discover_and_render_workspace_commands(tmp_path: Path):
    commands_dir = tmp_path / ".agents" / "commands"
    commands_dir.mkdir(parents=True)
    (commands_dir / "review.md").write_text(
        "---\n"
        "description: Review a target path\n"
        "argument_hint: <path>\n"
        "aliases: inspect\n"
        "---\n"
        "Review this path carefully: {arguments}\n",
        encoding="utf-8",
    )
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
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
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    commands = asyncio.run(registry.execute("command.discover", {"query": "review"}))
    rendered = asyncio.run(registry.execute("command.render", {"name": "inspect", "arguments": "src"}))
    read = asyncio.run(registry.execute("command.read", {"name": "review"}))
    saved = asyncio.run(
        registry.execute(
            "command.save",
            {
                "name": "ship",
                "content": "Ship {arguments}",
                "description": "Ship target",
                "aliases": ["release"],
            },
        )
    )
    rendered_saved = asyncio.run(registry.execute("command.render", {"name": "release", "arguments": "v1"}))
    deleted = asyncio.run(registry.execute("command.delete", {"name": "ship"}))

    assert commands.raw["commands"][0]["name"] == "/review"
    assert commands.raw["commands"][0]["argumentHint"] == "<path>"
    assert commands.raw["commands"][0]["aliases"] == ["/inspect"]
    assert rendered.raw["prompt"] == "Review this path carefully: src"
    assert read.raw["content"] == "Review this path carefully: {arguments}\n"
    assert saved.raw["path"] == ".agents/commands/ship.md"
    assert rendered_saved.raw["prompt"] == "Ship v1"
    assert deleted.raw["deleted"] is True

    impact = describe_tool_impact(ToolCall(id="call-command", name="command.render", arguments={"name": "review"}))
    assert impact.operations == ["command_read"]
    save_impact = describe_tool_impact(ToolCall(id="call-command-save", name="command.save", arguments={"name": "ship", "content": "Ship {arguments}"}))
    assert save_impact.risk == "medium"
    assert save_impact.operations == ["command_write"]
    assert save_impact.paths == [".agents/commands/ship.md"]


def test_patch_apply_edits_and_creates_workspace_files(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="default",
        user_id="user-1",
        agent_id="agent-1",
        workspace_id="default",
        root=tmp_path,
        path=tmp_path,
    )
    (tmp_path / "notes.txt").write_text("hello old world\n", encoding="utf-8")
    policy = SandboxPolicy.for_workspace(workspace.path, allow_file_write=True)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    result = asyncio.run(
        registry.execute(
            "patch.apply",
            {
                "edits": [{"path": "notes.txt", "old_text": "old", "new_text": "new"}],
                "creates": [{"path": "created.txt", "content": "created\n"}],
            },
        )
    )

    payload = result.raw
    assert result.is_error is False
    assert (tmp_path / "notes.txt").read_text(encoding="utf-8") == "hello new world\n"
    assert (tmp_path / "created.txt").read_text(encoding="utf-8") == "created\n"
    assert [item["path"] for item in payload["files"]] == ["notes.txt", "created.txt"]
    assert "--- a/notes.txt" in payload["diff"]


def test_filesystem_move_and_delete_are_native_workspace_tools(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="default",
        user_id="user-1",
        agent_id="agent-1",
        workspace_id="default",
        root=tmp_path,
        path=tmp_path,
    )
    (tmp_path / "old.txt").write_text("move me", encoding="utf-8")
    (tmp_path / "trash").mkdir()
    (tmp_path / "trash" / "note.txt").write_text("delete me", encoding="utf-8")
    policy = SandboxPolicy.for_workspace(workspace.path, allow_file_write=True)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    moved = asyncio.run(
        registry.execute(
            "filesystem.move",
            {"source_path": "old.txt", "destination_path": "renamed/new.txt"},
        )
    )
    deleted = asyncio.run(registry.execute("filesystem.delete", {"path": "trash", "recursive": True}))

    assert moved.is_error is False
    assert moved.raw["destination_path"] == "renamed/new.txt"
    assert (tmp_path / "renamed" / "new.txt").read_text(encoding="utf-8") == "move me"
    assert not (tmp_path / "old.txt").exists()
    assert deleted.raw["deleted"] is True
    assert not (tmp_path / "trash").exists()


def test_tool_impact_describes_patch_paths_and_preview():
    call = ToolCall(
        id="call-1",
        name="patch.apply",
        arguments={"edits": [{"path": "app.py", "old_text": "a = 1", "new_text": "a = 2"}]},
    )

    impact = describe_tool_impact(call).to_dict()

    assert impact["risk"] == "medium"
    assert impact["writes_files"] is True
    assert impact["paths"] == ["app.py"]
    assert "a = 2" in impact["diff_preview"]


def test_tool_impact_describes_file_move_and_git_commit():
    move = describe_tool_impact(
        ToolCall(
            id="call-1",
            name="filesystem.move",
            arguments={"source_path": "old.py", "destination_path": "new.py"},
        )
    ).to_dict()
    commit = describe_tool_impact(
        ToolCall(
            id="call-2",
            name="git.commit",
            arguments={"message": "ship", "all": True},
        )
    ).to_dict()

    assert move["risk"] == "medium"
    assert move["writes_files"] is True
    assert move["paths"] == ["old.py", "new.py"]
    assert commit["risk"] == "high"
    assert commit["writes_files"] is True
    assert commit["commands"] == ["git commit -a"]


def test_git_native_tools_stage_commit_log_and_show(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="default",
        user_id="user-1",
        agent_id="agent-1",
        workspace_id="default",
        root=tmp_path,
        path=tmp_path,
    )
    (tmp_path / "app.py").write_text("print('ok')\n", encoding="utf-8")
    policy = SandboxPolicy.for_workspace(
        workspace.path,
        allow_file_write=True,
        allow_process=True,
        allowed_commands=("git",),
    )
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    asyncio.run(context.sandbox_client.run_command("git init"))
    asyncio.run(context.sandbox_client.run_command("git config user.email test@example.com"))
    asyncio.run(context.sandbox_client.run_command("git config user.name Test"))
    added = asyncio.run(registry.execute("git.add", {"paths": ["app.py"]}))
    committed = asyncio.run(registry.execute("git.commit", {"message": "initial commit"}))
    log = asyncio.run(registry.execute("git.log", {"max_count": 1}))
    shown = asyncio.run(registry.execute("git.show", {"revision": "HEAD", "patch": False}))

    assert added.is_error is False
    assert committed.is_error is False
    assert "initial commit" in log.raw["stdout"]
    assert "initial commit" in shown.raw["stdout"]


def test_test_discover_suggests_workspace_test_commands(tmp_path: Path):
    workspace = WorkspaceContext(
        tenant_id="default",
        user_id="user-1",
        agent_id="agent-1",
        workspace_id="default",
        root=tmp_path,
        path=tmp_path,
    )
    (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_demo.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    policy = SandboxPolicy.for_workspace(workspace.path)
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    result = asyncio.run(registry.execute("test.discover", {}))

    assert result.is_error is False
    assert result.raw["recommended_command"] == "pytest"
    assert result.raw["commands"][0]["confidence"] == "high"


class FakeBrowserSandbox:
    async def run_command(self, command, timeout_seconds=30.0):
        return SandboxCommandResult(
            command=command,
            exit_code=0,
            stdout=json.dumps(
                {
                    "url": "https://example.com",
                    "path": "downloads/page.html",
                    "status": 200,
                    "content_type": "text/html",
                    "bytes": 12,
                    "truncated": False,
                }
            ),
        )


def test_browser_open_uses_sandbox_network_and_process_path():
    policy = SandboxPolicy.for_workspace(
        Path("."),
        allow_file_write=True,
        allow_process=True,
        allow_network=True,
        allowed_commands=("python3",),
    )
    context = SimpleNamespace(sandbox=policy, sandbox_client=FakeBrowserSandbox())

    result = asyncio.run(browser_open(context, "https://example.com", output_path="downloads/page.html"))

    assert result["status"] == 200
    assert result["path"] == "downloads/page.html"


class RecordingBrowserSandbox:
    def __init__(self, workspace: WorkspaceContext, output_path: str):
        self.workspace = workspace
        self.output_path = output_path

    async def run_command(self, command, timeout_seconds=30.0):
        target = self.workspace.path / self.output_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("<html>ok</html>", encoding="utf-8")
        return SandboxCommandResult(
            command=command,
            exit_code=0,
            stdout=json.dumps(
                {
                    "url": "https://example.com",
                    "path": self.output_path,
                    "status": 200,
                    "content_type": "text/html",
                    "bytes": 15,
                    "truncated": False,
                }
            ),
        )


def test_browser_open_records_run_artifact(tmp_path: Path):
    workspace_path = tmp_path / "workspace"
    workspace_path.mkdir()
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=workspace_path,
    )
    artifact_store = InMemoryArtifactStore()
    policy = SandboxPolicy.for_workspace(
        workspace.path,
        allow_file_write=True,
        allow_process=True,
        allow_network=True,
        allowed_commands=("python3",),
    )
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=RecordingBrowserSandbox(
            workspace,
            (tmp_path / "blob" / "runs" / "run-1" / "artifacts" / "downloads" / "browser-open.html").as_posix(),
        ),
        artifact_store=artifact_store,
        artifact_blob_store=LocalArtifactBlobStore(tmp_path / "blob", include_workspace_scope=False),
    )
    context.current_run_id = "run-1"
    context.current_tool_call_id = "call-1"

    result = asyncio.run(browser_open(context, "https://example.com"))
    artifacts = asyncio.run(artifact_store.list_for_run("run-1"))

    assert result["artifact"]["role"] == "tool_artifact"
    assert artifacts[0].tool_call_id == "call-1"
    assert artifacts[0].workspace_path == ""
    assert artifacts[0].uri.endswith("/blob/runs/run-1/artifacts/downloads/browser-open.html")
    assert artifacts[0].sha256


def test_skill_registry_loads_prompt_fragments_and_tool_names(tmp_path: Path):
    (tmp_path / "skills").mkdir()
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "focus.md").write_text("Focus on {topic}.", encoding="utf-8")
    (tmp_path / "skills" / "focus.json").write_text(
        json.dumps(
            {
                "name": "focus",
                "version": "1.0.0",
                "prompt_fragments": ["prompts/focus.md"],
                "tools": ["echo"],
            }
        ),
        encoding="utf-8",
    )

    registry = SkillRegistry.load(SkillLoader(tmp_path), ["focus"], context={"topic": "agents"})

    assert registry.names() == ["focus"]
    assert registry.prompt_text() == "Focus on agents."
    assert registry.tool_names() == ["echo"]
