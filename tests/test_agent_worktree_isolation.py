import asyncio
import subprocess
from pathlib import Path

import pytest

from agents.kernel.capabilities.tools import ToolRuntimeContext, register_builtin_tools
from agents.kernel.capabilities.tools.builtin.agents import agent_run
from agents.kernel.capabilities.tools.registry import ToolRegistry
from agents.kernel.context.workspace import WorkspaceContext
from agents.kernel.governance import SandboxPolicy
from agents.kernel.runtime import AgentResult
from agents.kernel.schema import Message
from agents.kernel.specs import AgentSpec
from agents.kernel.tasks import InMemoryTaskStore


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=str(cwd), text=True, capture_output=True, check=True)


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True)
    _git(path, "init")
    _git(path, "config", "user.email", "agents-test@example.com")
    _git(path, "config", "user.name", "Agents Test")
    (path / "README.md").write_text("hello\n", encoding="utf-8")
    _git(path, "add", "README.md")
    _git(path, "commit", "-m", "init")


def _context(repo: Path, factory, *, task_store=None) -> ToolRuntimeContext:
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=repo,
        path=repo,
    )
    return ToolRuntimeContext(
        workspace=workspace,
        sandbox=SandboxPolicy.for_workspace(workspace.path),
        agent_spec=AgentSpec.from_overrides(
            tenant_id="tenant",
            user_id="user",
            agent_id="agent",
            workspace_id="workspace",
            workspace_path=str(repo),
        ),
        agent_session_factory=factory,
        task_store=task_store,
    )


