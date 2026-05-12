# !/usr/bin/env python
# -*- coding: utf-8 -*-
# =====================================================
# @File   ：test_agent_runtime.py
# @Date   ：2026/04/24 00:00
# @Author ：Zegen
#
# 2026/04/24   Create
# =====================================================

import asyncio

import pytest

from agents.kernel.runtime import (
    AgentResult,
    AgentRuntime,
    AgentSession,
    InMemoryCheckpointStore,
    RuntimeCheckpoint,
    ScriptedModelClient,
    StaticToolPermissionPolicy,
)
from agents.kernel.governance.approval_grants import APPROVAL_ALLOW_FOR_RUN
from agents.kernel.hooks import SessionHookRegistry, SessionStateHooks
from agents.kernel.schema import Message, ModelResponse, ModelStreamEvent, ToolCall
from agents.kernel.capabilities.sandbox.local import LocalSandboxProvider
from agents.kernel.capabilities.tools import ToolRuntimeContext, register_builtin_tools
from agents.kernel.capabilities.tools.registry import ToolRegistry
from agents.kernel.context.workspace import WorkspaceContext
from agents.kernel.governance import SandboxPolicy
from agents.kernel.specs import AgentSpec
from agents.kernel.tasks import InMemoryTaskStore


def test_agent_runtime_runs_model_tool_model_loop():
    llm = ScriptedModelClient(
        [
            ModelResponse(
                message=Message.from_text(
                    "assistant",
                    "",
                    tool_calls=[ToolCall(id="call-1", name="echo", arguments={"text": "hi"})],
                ),
                stop_reason="tool_calls",
            ),
            ModelResponse(message=Message.from_text("assistant", "final answer")),
        ]
    )
    tools = ToolRegistry()
    tools.register("echo", "Echo", {}, lambda text: text)
    runtime = AgentRuntime(model_client=llm, tools=tools, protocol="scripted", model="scripted")

    result = asyncio.run(runtime.run([Message.from_text("user", "say hi")]))

    assert result.content == "final answer"
    assert result.tool_results[0].content == "hi"
    assert [message.role for message in result.messages] == ["user", "assistant", "tool", "assistant"]


def test_agent_runtime_executes_model_requested_task_tool(tmp_path):
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
    tools = ToolRegistry()
    register_builtin_tools(tools, context)
    llm = ScriptedModelClient(
        [
            ModelResponse(
                message=Message.from_text(
                    "assistant",
                    "",
                    tool_calls=[
                        ToolCall(
                            id="call-1",
                            name="task.create",
                            arguments={"title": "Plan work", "input": "Create a plan"},
                        )
                    ],
                ),
                stop_reason="tool_calls",
            ),
            ModelResponse(message=Message.from_text("assistant", "task tracked")),
        ]
    )
    runtime = AgentRuntime(model_client=llm, tools=tools, protocol="scripted", model="scripted", enabled_tools=["task.create"])

    result = asyncio.run(runtime.run([Message.from_text("user", "track this")]))
    tasks = asyncio.run(store.list_tasks("tenant", user_id="user", agent_id="agent"))

    assert result.content == "task tracked"
    assert result.tool_results[0].name == "task.create"
    assert result.tool_results[0].raw["task"]["title"] == "Plan work"
    assert tasks[0].title == "Plan work"
    assert tasks[0].metadata["source"] == "tool"


