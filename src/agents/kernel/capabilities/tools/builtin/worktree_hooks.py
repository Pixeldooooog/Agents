from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agents.kernel.capabilities.tools.builtin.worktree_hook_commands import (
    WorktreeHookCommand,
    hydrate_worktree_hook_commands,
    mark_worktree_hook_ran,
    run_worktree_hook,
    worktree_hook_commands,
    worktree_hook_error,
    worktree_hook_failure,
)
from agents.kernel.capabilities.tools.builtin.worktree_naming import worktree_branch_name
from agents.kernel.capabilities.tools.builtin.worktree_state import switch_workspace
from agents.kernel.capabilities.tools.builtin.worktree_tmux import (
    create_worktree_tmux_session,
    kill_worktree_tmux_session,
    tmux_keep_note,
)
from agents.kernel.capabilities.tools.context import ToolRuntimeContext
from agents.kernel.session_state import save_session_state


async def has_worktree_create_hook(context: ToolRuntimeContext) -> bool:
    await hydrate_worktree_hook_commands(context)
    return bool(worktree_hook_commands(context, "create"))


async def enter_hook_worktree(
    context: ToolRuntimeContext,
    *,
    slug: str,
    pr_number: int | None,
) -> dict[str, Any]:
    original_cwd = Path(context.workspace.path).expanduser().resolve()
    await hydrate_worktree_hook_commands(context)
    hook, worktree_path = await _run_create_hooks(
        context,
        worktree_hook_commands(context, "create"),
        original_cwd,
        slug,
        pr_number,
    )
    await mark_worktree_hook_ran(context, hook)

    branch = worktree_branch_name(slug)
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
        await hydrate_worktree_hook_commands(context)
        ran = await _run_remove_hooks(
            context,
            worktree_hook_commands(context, "remove"),
            original_cwd,
            session,
            worktree_path,
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


def _worktree_path_from_output(output: str, cwd: Path) -> Path:
    text = str(output or "").strip()
    if not text:
        raise RuntimeError("WorktreeCreate hook produced no worktree path")
    path_text = _json_worktree_path(text) or _last_output_line(text)
    path = Path(path_text).expanduser()
    return path.resolve() if path.is_absolute() else (cwd / path).resolve()


def _json_worktree_path(text: str) -> str:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return ""
    if not isinstance(payload, dict):
        return ""
    hook_specific = payload.get("hookSpecificOutput")
    if isinstance(hook_specific, dict):
        value = hook_specific.get("worktreePath") or hook_specific.get("worktree_path")
        if value:
            return str(value)
    value = payload.get("worktreePath") or payload.get("worktree_path") or payload.get("path")
    return str(value) if value else ""


def _last_output_line(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines[-1] if lines else text


async def _run_create_hooks(
    context: ToolRuntimeContext,
    hooks: list[WorktreeHookCommand],
    original_cwd: Path,
    slug: str,
    pr_number: int | None,
) -> tuple[WorktreeHookCommand, Path]:
    errors: list[str] = []
    for hook in hooks:
        result = run_worktree_hook(hook.command, original_cwd, _create_env(slug, pr_number, original_cwd))
        if result.returncode != 0:
            errors.append(worktree_hook_failure(hook, worktree_hook_error(result)))
            continue
        try:
            worktree_path = _worktree_path_from_output(result.stdout, original_cwd)
        except RuntimeError as exc:
            errors.append(worktree_hook_failure(hook, str(exc)))
            continue
        if not worktree_path.is_dir():
            errors.append(worktree_hook_failure(hook, "returned a path that is not a directory: %s" % worktree_path))
            continue
        return hook, worktree_path
    detail = "; ".join(errors) if errors else "no hook command configured"
    raise RuntimeError("WorktreeCreate hook failed: %s" % detail)


async def _run_remove_hooks(
    context: ToolRuntimeContext,
    hooks: list[WorktreeHookCommand],
    original_cwd: Path,
    session: dict[str, Any],
    worktree_path: Path,
) -> bool:
    ran = False
    for hook in hooks:
        result = run_worktree_hook(hook.command, original_cwd, _remove_env(session, original_cwd, worktree_path))
        if result.returncode != 0:
            detail = worktree_hook_failure(hook, worktree_hook_error(result))
            raise RuntimeError("WorktreeRemove hook failed: %s" % detail)
        await mark_worktree_hook_ran(context, hook)
        ran = True
    return ran


def _create_env(slug: str, pr_number: int | None, original_cwd: Path) -> dict[str, str]:
    return {
        "AGENTS_WORKTREE_NAME": slug,
        "AGENTS_WORKTREE_SLUG": slug,
        "AGENTS_WORKTREE_ORIGINAL_CWD": str(original_cwd),
        "AGENTS_WORKTREE_PR_NUMBER": "" if pr_number is None else str(pr_number),
    }


def _remove_env(session: dict[str, Any], original_cwd: Path, worktree_path: Path) -> dict[str, str]:
    return {
        "AGENTS_WORKTREE_NAME": str(session.get("worktreeName") or ""),
        "AGENTS_WORKTREE_PATH": str(worktree_path),
        "AGENTS_WORKTREE_ORIGINAL_CWD": str(original_cwd),
    }
