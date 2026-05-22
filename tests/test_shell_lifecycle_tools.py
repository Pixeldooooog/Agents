import asyncio
import shlex
import sys
from pathlib import Path

from agents.kernel.capabilities.sandbox.local import LocalSandboxProvider
from agents.kernel.capabilities.tools import ToolRegistry, ToolRuntimeContext, register_builtin_tools
from agents.kernel.context.workspace import WorkspaceContext
from agents.kernel.governance import SandboxPolicy
from agents.kernel.runtime import AgentRuntime, ScriptedModelClient
from agents.kernel.schema import Message, ModelResponse, ToolCall
from agents.kernel.specs import AgentSpec


def _context_and_registry(
    tmp_path: Path,
    *,
    metadata: dict | None = None,
    subagent_depth: int = 0,
) -> tuple[ToolRuntimeContext, ToolRegistry]:
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(
        workspace.path,
        allow_process=True,
        allowed_commands=(Path(sys.executable).name,),
    )
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
        agent_spec=AgentSpec(metadata=dict(metadata or {})),
        subagent_depth=subagent_depth,
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)
    return context, registry


def _registry(tmp_path: Path, *, metadata: dict | None = None, subagent_depth: int = 0) -> ToolRegistry:
    _, registry = _context_and_registry(tmp_path, metadata=metadata, subagent_depth=subagent_depth)
    return registry


def test_shell_run_assistant_auto_backgrounds_long_main_agent_command(tmp_path: Path):
    registry = _registry(tmp_path, metadata={"shellAssistantAutoBackgroundAfterSeconds": 0.05})

    async def execute():
        script = "import time; print('start', flush=True); time.sleep(0.2); print('done', flush=True)"
        started = await registry.execute(
            "shell.run",
            {
                "command": "%s -c %s" % (shlex.quote(sys.executable), shlex.quote(script)),
                "timeout_seconds": 2,
                "description": "Run slow command",
            },
        )
        final = await registry.execute(
            "shell.output",
            {"task_id": started.raw["backgroundTaskId"], "block": True, "timeout_seconds": 2},
        )
        return started, final

    started, final = asyncio.run(execute())

    assert started.is_error is False
    assert started.raw["background"] is True
    assert started.raw["backgroundTaskId"] == started.raw["task_id"]
    assert started.raw["assistantAutoBackgrounded"] is True
    assert started.raw["backgroundedByUser"] is False
    assert started.raw["description"] == "Run slow command"
    assert final.raw["retrieval_status"] == "success"
    assert final.raw["task"]["status"] == "completed"
    assert final.raw["output"] == "start\ndone\n"


def test_shell_run_assistant_auto_background_keeps_fast_command_foreground(tmp_path: Path):
    registry = _registry(tmp_path, metadata={"shellAssistantAutoBackgroundAfterSeconds": 1.0})

    result = asyncio.run(
        registry.execute(
            "shell.run",
            {
                "command": "%s -c %s" % (shlex.quote(sys.executable), shlex.quote("print('quick')")),
                "timeout_seconds": 2,
            },
        )
    )

    assert result.is_error is False
    assert result.raw["background"] is False
    assert "backgroundTaskId" not in result.raw
    assert result.raw["stdout"] == "quick\n"


def test_shell_run_assistant_auto_background_skips_subagents(tmp_path: Path):
    registry = _registry(
        tmp_path,
        metadata={"shellAssistantAutoBackgroundAfterSeconds": 0.01},
        subagent_depth=1,
    )

    result = asyncio.run(
        registry.execute(
            "shell.run",
            {
                "command": "%s -c %s" % (shlex.quote(sys.executable), shlex.quote("print('subagent')")),
                "timeout_seconds": 2,
            },
        )
    )

    assert result.is_error is False
    assert result.raw["background"] is False
    assert result.raw["stdout"] == "subagent\n"


def test_shell_run_streams_progress_and_stall_runtime_events(tmp_path: Path):
    _, registry = _context_and_registry(
        tmp_path,
        metadata={
            "shellAssistantAutoBackground": False,
            "shellProgressAfterSeconds": 0.02,
            "shellProgressIntervalSeconds": 0.05,
            "shellStallAfterSeconds": 0.05,
        },
    )
    marker = tmp_path / "done-marker"
    script = (
        "import pathlib, time; "
        "print('start', flush=True); "
        "time.sleep(0.2); "
        "pathlib.Path('done-marker').write_text('done'); "
        "print('done', flush=True)"
    )
    command = "%s -c %s" % (shlex.quote(sys.executable), shlex.quote(script))
    llm = ScriptedModelClient(
        [
            ModelResponse(
                message=Message.from_text(
                    "assistant",
                    "",
                    tool_calls=[ToolCall(id="call-shell", name="shell.run", arguments={"command": command})],
                ),
                stop_reason="tool_calls",
            ),
            ModelResponse(message=Message.from_text("assistant", "finished")),
        ]
    )
    runtime = AgentRuntime(
        model_client=llm,
        tools=registry,
        protocol="scripted",
        model="scripted",
        enabled_tools=["shell.run"],
    )

    async def collect():
        events = []
        progress_seen_before_completion = False
        async for event in runtime.stream([Message.from_text("user", "run shell")], run_id="run-shell-progress"):
            events.append(event)
            if event.type == "tool_progress" and event.payload.get("status") == "running" and not marker.exists():
                progress_seen_before_completion = True
        return events, progress_seen_before_completion

    events, progress_seen_before_completion = asyncio.run(collect())
    event_types = [event.type for event in events]
    progress_events = [event for event in events if event.type == "tool_progress"]
    tool_result = next(event for event in events if event.type == "tool_result")

    assert progress_seen_before_completion is True
    assert event_types.index("tool_start") < event_types.index("tool_progress") < event_types.index("tool_result")
    assert any(event.payload["status"] == "running" for event in progress_events)
    assert any(event.payload["status"] == "stalled" for event in progress_events)
    assert progress_events[0].payload["tool_call_id"] == "call-shell"
    assert progress_events[0].payload["task_id"].startswith("shell_")
    assert progress_events[0].payload["metadata"]["progress_type"] == "bash_progress"
    assert tool_result.payload["raw"]["background"] is False
    assert "backgroundTaskId" not in tool_result.payload["raw"]
