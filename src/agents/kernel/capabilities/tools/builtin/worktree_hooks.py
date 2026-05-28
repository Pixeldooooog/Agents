from __future__ import annotations

from pathlib import Path
from typing import Any

from agents.kernel.capabilities.tools.builtin.worktree_hook_lifecycle import (
    create_hook_worktree,
    has_hook_worktree_create_commands,
    remove_hook_worktree,
)
from agents.kernel.capabilities.tools.builtin.worktree_state import switch_workspace
from agents.kernel.capabilities.tools.builtin.worktree_tmux import (
    create_worktree_tmux_session,
    kill_worktree_tmux_session,
    tmux_keep_note,
)
from agents.kernel.capabilities.tools.context import ToolRuntimeContext
from agents.kernel.session_state import save_session_state


async def has_worktree_create_hook(context: ToolRuntimeContext) -> bool:
    return await has_hook_worktree_create_commands(context)


async def enter_hook_worktree(
    context: ToolRuntimeContext,
    *,
    slug: str,
    pr_number: int | None,
) -> dict[str, Any]:
    original_cwd = Path(context.workspace.path).expanduser().resolve()
    hook_worktree = await create_hook_worktree(
        context,
        original_cwd=original_cwd,
        slug=slug,
        pr_number=pr_number,
    )
    worktree_path = hook_worktree.path
    branch = hook_worktree.branch
    tmux = create_worktree_tmux_session(context, original_cwd, worktree_path, branch)
    session = {
        "originalCwd": str(original_cwd),
        "worktreePath": str(worktree_path),
        "worktreeName": slug,
        "worktreeBranch": branch,
        "originalHeadCommit": "",
        "sessionId": str(context.current_run_id or context.task_id or ""),
        "hookBased": True,
        "prNumber": pr_number,
        **tmux,
    }
    context.active_worktree_session = session
    switch_workspace(context, worktree_path)
    await save_session_state(context)
    return {
        "worktreePath": str(worktree_path),
        "worktreeBranch": branch,
        "resumed": False,
        "hookBased": True,
        "prNumber": pr_number,
        "tmuxSessionName": str(tmux.get("tmuxSessionName") or ""),
        "tmuxCreated": bool(tmux.get("tmuxCreated", False)),
        "tmuxError": str(tmux.get("tmuxError") or ""),
        "message": "Created hook-based worktree at %s. Session is now using that worktree." % worktree_path,
    }


async def exit_hook_worktree(
    context: ToolRuntimeContext,
    session: dict[str, Any],
    action: str,
    discard_changes: bool,
) -> dict[str, Any] | None:
    if not bool(session.get("hookBased")):
        return None
    original_cwd = Path(str(session.get("originalCwd") or "")).expanduser().resolve()
    worktree_path = Path(str(session.get("worktreePath") or "")).expanduser().resolve()
    tmux_name = str(session.get("tmuxSessionName") or "")
    if action == "remove" and not discard_changes:
        raise RuntimeError("Could not verify hook-based worktree changes. Re-run with discard_changes=true to remove it.")
    if action == "remove":
        ran = await remove_hook_worktree(
            context,
            original_cwd=original_cwd,
            slug=str(session.get("worktreeName") or ""),
            worktree_path=worktree_path,
        )
        tmux = kill_worktree_tmux_session(tmux_name)
    else:
        ran = False
        tmux = {}

    switch_workspace(context, original_cwd)
    context.active_worktree_session = {}
    await save_session_state(context)
    if action == "keep":
        return {
            "action": "keep",
            "hookBased": True,
            "originalCwd": str(original_cwd),
            "worktreePath": str(worktree_path),
            "worktreeBranch": str(session.get("worktreeBranch") or ""),
            "tmuxSessionName": tmux_name,
            "message": "Exited hook-based worktree. Your work is preserved at %s. Session is now back in %s.%s"
            % (worktree_path, original_cwd, tmux_keep_note(tmux_name)),
        }
    return {
        "action": "remove",
        "hookBased": True,
        "originalCwd": str(original_cwd),
        "worktreePath": str(worktree_path),
        "worktreeBranch": str(session.get("worktreeBranch") or ""),
        "worktreeRemoveHookRan": ran,
        "tmuxSessionName": str(tmux.get("tmuxSessionName") or ""),
        "tmuxTerminated": bool(tmux.get("tmuxTerminated", False)),
        "tmuxError": str(tmux.get("tmuxError") or ""),
        "message": "Exited hook-based worktree at %s. Session is now back in %s.%s"
        % (
            worktree_path,
            original_cwd,
            "" if ran else " No WorktreeRemove hook was configured; the directory was left in place.",
        ),
    }
