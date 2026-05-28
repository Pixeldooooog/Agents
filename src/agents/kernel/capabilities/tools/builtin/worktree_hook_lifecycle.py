from __future__ import annotations

import json
from dataclasses import dataclass
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
from agents.kernel.capabilities.tools.context import ToolRuntimeContext


@dataclass(frozen=True)
class HookWorktree:
    path: Path
    branch: str
    slug: str


async def has_hook_worktree_create_commands(context: ToolRuntimeContext) -> bool:
    await hydrate_worktree_hook_commands(context)
    return bool(worktree_hook_commands(context, "create"))


async def create_hook_worktree(
    context: ToolRuntimeContext,
    *,
    original_cwd: Path,
    slug: str,
    pr_number: int | None,
) -> HookWorktree:
    await hydrate_worktree_hook_commands(context)
    hook, worktree_path = await _run_create_hooks(context, worktree_hook_commands(context, "create"), original_cwd, slug, pr_number)
    await mark_worktree_hook_ran(context, hook)
    return HookWorktree(path=worktree_path, branch=worktree_branch_name(slug), slug=slug)


async def remove_hook_worktree(
    context: ToolRuntimeContext,
    *,
    original_cwd: Path,
    slug: str,
    worktree_path: Path,
) -> bool:
    await hydrate_worktree_hook_commands(context)
    ran = False
    for hook in worktree_hook_commands(context, "remove"):
        result = run_worktree_hook(hook.command, original_cwd, _remove_env(slug, original_cwd, worktree_path))
        if result.returncode != 0:
            detail = worktree_hook_failure(hook, worktree_hook_error(result))
            raise RuntimeError("WorktreeRemove hook failed: %s" % detail)
        await mark_worktree_hook_ran(context, hook)
        ran = True
    return ran


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


def _create_env(slug: str, pr_number: int | None, original_cwd: Path) -> dict[str, str]:
    return {
        "AGENTS_WORKTREE_NAME": slug,
        "AGENTS_WORKTREE_SLUG": slug,
        "AGENTS_WORKTREE_ORIGINAL_CWD": str(original_cwd),
        "AGENTS_WORKTREE_PR_NUMBER": "" if pr_number is None else str(pr_number),
    }


def _remove_env(slug: str, original_cwd: Path, worktree_path: Path) -> dict[str, str]:
    return {
        "AGENTS_WORKTREE_NAME": slug,
        "AGENTS_WORKTREE_PATH": str(worktree_path),
        "AGENTS_WORKTREE_ORIGINAL_CWD": str(original_cwd),
    }