def test_agent_runtime_executes_model_requested_task_run(tmp_path):
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
        async def send(self, prompt, run_id=None, task_id=None):
            return AgentResult(
                content="task result: %s" % prompt,
                messages=[Message.from_text("assistant", "task result")],
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
    tools = ToolRegistry()
    register_builtin_tools(tools, context)
    llm = ScriptedModelClient(
        [
            ModelResponse(
                message=Message.from_text(
                    "assistant",
                    "",
                    tool_calls=[
                        ToolCall(
                            id="call-1",
                            name="task.run",
                            arguments={"title": "Execute work", "input": "ship it"},
                        )
                    ],
                ),
                stop_reason="tool_calls",
            ),
            ModelResponse(message=Message.from_text("assistant", "task executed")),
        ]
    )
    runtime = AgentRuntime(model_client=llm, tools=tools, protocol="scripted", model="scripted", enabled_tools=["task.run"])

    result = asyncio.run(runtime.run([Message.from_text("user", "run this task")]))
    tasks = asyncio.run(store.list_tasks("tenant", user_id="user", agent_id="agent"))

    assert result.content == "task executed"
    assert result.tool_results[0].name == "task.run"
    assert result.tool_results[0].raw["task"]["status"] == "finished"
    assert result.tool_results[0].raw["result"]["content"] == "task result: ship it"
    assert tasks[0].title == "Execute work"
    assert tasks[0].status.value == "finished"
    assert created_children[0][1] == tasks[0].task_id


def test_agent_runtime_executes_model_requested_child_agent(tmp_path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="parent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path)
    parent_spec = AgentSpec.from_overrides(
        tenant_id="tenant",
        user_id="user",
        agent_id="parent",
        workspace_id="workspace",
        workspace_path=str(tmp_path),
    )
    created_children = []

    class ChildSession:
        closed = False

        async def send(self, prompt, run_id=None, task_id=None):
            return AgentResult(
                content="child answer: %s" % prompt,
                messages=[Message.from_text("user", prompt), Message.from_text("assistant", "child answer")],
            )

        async def aclose(self):
            self.closed = True

    async def create_child(spec, task_id=""):
        session = ChildSession()
        created_children.append((spec, task_id, session))
        return session

    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
        agent_spec=parent_spec,
        agent_session_factory=create_child,
    )
    tools = ToolRegistry()
    register_builtin_tools(tools, context)
    llm = ScriptedModelClient(
        [
            ModelResponse(
                message=Message.from_text(
                    "assistant",
                    "",
                    tool_calls=[
                        ToolCall(
                            id="call-1",
                            name="agent.run",
                            arguments={"prompt": "inspect repo", "description": "repo scan", "agent_id": "explorer"},
                        )
                    ],
                ),
                stop_reason="tool_calls",
            ),
            ModelResponse(message=Message.from_text("assistant", "used child")),
        ]
    )
    runtime = AgentRuntime(model_client=llm, tools=tools, protocol="scripted", model="scripted", enabled_tools=["agent.run"])

    result = asyncio.run(runtime.run([Message.from_text("user", "delegate")]))

    assert result.content == "used child"
    assert result.tool_results[0].name == "agent.run"
    assert result.tool_results[0].raw["agent_id"] == "explorer"
    assert result.tool_results[0].raw["content"] == "child answer: inspect repo"
    assert created_children[0][0].agent_id == "explorer"
    assert created_children[0][0].workspace.agent_id == "explorer"
    assert created_children[0][2].closed is True


def test_agent_runtime_executes_model_requested_planning_tools(tmp_path):
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
    tools = ToolRegistry()
    register_builtin_tools(tools, context)
    llm = ScriptedModelClient(
        [
            ModelResponse(
                message=Message.from_text(
                    "assistant",
                    "",
                    tool_calls=[
                        ToolCall(
                            id="call-1",
                            name="todo.write",
                            arguments={
                                "todos": [
                                    {
                                        "content": "Implement planning tools",
                                        "status": "in_progress",
                                        "activeForm": "Implementing planning tools",
                                    },
                                    {"content": "Run checks", "status": "pending", "activeForm": "Running checks"},
                                ]
                            },
                        ),
                        ToolCall(id="call-2", name="plan.enter", arguments={}),
                    ],
                ),
                stop_reason="tool_calls",
            ),
            ModelResponse(
                message=Message.from_text(
                    "assistant",
                    "",
                    tool_calls=[
                        ToolCall(
                            id="call-3",
                            name="plan.exit",
                            arguments={"plan": "Implement todo.write, plan.enter, and plan.exit."},
                        )
                    ],
                ),
                stop_reason="tool_calls",
            ),
            ModelResponse(message=Message.from_text("assistant", "planning tracked")),
        ]
    )
    runtime = AgentRuntime(
        model_client=llm,
        tools=tools,
        protocol="scripted",
        model="scripted",
        enabled_tools=["todo.write", "plan.enter", "plan.exit"],
    )

    result = asyncio.run(runtime.run([Message.from_text("user", "plan this")]))

    assert result.content == "planning tracked"
    assert [item.name for item in result.tool_results] == ["todo.write", "plan.enter", "plan.exit"]
    assert context.todos[0]["content"] == "Implement planning tools"
    assert context.plan_mode is False
    assert context.plan_text == "Implement todo.write, plan.enter, and plan.exit."


def test_agent_runtime_denies_tools_through_permission_policy():
    llm = ScriptedModelClient(
        [
            ModelResponse(
                message=Message.from_text(
                    "assistant",
                    "",
                    tool_calls=[ToolCall(id="call-1", name="dangerous", arguments={})],
                )
            ),
            ModelResponse(message=Message.from_text("assistant", "handled denial")),
        ]
    )
    tools = ToolRegistry()
    tools.register("dangerous", "Dangerous", {}, lambda: "should not run")
    runtime = AgentRuntime(
        model_client=llm,
        tools=tools,
        protocol="scripted",
        model="scripted",
        permission_policy=StaticToolPermissionPolicy(denied_tools={"dangerous"}),
    )

    result = asyncio.run(runtime.run([Message.from_text("user", "run it")]))

    assert result.content == "handled denial"
    assert result.tool_results[0].is_error is True
    assert "denied" in result.tool_results[0].content
    assert result.messages[2].role == "tool"


def test_agent_runtime_pauses_when_tool_requires_approval():
    call = ToolCall(id="call-1", name="dangerous", arguments={})
    llm = ScriptedModelClient([ModelResponse(message=Message.from_text("assistant", "", tool_calls=[call]))])
    store = InMemoryCheckpointStore()
    tools = ToolRegistry()
    ran = {"value": False}
    tools.register("dangerous", "Dangerous", {}, lambda: ran.update(value=True))
    runtime = AgentRuntime(
        model_client=llm,
        tools=tools,
        protocol="scripted",
        model="scripted",
        permission_policy=StaticToolPermissionPolicy(approval_required_tools={"dangerous"}),
        checkpoint_store=store,
    )

    async def execute():
        result = await runtime.run([Message.from_text("user", "run it")], run_id="run-1")
        checkpoint = await store.load("run-1")
        return result, checkpoint

    result, checkpoint = asyncio.run(execute())

    assert result.status == "awaiting_approval"
    assert result.content == "tool approval required"
    assert ran["value"] is False
    assert checkpoint is not None
    assert checkpoint.step == "approval_required"
    assert checkpoint.pending_tool_calls == [call]
    approval_event = next(event for event in result.events if event.type == "tool_approval_required")
    assert approval_event.payload["impact"]["tool_name"] == "dangerous"
    assert approval_event.payload["impact"]["risk"] == "medium"


def test_agent_runtime_resumes_after_tool_approval():
    call = ToolCall(id="call-1", name="echo", arguments={"text": "hi"})
    llm = ScriptedModelClient(
        [
            ModelResponse(message=Message.from_text("assistant", "", tool_calls=[call])),
            ModelResponse(message=Message.from_text("assistant", "approved")),
        ]
    )
    store = InMemoryCheckpointStore()
    tools = ToolRegistry()
    tools.register("echo", "Echo", {}, lambda text: text)
    runtime = AgentRuntime(
        model_client=llm,
        tools=tools,
        protocol="scripted",
        model="scripted",
        permission_policy=StaticToolPermissionPolicy(approval_required_tools={"echo"}),
        checkpoint_store=store,
    )

    async def execute():
        paused = await runtime.run([Message.from_text("user", "say hi")], run_id="run-1")
        resumed = await runtime.resume("run-1", approvals={"call-1": True})
        return paused, resumed

    paused, resumed = asyncio.run(execute())

    assert paused.status == "awaiting_approval"
    assert resumed.status == "finished"
    assert resumed.content == "approved"
    assert resumed.tool_results[0].content == "hi"
    assert [event.type for event in resumed.events if event.type.startswith("tool_approval")] == [
        "tool_approval_required",
        "tool_approval_decision",
    ]
    decision = next(event for event in resumed.events if event.type == "tool_approval_decision")
    assert decision.payload["impact"]["tool_name"] == "echo"
    assert decision.payload["scope"] == "allow_once"


def test_agent_runtime_resumes_after_user_denies_tool_approval():
    call = ToolCall(id="call-1", name="echo", arguments={"text": "hi"})
    llm = ScriptedModelClient(
        [
            ModelResponse(message=Message.from_text("assistant", "", tool_calls=[call])),
            ModelResponse(message=Message.from_text("assistant", "handled denial")),
        ]
    )
    store = InMemoryCheckpointStore()
    tools = ToolRegistry()
    calls = []
    tools.register("echo", "Echo", {}, lambda text: calls.append(text) or text)
    runtime = AgentRuntime(
        model_client=llm,
        tools=tools,
        protocol="scripted",
        model="scripted",
        permission_policy=StaticToolPermissionPolicy(approval_required_tools={"echo"}),
        checkpoint_store=store,
    )

    async def execute():
        paused = await runtime.run([Message.from_text("user", "say hi")], run_id="run-1")
        resumed = await runtime.resume("run-1", approvals={"call-1": False}, approval_scopes={"call-1": "deny"})
        return paused, resumed

    paused, resumed = asyncio.run(execute())

    assert paused.status == "awaiting_approval"
    assert resumed.status == "finished"
    assert resumed.content == "handled denial"
    assert calls == []
    assert resumed.tool_results[0].is_error is True
    assert "denied" in resumed.tool_results[0].content
    assert [message.role for message in resumed.messages] == ["user", "assistant", "tool", "assistant"]
    decision = next(event for event in resumed.events if event.type == "tool_approval_decision")
    assert decision.payload["approved"] is False
    assert decision.payload["scope"] == "deny"


def test_agent_runtime_reuses_run_scoped_tool_approval():
    first_call = ToolCall(id="call-1", name="echo", arguments={"text": "hi"})
    second_call = ToolCall(id="call-2", name="echo", arguments={"text": "hi"})
    llm = ScriptedModelClient(
        [
            ModelResponse(message=Message.from_text("assistant", "", tool_calls=[first_call])),
            ModelResponse(message=Message.from_text("assistant", "", tool_calls=[second_call])),
            ModelResponse(message=Message.from_text("assistant", "done")),
        ]
    )
    store = InMemoryCheckpointStore()
    tools = ToolRegistry()
    calls = []
    tools.register("echo", "Echo", {}, lambda text: calls.append(text) or text)
    runtime = AgentRuntime(
        model_client=llm,
        tools=tools,
        protocol="scripted",
        model="scripted",
        permission_policy=StaticToolPermissionPolicy(approval_required_tools={"echo"}),
        checkpoint_store=store,
    )

    async def execute():
        paused = await runtime.run([Message.from_text("user", "say hi twice")], run_id="run-1")
        resumed = await runtime.resume(
            "run-1",
            approvals={"call-1": True},
            approval_scopes={"call-1": APPROVAL_ALLOW_FOR_RUN},
        )
        checkpoint = await store.load("run-1")
        return paused, resumed, checkpoint

    paused, resumed, checkpoint = asyncio.run(execute())

    assert paused.status == "awaiting_approval"
    assert resumed.status == "finished"
    assert calls == ["hi", "hi"]
    assert [event.type for event in resumed.events if event.type == "tool_approval_required"] == ["tool_approval_required"]
    decisions = [event for event in resumed.events if event.type == "tool_approval_decision"]
    assert [event.payload["scope"] for event in decisions] == ["allow_for_run", "allow_for_run"]
    assert decisions[1].payload["reason"] == "run approval grant"
    assert checkpoint is not None
    assert checkpoint.tool_approval_grants


def test_agent_runtime_approval_grant_does_not_override_hard_denial():
    call = ToolCall(id="call-1", name="echo", arguments={"text": "hi"})
    checkpoint = RuntimeCheckpoint(
        run_id="run-1",
        step="model_response",
        iteration=0,
        messages=[
            Message.from_text("user", "say hi"),
            Message.from_text("assistant", "", tool_calls=[call]),
        ],
        pending_tool_calls=[call],
    )
    store = InMemoryCheckpointStore()

    async def seed_checkpoint():
        await store.save(checkpoint)

    asyncio.run(seed_checkpoint())
    llm = ScriptedModelClient([ModelResponse(message=Message.from_text("assistant", "denied"))])
    tools = ToolRegistry()
    calls = []
    tools.register("echo", "Echo", {}, lambda text: calls.append(text) or text)
    runtime = AgentRuntime(
        model_client=llm,
        tools=tools,
        protocol="scripted",
        model="scripted",
        permission_policy=StaticToolPermissionPolicy(denied_tools={"echo"}),
        checkpoint_store=store,
    )

    result = asyncio.run(
        runtime.resume(
            "run-1",
            approvals={"call-1": True},
            approval_scopes={"call-1": APPROVAL_ALLOW_FOR_RUN},
        )
    )

    assert result.content == "denied"
    assert calls == []
    assert result.tool_results[0].is_error is True
    assert not any(event.type == "tool_approval_decision" for event in result.events)


def test_agent_runtime_saves_finished_checkpoint():
    llm = ScriptedModelClient([ModelResponse(message=Message.from_text("assistant", "done"))])
    store = InMemoryCheckpointStore()
    runtime = AgentRuntime(
        model_client=llm,
        tools=ToolRegistry(),
        protocol="scripted",
        model="scripted",
        checkpoint_store=store,
    )

    async def execute():
        result = await runtime.run([Message.from_text("user", "hi")], run_id="run-1")
        checkpoint = await store.load("run-1")
        return result, checkpoint

    result, checkpoint = asyncio.run(execute())

    assert result.content == "done"
    assert checkpoint is not None
    assert checkpoint.step == "finished"
    assert [message.role for message in checkpoint.messages] == ["user", "assistant"]


def test_agent_session_forwards_run_id_to_runtime_checkpoints():
    llm = ScriptedModelClient([ModelResponse(message=Message.from_text("assistant", "done"))])
    store = InMemoryCheckpointStore()
    runtime = AgentRuntime(
        model_client=llm,
        tools=ToolRegistry(),
        protocol="scripted",
        model="scripted",
        checkpoint_store=store,
    )
    session = AgentSession(runtime=runtime)

    async def execute():
        await session.send("hi", run_id="run-1")
        return await store.load("run-1")

    checkpoint = asyncio.run(execute())

    assert checkpoint is not None
    assert checkpoint.step == "finished"


def test_agent_session_closes_model_client_when_supported():
    class ClosableModel(ScriptedModelClient):
        def __init__(self):
            super().__init__([ModelResponse(message=Message.from_text("assistant", "done"))])
            self.closed = False

        async def async_close(self):
            self.closed = True

    llm = ClosableModel()
    runtime = AgentRuntime(model_client=llm, tools=ToolRegistry(), protocol="scripted", model="scripted")
    session = AgentSession(runtime=runtime)

    asyncio.run(session.aclose())

    assert llm.closed is True


def test_agent_runtime_resumes_pending_tool_checkpoint():
    call = ToolCall(id="call-1", name="echo", arguments={"text": "hi"})
    checkpoint = RuntimeCheckpoint(
        run_id="run-1",
        step="model_response",
        iteration=0,
        messages=[
            Message.from_text("user", "say hi"),
            Message.from_text("assistant", "", tool_calls=[call]),
        ],
        pending_tool_calls=[call],
    )
    store = InMemoryCheckpointStore()

    async def seed_checkpoint():
        await store.save(checkpoint)

    asyncio.run(seed_checkpoint())
    llm = ScriptedModelClient([ModelResponse(message=Message.from_text("assistant", "resumed"))])
    tools = ToolRegistry()
    tools.register("echo", "Echo", {}, lambda text: text)
    runtime = AgentRuntime(
        model_client=llm,
        tools=tools,
        protocol="scripted",
        model="scripted",
        checkpoint_store=store,
    )

    result = asyncio.run(runtime.resume("run-1"))

    assert result.content == "resumed"
    assert result.tool_results[0].content == "hi"
    assert [message.role for message in result.messages] == ["user", "assistant", "tool", "assistant"]


def test_agent_session_commits_history_on_error():
    llm = ScriptedModelClient([])
    tools = ToolRegistry()
    runtime = AgentRuntime(model_client=llm, tools=tools, protocol="scripted", model="scripted")
    session = AgentSession(runtime=runtime, system_prompt="Be concise.")

    result = asyncio.run(session.send("hello"))

    assert result.content.startswith("unexpected error")
    assert [message.role for message in session.messages] == ["system", "user"]


def test_agent_runtime_guard_stops_infinite_tool_loop():
    llm = ScriptedModelClient(
        [
            ModelResponse(
                message=Message.from_text(
                    "assistant",
                    "",
                    tool_calls=[ToolCall(id="call-1", name="echo", arguments={"text": "hi"})],
                )
            )
        ]
    )
    tools = ToolRegistry()
    tools.register("echo", "Echo", {}, lambda text: text)
    runtime = AgentRuntime(
        model_client=llm,
        tools=tools,
        protocol="scripted",
        model="scripted",
        max_tool_iterations=1,
    )

    result = asyncio.run(runtime.run([Message.from_text("user", "loop")]))

    assert "exceeded max iterations" in result.content
    assert any(event.type == "error" for event in result.events)


def test_agent_runtime_default_allows_unbounded_tool_iterations():
    responses = [
        ModelResponse(
            message=Message.from_text(
                "assistant",
                "",
                tool_calls=[ToolCall(id=f"call-{index}", name="echo", arguments={"text": str(index)})],
            )
        )
        for index in range(9)
    ]
    responses.append(ModelResponse(message=Message.from_text("assistant", "done")))
    llm = ScriptedModelClient(responses)
    tools = ToolRegistry()
    tools.register("echo", "Echo", {}, lambda text: text)
    runtime = AgentRuntime(model_client=llm, tools=tools, protocol="scripted", model="scripted")

    result = asyncio.run(runtime.run([Message.from_text("user", "loop until done")]))

    assert result.content == "done"
    assert len(result.tool_results) == 9


def test_agent_runtime_streams_text_and_tool_events():
    llm = ScriptedModelClient(
        [
            [
                ModelStreamEvent(type="text_delta", delta="hel"),
                ModelStreamEvent(type="text_delta", delta="lo"),
                ModelStreamEvent(type="message", response=ModelResponse(message=Message.from_text("assistant", "hello"))),
            ]
        ]
    )
    runtime = AgentRuntime(model_client=llm, tools=ToolRegistry(), protocol="scripted", model="scripted")

    async def collect():
        return [event async for event in runtime.stream([Message.from_text("user", "hi")])]

    events = asyncio.run(collect())

    assert [event.type for event in events] == ["text_delta", "text_delta", "done"]
    assert "".join(event.payload.get("delta", "") for event in events) == "hello"


def test_agent_runtime_streams_reasoning_events():
    llm = ScriptedModelClient(
        [
            [
                ModelStreamEvent(type="reasoning_delta", delta="think"),
                ModelStreamEvent(type="message", response=ModelResponse(message=Message.from_text("assistant", "done"))),
            ]
        ]
    )
    runtime = AgentRuntime(model_client=llm, tools=ToolRegistry(), protocol="scripted", model="scripted")

    async def collect():
        return [event async for event in runtime.stream([Message.from_text("user", "hi")])]

    events = asyncio.run(collect())

    assert [event.type for event in events] == ["reasoning_delta", "done"]
    assert events[0].payload["delta"] == "think"


def test_agent_runtime_stream_continues_after_tool_error_result():
    call = ToolCall(id="call-1", name="boom", arguments={})
    llm = ScriptedModelClient(
        [
            [ModelStreamEvent(type="message", response=ModelResponse(message=Message.from_text("assistant", "", tool_calls=[call])))],
            [
                ModelStreamEvent(type="text_delta", delta="handled tool failure"),
                ModelStreamEvent(type="message", response=ModelResponse(message=Message.from_text("assistant", "handled tool failure"))),
            ],
        ]
    )
    tools = ToolRegistry()

    def fail():
        raise RuntimeError("tool exploded")

    tools.register("boom", "Boom", {}, fail)
    runtime = AgentRuntime(model_client=llm, tools=tools, protocol="scripted", model="scripted")

    async def collect():
        return [event async for event in runtime.stream([Message.from_text("user", "run failing tool")])]

    events = asyncio.run(collect())

    assert [event.type for event in events] == ["tool_start", "tool_result", "text_delta", "done"]
    tool_result = events[1]
    assert tool_result.payload["is_error"] is True
    assert tool_result.payload["content"] == "tool exploded"
    assert events[-1].payload["content"] == "handled tool failure"


def test_agent_runtime_stream_does_not_emit_tool_start_for_hook_denied_tool():
    call = ToolCall(id="call-1", name="shell.run", arguments={"cmd": "echo hi"})
    llm = ScriptedModelClient(
        [
            [ModelStreamEvent(type="message", response=ModelResponse(message=Message.from_text("assistant", "", tool_calls=[call])))],
            [
                ModelStreamEvent(type="text_delta", delta="handled deny"),
                ModelStreamEvent(type="message", response=ModelResponse(message=Message.from_text("assistant", "handled deny"))),
            ],
        ]
    )
    tools = ToolRegistry()
    tools.register("shell.run", "Shell", {}, lambda cmd: cmd)
    registry = SessionHookRegistry()
    registry.add(event="pre_tool_use", name="block-shell", action="deny_tool", tool="shell.run", content="shell blocked")
    runtime = AgentRuntime(
        model_client=llm,
        tools=tools,
        protocol="scripted",
        model="scripted",
        hooks=SessionStateHooks(registry),
    )

    async def collect():
        return [event async for event in runtime.stream([Message.from_text("user", "run shell")])]

    events = asyncio.run(collect())

    assert [event.type for event in events] == ["tool_result", "text_delta", "done"]
    assert events[0].payload["is_error"] is True
    assert events[0].payload["content"] == "shell blocked"


def test_agent_runtime_stream_done_uses_error_content_on_failure():
    llm = ScriptedModelClient([])
    runtime = AgentRuntime(model_client=llm, tools=ToolRegistry(), protocol="scripted", model="scripted")

    async def collect():
        return [event async for event in runtime.stream([Message.from_text("user", "hi")])]

    events = asyncio.run(collect())

    assert events[-2].type == "error"
    assert events[-1].type == "done"
    assert events[-1].payload["content"].startswith("unexpected error")
    assert events[-1].payload["error"].startswith("unexpected error")


def test_agent_runtime_stream_done_reports_checkpoint_event_count_for_approval_resume():
    call = ToolCall(id="call-1", name="echo", arguments={"text": "hi"})
    llm = ScriptedModelClient([ModelResponse(message=Message.from_text("assistant", "", tool_calls=[call]))])
    store = InMemoryCheckpointStore()
    tools = ToolRegistry()
    tools.register("echo", "Echo", {}, lambda text: text)
    runtime = AgentRuntime(
        model_client=llm,
        tools=tools,
        protocol="scripted",
        model="scripted",
        permission_policy=StaticToolPermissionPolicy(approval_required_tools={"echo"}),
        checkpoint_store=store,
    )

    async def collect():
        events = [event async for event in runtime.stream([Message.from_text("user", "hi")], run_id="run-1")]
        checkpoint = await store.load("run-1")
        return events, checkpoint

    events, checkpoint = asyncio.run(collect())

    assert [event.type for event in events] == ["tool_approval_required", "done"]
    assert checkpoint is not None
    assert events[-1].payload["status"] == "awaiting_approval"
    assert events[-1].payload["event_count"] == len(checkpoint.events) == 2


def test_agent_runtime_resume_stream_continues_after_tool_approval():
    call = ToolCall(id="call-1", name="echo", arguments={"text": "hi"})
    llm = ScriptedModelClient(
        [
            ModelResponse(message=Message.from_text("assistant", "", tool_calls=[call])),
            [
                ModelStreamEvent(type="text_delta", delta="approved"),
                ModelStreamEvent(type="message", response=ModelResponse(message=Message.from_text("assistant", "approved"))),
            ],
        ]
    )
    store = InMemoryCheckpointStore()
    tools = ToolRegistry()
    tools.register("echo", "Echo", {}, lambda text: text)
    runtime = AgentRuntime(
        model_client=llm,
        tools=tools,
        protocol="scripted",
        model="scripted",
        permission_policy=StaticToolPermissionPolicy(approval_required_tools={"echo"}),
        checkpoint_store=store,
    )

    async def execute():
        paused_events = [event async for event in runtime.stream([Message.from_text("user", "hi")], run_id="run-1")]
        resumed_events = [event async for event in runtime.resume_stream("run-1", approvals={"call-1": True})]
        checkpoint = await store.load("run-1")
        return paused_events, resumed_events, checkpoint

    paused_events, resumed_events, checkpoint = asyncio.run(execute())

    assert paused_events[-1].payload["status"] == "awaiting_approval"
    assert [event.type for event in resumed_events] == [
        "tool_approval_decision",
        "tool_start",
        "tool_result",
        "text_delta",
        "done",
    ]
    assert resumed_events[-1].payload["status"] == "finished"
    assert resumed_events[-1].payload["event_count"] == len(checkpoint.events)


def test_agent_session_resume_stream_commits_completed_history():
    call = ToolCall(id="call-1", name="echo", arguments={"text": "hi"})
    llm = ScriptedModelClient(
        [
            ModelResponse(message=Message.from_text("assistant", "", tool_calls=[call])),
            ModelResponse(message=Message.from_text("assistant", "approved")),
        ]
    )
    store = InMemoryCheckpointStore()
    tools = ToolRegistry()
    tools.register("echo", "Echo", {}, lambda text: text)
    runtime = AgentRuntime(
        model_client=llm,
        tools=tools,
        protocol="scripted",
        model="scripted",
        permission_policy=StaticToolPermissionPolicy(approval_required_tools={"echo"}),
        checkpoint_store=store,
    )
    session = AgentSession(runtime=runtime, system_prompt="Be concise.")

    async def execute():
        await session.send("hi", run_id="run-1")
        return [event async for event in session.resume_stream("run-1", approvals={"call-1": True})]

    events = asyncio.run(execute())

    assert events[-1].type == "done"
    assert [message.role for message in session.messages] == ["system", "user", "assistant", "tool", "assistant"]
    assert session.messages[-1].content_text() == "approved"


def test_agent_session_manual_compact_summarizes_older_messages():
    llm = ScriptedModelClient([ModelResponse(message=Message.from_text("assistant", "done"))])
    runtime = AgentRuntime(model_client=llm, tools=ToolRegistry(), protocol="scripted", model="scripted")
    session = AgentSession(runtime=runtime, system_prompt="Be concise.", compaction_target_tokens=8)
    session.messages.extend(
        [
            Message.from_text("user", "old request " + ("alpha " * 80)),
            Message.from_text("assistant", "old answer " + ("beta " * 80)),
            Message.from_text("user", "recent request"),
            Message.from_text("assistant", "recent answer"),
        ]
    )

    stats = session.compact(target_tokens=8)

    assert stats["dropped_messages"] > 0
    assert session.messages[0].content_text() == "Be concise."
    assert session.messages[1].content_text().startswith("Prior conversation summary:")
    assert session.messages[-1].content_text() == "recent answer"


def test_agent_session_stream_commits_completed_history():
    llm = ScriptedModelClient(
        [
            [
                ModelStreamEvent(type="text_delta", delta="hello"),
                ModelStreamEvent(type="message", response=ModelResponse(message=Message.from_text("assistant", "hello"))),
            ]
        ]
    )
    runtime = AgentRuntime(model_client=llm, tools=ToolRegistry(), protocol="scripted", model="scripted")
    session = AgentSession(runtime=runtime, system_prompt="Be concise.")

    async def drain():
        return [event async for event in session.stream("hi")]

    asyncio.run(drain())

    assert [message.role for message in session.messages] == ["system", "user", "assistant"]
    assert session.messages[-1].content_text() == "hello"
