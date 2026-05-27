import asyncio
import shlex
import sys
from pathlib import Path

from agents.kernel.capabilities.sandbox.local import LocalSandboxProvider
from agents.kernel.capabilities.tools import ToolRuntimeContext, register_builtin_tools
from agents.kernel.capabilities.tools.builtin.worktree import restore_active_worktree_session
from agents.kernel.capabilities.tools.registry import ToolRegistry
from agents.kernel.context.workspace import WorkspaceContext
from agents.kernel.governance import SandboxPolicy
from agents.kernel.session_state import InMemorySessionStateStore
from agents.kernel.specs import AgentSpec


def test_worktree_create_and_remove_hooks_support_non_git_workspaces(tmp_path: Path):
    context = _tool_context(
        tmp_path,
        AgentSpec(
            metadata={
                "worktree": {
                    "hooks": {
                        "create": _python_hook(
                            "import os, pathlib\n"
                            "path = pathlib.Path(os.environ['AGENTS_WORKTREE_ORIGINAL_CWD']) / 'hook-worktree'\n"
                            "path.mkdir(parents=True, exist_ok=True)\n"
                            "print(path)\n"
                        ),
                        "remove": _python_hook(
                            "import os, pathlib, shutil\n"
                            "path = pathlib.Path(os.environ['AGENTS_WORKTREE_PATH'])\n"
                            "shutil.rmtree(path)\n"
                            "print('removed')\n"
                        ),
                    }
                }
            }
        ),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    entered = asyncio.run(registry.execute("worktree.enter", {"name": "hooked"}))
    worktree_path = Path(entered.raw["worktreePath"])
    workspace_after_enter = context.workspace.path
    blocked = asyncio.run(registry.execute("worktree.exit", {"action": "remove"}))
    removed = asyncio.run(registry.execute("worktree.exit", {"action": "remove", "discard_changes": True}))

    assert entered.is_error is False
    assert entered.raw["hookBased"] is True
    assert worktree_path == (tmp_path / "hook-worktree").resolve()
    assert workspace_after_enter == worktree_path
    assert blocked.is_error is True
    assert "discard_changes=true" in blocked.content
    assert removed.is_error is False
    assert removed.raw["hookBased"] is True
    assert removed.raw["worktreeRemoveHookRan"] is True
    assert not worktree_path.exists()
    assert context.workspace.path == tmp_path.resolve()


def test_hook_based_worktree_session_restore_uses_saved_path(tmp_path: Path):
    store = InMemorySessionStateStore()
    worktree_path = tmp_path / "hook-worktree"
    context = _tool_context(
        tmp_path,
        AgentSpec(
            metadata={
                "worktree": {
                    "create_hook": _python_hook(
                        "import json, os, pathlib\n"
                        "path = pathlib.Path(os.environ['AGENTS_WORKTREE_ORIGINAL_CWD']) / 'hook-worktree'\n"
                        "path.mkdir(parents=True, exist_ok=True)\n"
                        "print(json.dumps({'hookSpecificOutput': {'hookEventName': 'WorktreeCreate', 'worktreePath': str(path)}}))\n"
                    )
                }
            }
        ),
        store=store,
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    entered = asyncio.run(registry.execute("EnterWorktree", {"name": "json-hook"}))
    record = asyncio.run(store.load_for_scope("tenant", user_id="user", agent_id="agent", workspace_id="workspace"))
    restored_context = _tool_context(tmp_path, AgentSpec(), store=store)
    restored = restore_active_worktree_session(restored_context, record.active_worktree_session)

    assert entered.is_error is False
    assert entered.raw["worktreePath"] == str(worktree_path.resolve())
    assert record.active_worktree_session["hookBased"] is True
    assert restored is True
    assert restored_context.workspace.path == worktree_path.resolve()


def _tool_context(tmp_path: Path, agent_spec: AgentSpec, store: InMemorySessionStateStore | None = None) -> ToolRuntimeContext:
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path, allow_file_write=True, allow_process=True)
    return ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
        session_state_store=store,
        agent_spec=agent_spec,
    )


def _python_hook(source: str) -> str:
    return "%s -c %s" % (shlex.quote(sys.executable), shlex.quote(source))
