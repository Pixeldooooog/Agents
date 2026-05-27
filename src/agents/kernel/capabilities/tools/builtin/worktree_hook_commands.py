from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agents.kernel.capabilities.tools.context import ToolRuntimeContext
from agents.kernel.hooks.store import hydrate_hook_registry, save_hook_record


@dataclass(frozen=True)
class WorktreeHookCommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


@dataclass(frozen=True)
class WorktreeHookCommand:
    command: str | list[str]
    record: Any | None = None


async def hydrate_worktree_hook_commands(context: ToolRuntimeContext) -> None:
    await hydrate_hook_registry(context.hook_registry, getattr(context, "hook_store", None), context.workspace)


async def mark_worktree_hook_ran(context: ToolRuntimeContext, hook: WorktreeHookCommand) -> None:
    if hook.record is None:
        return
    context.hook_registry.mark_ran(hook.record)
    await save_hook_record(hook.record, getattr(context, "hook_store", None), context.workspace)


def worktree_hook_commands(context: ToolRuntimeContext, kind: str) -> list[WorktreeHookCommand]:
    return _registry_hook_commands(context, kind) + _configured_hook_commands(context, kind)


def run_worktree_hook(command: str | list[str], cwd: Path, env: dict[str, str]) -> WorktreeHookCommandResult:
    run_env = dict(os.environ)
    run_env.update(env)
    try:
        if isinstance(command, (list, tuple)):
            result = subprocess.run(
                [str(item) for item in command],
                cwd=str(cwd),
                env=run_env,
                text=True,
                capture_output=True,
                timeout=60,
            )
        else:
            result = subprocess.run(
                str(command),
                cwd=str(cwd),
                env=run_env,
                text=True,
                capture_output=True,
                shell=True,
                timeout=60,
            )
    except (OSError, subprocess.SubprocessError) as exc:
        return WorktreeHookCommandResult(returncode=1, stderr=str(exc))
    return WorktreeHookCommandResult(returncode=result.returncode, stdout=result.stdout, stderr=result.stderr)


def worktree_hook_error(result: WorktreeHookCommandResult) -> str:
    return (result.stderr or result.stdout or "hook command failed").strip()


def worktree_hook_failure(hook: WorktreeHookCommand, detail: str) -> str:
    name = str(getattr(hook.record, "name", "") or "").strip()
    return "%s: %s" % (name, detail) if name else detail


def _registry_hook_commands(context: ToolRuntimeContext, kind: str) -> list[WorktreeHookCommand]:
    event = "worktree_create" if kind == "create" else "worktree_remove"
    return [
        WorktreeHookCommand(record.content, record)
        for record in context.hook_registry.list(event=event, enabled=True, limit=100)
        if record.action == "run_command" and record.content.strip()
    ]


def _configured_hook_commands(context: ToolRuntimeContext, kind: str) -> list[WorktreeHookCommand]:
    worktree = _worktree_metadata(context)
    hooks = worktree.get("hooks") if isinstance(worktree.get("hooks"), dict) else {}
    names = ("create", "WorktreeCreate", "create_hook", "createHook") if kind == "create" else (
        "remove",
        "WorktreeRemove",
        "remove_hook",
        "removeHook",
    )
    for name in names:
        value = hooks.get(name) or worktree.get(name)
        if value:
            return [WorktreeHookCommand(value)]
    value = _settings_value(context, "WORKTREE_CREATE_HOOK" if kind == "create" else "WORKTREE_REMOVE_HOOK")
    return [WorktreeHookCommand(value)] if value else []


def _worktree_metadata(context: ToolRuntimeContext) -> dict[str, Any]:
    metadata = getattr(getattr(context, "agent_spec", None), "metadata", None)
    worktree = metadata.get("worktree") if isinstance(metadata, dict) else {}
    return worktree if isinstance(worktree, dict) else {}


def _settings_value(context: ToolRuntimeContext, name: str) -> Any:
    agent = getattr(getattr(context, "settings", None), "agent", None)
    return getattr(agent, name, None) if agent is not None else None
