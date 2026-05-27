from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agents.kernel.capabilities.tools.context import ToolRuntimeContext


@dataclass(frozen=True)
class TmuxCommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


def create_worktree_tmux_session(
    context: ToolRuntimeContext,
    repo_root: Path,
    worktree_path: Path,
    branch: str,
) -> dict[str, Any]:
    if not _tmux_requested(context):
        return {}
    session_name = tmux_session_name(repo_root, branch)
    result = _run_tmux(["new-session", "-d", "-s", session_name, "-c", str(worktree_path)])
    created = result.returncode == 0
    return {
        "tmuxSessionName": session_name,
        "tmuxCreated": created,
        "tmuxError": "" if created else _tmux_error(result),
    }


def kill_worktree_tmux_session(session_name: str) -> dict[str, Any]:
    name = str(session_name or "").strip()
    if not name:
        return {}
    result = _run_tmux(["kill-session", "-t", name])
    terminated = result.returncode == 0
    return {
        "tmuxSessionName": name,
        "tmuxTerminated": terminated,
        "tmuxError": "" if terminated else _tmux_error(result),
    }


def tmux_keep_note(session_name: str) -> str:
    name = str(session_name or "").strip()
    if not name:
        return ""
    return " Tmux session %s is still running; reattach with: tmux attach -t %s" % (name, name)


def tmux_session_name(repo_root: Path, branch: str) -> str:
    repo_name = Path(repo_root).expanduser().resolve().name or "worktree"
    raw = "%s_%s" % (repo_name, branch or "worktree")
    return re.sub(r"[/.]", "_", raw)


def _tmux_requested(context: ToolRuntimeContext) -> bool:
    metadata = getattr(getattr(context, "agent_spec", None), "metadata", None)
    worktree = metadata.get("worktree") if isinstance(metadata, dict) else {}
    worktree = worktree if isinstance(worktree, dict) else {}
    value = worktree.get("tmux", worktree.get("tmux_enabled", worktree.get("tmuxEnabled")))
    if value is None:
        value = _settings_value(context, "WORKTREE_TMUX")
    return _truthy(value)


def _settings_value(context: ToolRuntimeContext, name: str) -> Any:
    agent = getattr(getattr(context, "settings", None), "agent", None)
    return getattr(agent, name, None) if agent is not None else None


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _run_tmux(args: list[str]) -> TmuxCommandResult:
    try:
        result = subprocess.run(
            ["tmux", *args],
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return TmuxCommandResult(returncode=1, stderr=str(exc))
    return TmuxCommandResult(returncode=result.returncode, stdout=result.stdout, stderr=result.stderr)


def _tmux_error(result: TmuxCommandResult) -> str:
    return (result.stderr or result.stdout or "tmux command failed").strip()
