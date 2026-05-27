from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from agents.kernel.capabilities.tools.builtin.worktree_git import (
    count_worktree_changes,
    create_git_worktree,
    git,
    git_error,
    git_root,
    is_git_worktree,
    prepare_worktree_base_ref,
)
from agents.kernel.capabilities.tools.builtin.worktree_naming import (
    validate_worktree_slug,
    worktree_branch_name,
    worktree_path_for,
    worktree_request,
)
from agents.kernel.capabilities.tools.builtin.worktree_hooks import (
    enter_hook_worktree,
    exit_hook_worktree,
    has_worktree_create_hook,
)
from agents.kernel.capabilities.tools.builtin.worktree_setup import (
    ensure_worktrees_excluded,
    perform_post_creation_setup,
    worktree_settings,
)
from agents.kernel.capabilities.tools.builtin.worktree_state import (
    restore_active_worktree_session,
    switch_workspace,
)
from agents.kernel.capabilities.tools.builtin.worktree_tmux import (
    create_worktree_tmux_session,
    kill_worktree_tmux_session,
    tmux_keep_note,
)
from agents.kernel.capabilities.tools.context import ToolRuntimeContext
from agents.kernel.session_state import save_session_state


NO_ACTIVE_WORKTREE_SESSION_MESSAGE = (
    "No-op: there is no active EnterWorktree session to exit. "
    "This tool only operates on worktrees created by EnterWorktree in the current session. "
    "No filesystem changes were made."
)

WORKTREE_ENTER_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {
            "type": "string",
            "description": "Optional worktree name or PR reference (#123 or a GitHub /pull/123 URL). Slash-separated name segments are flattened for the actual branch/path.",
        },
        "pr_number": {
            "type": "integer",
            "minimum": 1,
            "description": "Optional pull request number. When provided, the worktree is created from origin pull/<number>/head.",
        },
        "prNumber": {
            "type": "integer",
            "minimum": 1,
            "description": "CamelCase alias for pr_number.",
        },
    },
    "additionalProperties": False,
}

WORKTREE_EXIT_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": ["keep", "remove"],
            "description": "keep preserves the worktree; remove deletes the worktree and its branch.",
        },
        "discard_changes": {
            "type": "boolean",
            "description": "Required to remove a worktree that has uncommitted files or commits after its base.",
        },
    },
    "required": ["action"],
    "additionalProperties": False,
}


async def enter_worktree(
    context: ToolRuntimeContext,
    name: str = "",
    pr_number: int | None = None,
    pr_number_alias: int | None = None,
) -> dict[str, Any]:
    if context.active_worktree_session:
        session = context.active_worktree_session
        raise RuntimeError("Already in a worktree session at %s" % session.get("worktreePath", "unknown"))

    slug, resolved_pr_number = worktree_request(name, pr_number=pr_number, pr_number_alias=pr_number_alias)
    if has_worktree_create_hook(context):
        return await enter_hook_worktree(context, slug=slug, pr_number=resolved_pr_number)

    repo_root = git_root(context.workspace.path)
    worktree_path = worktree_path_for(repo_root, slug)
    branch = worktree_branch_name(slug)
    settings = worktree_settings(context)
    ensure_worktrees_excluded(repo_root)

    post_create: dict[str, Any] = {}
    existed = is_git_worktree(worktree_path)
    base_ref = "HEAD"
    if not existed:
        base_ref = prepare_worktree_base_ref(repo_root, resolved_pr_number)
        create_git_worktree(repo_root, worktree_path, branch, base_ref=base_ref, sparse_paths=settings["sparse_paths"])
        post_create = perform_post_creation_setup(
            repo_root,
            worktree_path,
            symlink_directories=settings["symlink_directories"],
        )
    worktree_head = git(worktree_path, ["rev-parse", "HEAD"]).stdout.strip()
    tmux = create_worktree_tmux_session(context, repo_root, worktree_path, branch)

    session = {
        "originalCwd": str(repo_root),
        "worktreePath": str(worktree_path),
        "worktreeName": slug,
        "worktreeBranch": branch,
        "originalHeadCommit": worktree_head,
        "sessionId": str(context.current_run_id or context.task_id or uuid.uuid4().hex),
        "usedSparsePaths": bool(settings["sparse_paths"] and not existed),
        "prNumber": resolved_pr_number,
        **post_create,
        **tmux,
    }
    context.active_worktree_session = session
    switch_workspace(context, worktree_path)
    await save_session_state(context)

    action = "Resumed" if existed else "Created"
    return {
        "worktreePath": str(worktree_path),
        "worktreeBranch": branch,
        "resumed": existed,
        "copiedFiles": list(post_create.get("copiedFiles") or []),
        "copiedLocalFiles": list(post_create.get("copiedLocalFiles") or []),
        "symlinkedDirectories": list(post_create.get("symlinkedDirectories") or []),
        "hooksPath": str(post_create.get("hooksPath") or ""),
        "usedSparsePaths": bool(settings["sparse_paths"] and not existed),
        "prNumber": resolved_pr_number,
        "baseRef": base_ref,
        "headCommit": worktree_head,
        "tmuxSessionName": str(tmux.get("tmuxSessionName") or ""),
        "tmuxCreated": bool(tmux.get("tmuxCreated", False)),
        "tmuxError": str(tmux.get("tmuxError") or ""),
        "message": "%s worktree at %s on branch %s. Session is now using that worktree." % (action, worktree_path, branch),
    }