def test_agent_run_worktree_isolation_removes_clean_child_worktree(tmp_path: Path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    created_specs = []

    class ChildSession:
        async def send(self, text, run_id=None, task_id=None):
            return AgentResult(content="ok", messages=[Message.from_text("assistant", text)])

    async def create_child(child_spec, task_id=""):
        created_specs.append(child_spec)
        return ChildSession()

    result = asyncio.run(agent_run(_context(repo, create_child), prompt="inspect", agent_id="researcher", isolation="worktree"))
    child_path = Path(created_specs[0].workspace.path)

    assert result["content"] == "ok"
    assert result["worktreeKept"] is False
    assert result["worktreeChangedFiles"] == 0
    assert child_path.parent == repo / ".agents" / "worktrees"
    assert child_path.name.startswith("agent-researcher-")
    assert child_path.exists() is False


def test_agent_run_worktree_isolation_cleans_up_when_child_close_fails(tmp_path: Path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    created_specs = []

    class ChildSession:
        async def send(self, text, run_id=None, task_id=None):
            return AgentResult(content="ok", messages=[Message.from_text("assistant", text)])

        async def aclose(self):
            raise RuntimeError("close failed")

    async def create_child(child_spec, task_id=""):
        created_specs.append(child_spec)
        return ChildSession()

    with pytest.raises(RuntimeError, match="close failed"):
        asyncio.run(agent_run(_context(repo, create_child), prompt="inspect", agent_id="closer", isolation="worktree"))

    child_path = Path(created_specs[0].workspace.path)
    assert child_path.parent == repo / ".agents" / "worktrees"
    assert child_path.exists() is False


def test_agent_run_worktree_isolation_keeps_dirty_child_worktree(tmp_path: Path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    created_specs = []

    class ChildSession:
        def __init__(self, workspace_path: str):
            self.workspace_path = Path(workspace_path)

        async def send(self, text, run_id=None, task_id=None):
            (self.workspace_path / "child.txt").write_text("dirty\n", encoding="utf-8")
            return AgentResult(content="dirty", messages=[Message.from_text("assistant", text)])

    async def create_child(child_spec, task_id=""):
        created_specs.append(child_spec)
        return ChildSession(child_spec.workspace.path)

    result = asyncio.run(agent_run(_context(repo, create_child), prompt="edit", agent_id="writer", isolation="worktree"))
    child_path = Path(created_specs[0].workspace.path)

    assert result["content"] == "dirty"
    assert result["worktreePath"] == str(child_path)
    assert result["worktreeBranch"].startswith("worktree-agent-writer-")
    assert result["worktreeKept"] is True
    assert result["worktreeChangedFiles"] == 1
    assert (child_path / "child.txt").read_text(encoding="utf-8") == "dirty\n"


def test_agent_run_cwd_override_stays_inside_workspace(tmp_path: Path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    subdir = repo / "pkg"
    subdir.mkdir()
    created_specs = []

    class ChildSession:
        async def send(self, text, run_id=None, task_id=None):
            return AgentResult(content="cwd", messages=[Message.from_text("assistant", text)])

    async def create_child(child_spec, task_id=""):
        created_specs.append(child_spec)
        return ChildSession()

    result = asyncio.run(agent_run(_context(repo, create_child), prompt="inspect", cwd="pkg"))

    assert result["content"] == "cwd"
    assert Path(created_specs[0].workspace.path) == subdir.resolve()
    assert "worktreeKept" not in result


def test_agent_run_cwd_override_cannot_escape_workspace(tmp_path: Path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    created_specs = []

    async def create_child(child_spec, task_id=""):
        created_specs.append(child_spec)
        raise AssertionError("child session should not be created")

    with pytest.raises(ValueError, match="inside the current workspace"):
        asyncio.run(agent_run(_context(repo, create_child), prompt="inspect", cwd="../outside"))

    assert created_specs == []


def test_src_origin_agent_alias_passes_worktree_isolation(tmp_path: Path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    created_specs = []

    class ChildSession:
        async def send(self, text, run_id=None, task_id=None):
            return AgentResult(content="alias", messages=[Message.from_text("assistant", text)])

    async def create_child(child_spec, task_id=""):
        created_specs.append(child_spec)
        return ChildSession()

    registry = ToolRegistry()
    register_builtin_tools(registry, _context(repo, create_child))

    result = asyncio.run(
        registry.execute(
            "Agent",
            {"description": "Inspect", "prompt": "inspect", "name": "aliased", "isolation": "worktree"},
        )
    )

    assert result.is_error is False
    assert result.raw["content"] == "alias"
    assert result.raw["worktreeKept"] is False
    assert Path(created_specs[0].workspace.path).name.startswith("agent-aliased-")


def test_background_agent_alias_uses_worktree_isolation_for_child_session(tmp_path: Path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    created_specs = []
    store = InMemoryTaskStore()

    class ChildSession:
        async def send(self, text, run_id=None, task_id=None):
            return AgentResult(content="background", messages=[Message.from_text("assistant", text)])

    async def create_child(child_spec, task_id=""):
        created_specs.append(child_spec)
        return ChildSession()

    context = _context(repo, create_child, task_store=store)
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    async def run_background():
        started = await registry.execute(
            "Agent",
            {"description": "Inspect", "prompt": "inspect", "name": "bg", "run_in_background": True, "isolation": "worktree"},
        )
        task_id = started.raw["agentId"]
        await context.background_tasks[task_id]
        return started

    result = asyncio.run(run_background())
    child_path = Path(created_specs[0].workspace.path)

    assert result.raw["status"] == "async_launched"
    assert child_path.parent == repo / ".agents" / "worktrees"
    assert child_path.name.startswith("agent-bg-")
    assert child_path.exists() is False


def test_background_task_alias_keeps_dirty_worktree_in_output(tmp_path: Path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    created_specs = []
    store = InMemoryTaskStore()

    class ChildSession:
        def __init__(self, workspace_path: str):
            self.workspace_path = Path(workspace_path)

        async def send(self, text, run_id=None, task_id=None):
            (self.workspace_path / "child.txt").write_text("dirty\n", encoding="utf-8")
            return AgentResult(content="changed", messages=[Message.from_text("assistant", text)])

    async def create_child(child_spec, task_id=""):
        created_specs.append(child_spec)
        return ChildSession(child_spec.workspace.path)

    context = _context(repo, create_child, task_store=store)
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    async def run_background():
        started = await registry.execute(
            "Task",
            {"description": "Edit", "prompt": "edit", "name": "writer", "run_in_background": True, "isolation": "worktree"},
        )
        task_id = started.raw["agentId"]
        await context.background_tasks[task_id]
        return await registry.execute("task.output", {"task_id": task_id}), context.background_task_results[task_id]

    output, background_result = asyncio.run(run_background())
    child_path = Path(created_specs[0].workspace.path)

    assert child_path.exists() is True
    assert (child_path / "child.txt").read_text(encoding="utf-8") == "dirty\n"
    assert "worktreePath: %s" % child_path in output.raw["output"]
    assert "worktreeBranch: worktree-agent-writer-" in output.raw["output"]
    assert background_result["worktreePath"] == str(child_path)
    assert background_result["worktreeBranch"].startswith("worktree-agent-writer-")


def test_background_agent_alias_uses_cwd_override_for_child_session(tmp_path: Path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    subdir = repo / "pkg"
    subdir.mkdir()
    created_specs = []
    store = InMemoryTaskStore()

    class ChildSession:
        async def send(self, text, run_id=None, task_id=None):
            return AgentResult(content="cwd", messages=[Message.from_text("assistant", text)])

    async def create_child(child_spec, task_id=""):
        created_specs.append(child_spec)
        return ChildSession()

    context = _context(repo, create_child, task_store=store)
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    async def run_background():
        started = await registry.execute(
            "Agent",
            {"description": "Inspect", "prompt": "inspect", "run_in_background": True, "cwd": "pkg"},
        )
        await context.background_tasks[started.raw["agentId"]]

    asyncio.run(run_background())

    assert Path(created_specs[0].workspace.path) == subdir.resolve()
