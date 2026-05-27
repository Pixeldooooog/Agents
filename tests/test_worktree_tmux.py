import asyncio
import subprocess
from pathlib import Path

import pytest

from agents.kernel.capabilities.sandbox.local import LocalSandboxProvider
from agents.kernel.capabilities.tools import ToolRuntimeContext, register_builtin_tools
from agents.kernel.capabilities.tools.builtin import worktree_tmux
from agents.kernel.capabilities.tools.registry import ToolRegistry
from agents.kernel.context.workspace import WorkspaceContext
from agents.kernel.governance import SandboxPolicy
from agents.kernel.specs import AgentSpec


def test_worktree_tmux_metadata_creates_and_kills_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    repo = _git_repo(tmp_path)
    commands: list[list[str]] = []

    def fake_tmux(args: list[str]) -> worktree_tmux.TmuxCommandResult:
        commands.append(args)
        return worktree_tmux.TmuxCommandResult(returncode=0)

    monkeypatch.setattr(worktree_tmux, "_run_tmux", fake_tmux)
    context = _tool_context(tmp_path, repo, AgentSpec(metadata={"worktree": {"tmux": True}}))
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    entered = asyncio.run(registry.execute("worktree.enter", {"name": "tmux-test"}))
    removed = asyncio.run(registry.execute("worktree.exit", {"action": "remove"}))

    session_name = "repo_worktree-tmux-test"
    assert entered.is_error is False
    assert entered.raw["tmuxSessionName"] == session_name
    assert entered.raw["tmuxCreated"] is True
    assert context.active_worktree_session == {}
    assert removed.raw["tmuxSessionName"] == session_name
    assert removed.raw["tmuxTerminated"] is True
    assert commands == [
        ["new-session", "-d", "-s", session_name, "-c", entered.raw["worktreePath"]],
        ["kill-session", "-t", session_name],
    ]


def test_worktree_keep_preserves_tmux_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    repo = _git_repo(tmp_path)
    commands: list[list[str]] = []

    def fake_tmux(args: list[str]) -> worktree_tmux.TmuxCommandResult:
        commands.append(args)
        return worktree_tmux.TmuxCommandResult(returncode=0)

    monkeypatch.setattr(worktree_tmux, "_run_tmux", fake_tmux)
    context = _tool_context(tmp_path, repo, AgentSpec(metadata={"worktree": {"tmuxEnabled": True}}))
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    entered = asyncio.run(registry.execute("EnterWorktree", {"name": "keep-tmux"}))
    kept = asyncio.run(registry.execute("ExitWorktree", {"action": "keep"}))

    assert kept.is_error is False
    assert kept.raw["tmuxSessionName"] == entered.raw["tmuxSessionName"]
    assert "tmux attach -t %s" % entered.raw["tmuxSessionName"] in kept.content
    assert commands == [["new-session", "-d", "-s", entered.raw["tmuxSessionName"], "-c", entered.raw["worktreePath"]]]


def test_worktree_tmux_creation_failure_is_nonfatal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    repo = _git_repo(tmp_path)

    def fake_tmux(args: list[str]) -> worktree_tmux.TmuxCommandResult:
        return worktree_tmux.TmuxCommandResult(returncode=1, stderr="tmux missing")

    monkeypatch.setattr(worktree_tmux, "_run_tmux", fake_tmux)
    context = _tool_context(tmp_path, repo, AgentSpec(metadata={"worktree": {"tmux": True}}))
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    entered = asyncio.run(registry.execute("worktree.enter", {"name": "tmux-fail"}))
    removed = asyncio.run(registry.execute("worktree.exit", {"action": "remove"}))

    assert entered.is_error is False
    assert entered.raw["tmuxSessionName"] == "repo_worktree-tmux-fail"
    assert entered.raw["tmuxCreated"] is False
    assert entered.raw["tmuxError"] == "tmux missing"
    assert removed.is_error is False


def _tool_context(tmp_path: Path, repo: Path, agent_spec: AgentSpec) -> ToolRuntimeContext:
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=repo,
    )
    policy = SandboxPolicy.for_workspace(workspace.path, allow_file_write=True, allow_process=True)
    return ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
        agent_spec=agent_spec,
    )


def _git_repo(tmp_path: Path) -> Path:
    if _run(["git", "--version"], tmp_path).returncode != 0:
        pytest.skip("git is not installed")
    repo = tmp_path / "repo"
    repo.mkdir()
    _run(["git", "init"], repo, check=True)
    _run(["git", "config", "user.email", "agent@example.com"], repo, check=True)
    _run(["git", "config", "user.name", "Agent Test"], repo, check=True)
    (repo / "README.md").write_text("hello\n", encoding="utf-8")
    _run(["git", "add", "README.md"], repo, check=True)
    _run(["git", "commit", "-m", "initial"], repo, check=True)
    return repo


def _run(args: list[str], cwd: Path, *, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=str(cwd), text=True, capture_output=True, check=check)
