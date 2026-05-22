import asyncio
import shlex
import sys
from pathlib import Path

from agents.kernel.capabilities.sandbox.local import LocalSandboxProvider
from agents.kernel.capabilities.tools import ToolRegistry, ToolRuntimeContext, register_builtin_tools
from agents.kernel.context.workspace import WorkspaceContext
from agents.kernel.governance import SandboxPolicy
from agents.kernel.specs import AgentSpec


def _registry(tmp_path: Path, *, metadata: dict | None = None, subagent_depth: int = 0) -> ToolRegistry:
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