async def exit_worktree(context: ToolRuntimeContext, action: str, discard_changes: bool = False) -> dict[str, Any]:
    normalized_action = str(action or "").strip()
    if normalized_action not in {"keep", "remove"}:
        raise ValueError("action must be keep or remove")
    session = dict(context.active_worktree_session or {})
    if not session:
        original_cwd = Path(context.workspace.path).expanduser().resolve()
        return {
            "action": normalized_action,
            "noop": True,
            "reason": "no_active_worktree_session",
            "originalCwd": str(original_cwd),
            "worktreePath": "",
            "worktreeBranch": "",
            "message": NO_ACTIVE_WORKTREE_SESSION_MESSAGE,
        }
    hook_result = await exit_hook_worktree(context, session, normalized_action, discard_changes)
    if hook_result is not None:
        return hook_result

    original_cwd = Path(str(session.get("originalCwd") or "")).expanduser().resolve()
    worktree_path = Path(str(session.get("worktreePath") or "")).expanduser().resolve()
    branch = str(session.get("worktreeBranch") or "")
    original_head = str(session.get("originalHeadCommit") or "")
    changes = count_worktree_changes(worktree_path, original_head)

    if normalized_action == "remove" and not discard_changes and (changes is None or changes["changedFiles"] or changes["commits"]):
        if changes is None:
            detail = "Could not verify worktree changes."
        else:
            parts = []
            if changes["changedFiles"]:
                parts.append("%d changed file(s)" % changes["changedFiles"])
            if changes["commits"]:
                parts.append("%d commit(s)" % changes["commits"])
            detail = "Worktree contains %s." % " and ".join(parts)
        raise RuntimeError("%s Re-run with discard_changes=true to remove it." % detail)

    changed_files = int((changes or {}).get("changedFiles") or 0)
    commits = int((changes or {}).get("commits") or 0)
    switch_workspace(context, original_cwd)
    context.active_worktree_session = {}

    if normalized_action == "keep":
        await save_session_state(context)
        tmux_name = str(session.get("tmuxSessionName") or "")
        return {
            "action": "keep",
            "originalCwd": str(original_cwd),
            "worktreePath": str(worktree_path),
            "worktreeBranch": branch,
            "tmuxSessionName": tmux_name,
            "message": "Exited worktree. Your work is preserved at %s%s. Session is now back in %s.%s"
            % (worktree_path, " on branch %s" % branch if branch else "", original_cwd, tmux_keep_note(tmux_name)),
        }

    tmux = kill_worktree_tmux_session(str(session.get("tmuxSessionName") or ""))
    remove = git(original_cwd, ["worktree", "remove", "--force", str(worktree_path)], check=False, timeout=60)
    if remove.returncode != 0:
        context.active_worktree_session = session
        switch_workspace(context, worktree_path)
        raise RuntimeError(git_error("Failed to remove worktree", remove))
    branch_delete_error = ""
    if branch:
        deleted = git(original_cwd, ["branch", "-D", branch], check=False)
        if deleted.returncode != 0:
            branch_delete_error = git_error("Could not delete worktree branch", deleted)
    await save_session_state(context)

    discard_parts = []
    if commits:
        discard_parts.append("%d commit%s" % (commits, "" if commits == 1 else "s"))
    if changed_files:
        discard_parts.append("%d uncommitted file%s" % (changed_files, "" if changed_files == 1 else "s"))
    discard_note = " Discarded %s." % " and ".join(discard_parts) if discard_parts else ""
    warning = " %s" % branch_delete_error if branch_delete_error else ""
    return {
        "action": "remove",
        "originalCwd": str(original_cwd),
        "worktreePath": str(worktree_path),
        "worktreeBranch": branch,
        "discardedFiles": changed_files,
        "discardedCommits": commits,
        "tmuxSessionName": str(tmux.get("tmuxSessionName") or ""),
        "tmuxTerminated": bool(tmux.get("tmuxTerminated", False)),
        "tmuxError": str(tmux.get("tmuxError") or ""),
        "message": "Exited and removed worktree at %s.%s Session is now back in %s.%s"
        % (worktree_path, discard_note, original_cwd, warning),
    }


def format_worktree_result(result: Any) -> str:
    payload = result if isinstance(result, dict) else {}
    return str(payload.get("message") or payload)
