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
from agents.kernel.capabilities.tools.builtin.shell_prompt_stall import looks_like_shell_prompt


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


def test_shell_background_task_emits_started_and_terminal_runtime_events(tmp_path: Path):
    _, registry = _context_and_registry(tmp_path)

    async def execute():
        events = []
        script = "import time; print('start', flush=True); time.sleep(0.05); print('done', flush=True)"
        with registry.runtime_event_sink(events.append):
            started = await registry.execute(
                "shell.run",
                {
                    "command": "%s -c %s" % (shlex.quote(sys.executable), shlex.quote(script)),
                    "run_in_background": True,
                    "timeout_seconds": 2,
                    "description": "Run background notifier",
                },
                tool_call_id="call-shell-run",
            )
            final = await registry.execute(
                "shell.output",
                {"task_id": started.raw["backgroundTaskId"], "block": True, "timeout_seconds": 2},
                tool_call_id="call-shell-output",
            )
            repeated = await registry.execute(
                "shell.output",
                {"task_id": started.raw["backgroundTaskId"], "block": False},
                tool_call_id="call-shell-output-repeat",
            )
        return events, started, final, repeated

    events, started, final, repeated = asyncio.run(execute())
    task_events = [event for event in events if event.type in {"task_started", "task_notification"}]

    assert started.is_error is False
    assert final.is_error is False
    assert repeated.is_error is False
    assert [event.type for event in task_events] == ["task_started", "task_notification"]
    assert task_events[0].payload["task_id"] == started.raw["backgroundTaskId"]
    assert task_events[0].payload["tool_call_id"] == "call-shell-run"
    assert task_events[0].payload["task_type"] == "shell"
    assert task_events[1].payload["task_id"] == started.raw["backgroundTaskId"]
    assert task_events[1].payload["tool_call_id"] == "call-shell-output"
    assert task_events[1].payload["status"] == "completed"
    assert task_events[1].payload["output_file"] == started.raw["output_path"]
    assert task_events[1].payload["summary"] == "start\ndone"


def test_shell_background_completion_enqueues_async_notification(tmp_path: Path):
    context, registry = _context_and_registry(tmp_path)
    queued = []
    context.async_message_enqueue = queued.append

    async def execute():
        script = "import time; print('start', flush=True); time.sleep(0.05); print('done', flush=True)"
        started = await registry.execute(
            "shell.run",
            {
                "command": "%s -c %s" % (shlex.quote(sys.executable), shlex.quote(script)),
                "run_in_background": True,
                "timeout_seconds": 2,
                "description": "Run async notification script",
            },
        )
        handle = context.background_commands[started.raw["task_id"]]
        await handle._task
        await asyncio.sleep(0)
        return started

    started = asyncio.run(execute())

    assert started.is_error is False
    assert len(queued) == 1
    assert queued[0]["priority"] == "later"
    assert queued[0]["isSynthetic"] is True
    text = queued[0]["message"]["content"][0]["text"]
    assert "<task_notification>" in text
    assert "<task_id>%s</task_id>" % started.raw["task_id"] in text
    assert "<output_file>%s</output_file>" % started.raw["output_path"] in text
    assert "<status>completed</status>" in text
    assert "Background Bash command &quot;Run async notification script&quot; completed" in text
    assert "Last output:\nstart\ndone" in text


def test_shell_background_prompt_stall_enqueues_next_notification(tmp_path: Path):
    context, registry = _context_and_registry(
        tmp_path,
        metadata={
            "shellPromptStallAfterSeconds": 0.05,
            "shellPromptStallIntervalSeconds": 0.02,
        },
    )
    queued = []
    context.async_message_enqueue = queued.append

    async def execute():
        script = "import time; print('Continue? ', end='', flush=True); time.sleep(0.5)"
        started = await registry.execute(
            "shell.run",
            {
                "command": "%s -c %s" % (shlex.quote(sys.executable), shlex.quote(script)),
                "run_in_background": True,
                "timeout_seconds": 2,
                "description": "Run interactive prompt script",
            },
        )
        for _ in range(30):
            if queued:
                break
            await asyncio.sleep(0.02)
        killed = await registry.execute("shell.kill", {"task_id": started.raw["task_id"]})
        return started, killed

    started, killed = asyncio.run(execute())

    assert started.is_error is False
    assert killed.is_error is False
    assert len(queued) == 1
    assert queued[0]["priority"] == "next"
    text = queued[0]["message"]["content"][0]["text"]
    assert "<task_id>%s</task_id>" % started.raw["task_id"] in text
    assert "<status>" not in text
    assert "appears to be waiting for interactive input" in text
    assert "Last output:\nContinue?" in text


def test_shell_prompt_detection_uses_last_output_line():
    assert looks_like_shell_prompt("build output\nReady to continue?") is True
    assert looks_like_shell_prompt("first prompt? \nmore build output") is False


def test_shell_output_block_claim_suppresses_async_completion_notification(tmp_path: Path):
    context, registry = _context_and_registry(tmp_path)
    queued = []
    context.async_message_enqueue = queued.append

    async def execute():
        script = "import time; print('start', flush=True); time.sleep(0.05); print('done', flush=True)"
        started = await registry.execute(
            "shell.run",
            {
                "command": "%s -c %s" % (shlex.quote(sys.executable), shlex.quote(script)),
                "run_in_background": True,
                "timeout_seconds": 2,
            },
        )
        final = await registry.execute(
            "shell.output",
            {"task_id": started.raw["task_id"], "block": True, "timeout_seconds": 2},
        )
        await asyncio.sleep(0)
        return started, final

    started, final = asyncio.run(execute())

    assert started.is_error is False
    assert final.is_error is False
    assert final.raw["retrieval_status"] == "success"
    assert queued == []


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
