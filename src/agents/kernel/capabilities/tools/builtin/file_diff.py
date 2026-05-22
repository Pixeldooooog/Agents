from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from agents.kernel.capabilities.tools.context import ToolRuntimeContext


GIT_DIFF_TIMEOUT_SECONDS = 5.0


def single_file_git_diff(context: ToolRuntimeContext, path: str) -> dict[str, Any] | None:
    try:
        absolute_path = context.sandbox.resolve_workspace_path(path)
    except (OSError, PermissionError):
        return None
    git_root = _git_root(absolute_path.parent)
    if git_root is None:
        return None
    try:
        git_path = absolute_path.relative_to(git_root).as_posix()
    except ValueError:
        return None
    if _is_git_tracked(git_root, git_path):
        raw = _git_stdout(git_root, ["diff", _diff_ref(git_root), "--", git_path])
        if not raw:
            return None
        return _parse_raw_git_diff(git_path, raw, status="modified")
    return _synthetic_added_diff(git_path, absolute_path)


def _git_root(cwd: Path) -> Path | None:
    stdout = _git_stdout(cwd, ["rev-parse", "--show-toplevel"])
    if not stdout:
        return None
    return Path(stdout.strip())


def _is_git_tracked(git_root: Path, git_path: str) -> bool:
    result = _run_git(git_root, ["ls-files", "--error-unmatch", git_path])
    return result is not None and result.returncode == 0


def _diff_ref(git_root: Path) -> str:
    base_ref = os.environ.get("CLAUDE_CODE_BASE_REF") or _default_branch_ref(git_root)
    if base_ref:
        merge_base = _git_stdout(git_root, ["merge-base", "HEAD", base_ref]).strip()
        if merge_base:
            return merge_base
    return "HEAD"


def _default_branch_ref(git_root: Path) -> str:
    remote_head = _git_stdout(git_root, ["symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"]).strip()
    if remote_head:
        return remote_head
    for candidate in ("main", "master", "origin/main", "origin/master"):
        if _git_stdout(git_root, ["rev-parse", "--verify", "--quiet", candidate]).strip():
            return candidate
    return ""


def _git_stdout(cwd: Path, args: list[str]) -> str:
    result = _run_git(cwd, args)
    if result is None or result.returncode != 0:
        return ""
    return result.stdout


def _run_git(cwd: Path, args: list[str]) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            ["git", "--no-optional-locks", *args],
            cwd=str(cwd),
            text=True,
            capture_output=True,
            timeout=GIT_DIFF_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def _parse_raw_git_diff(git_path: str, raw_diff: str, *, status: str) -> dict[str, Any] | None:
    patch_lines: list[str] = []
    additions = 0
    deletions = 0
    in_hunks = False
    for line in raw_diff.splitlines():
        if line.startswith("@@"):
            in_hunks = True
        if not in_hunks:
            continue
        patch_lines.append(line)
        if line.startswith("+") and not line.startswith("+++"):
            additions += 1
        elif line.startswith("-") and not line.startswith("---"):
            deletions += 1
    if not patch_lines:
        return None
    return {
        "filename": git_path,
        "status": status,
        "additions": additions,
        "deletions": deletions,
        "changes": additions + deletions,
        "patch": "\n".join(patch_lines),
        "repository": None,
    }


def _synthetic_added_diff(git_path: str, absolute_path: Path) -> dict[str, Any] | None:
    try:
        content = absolute_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    lines = content.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    line_count = len(lines)
    patch = "@@ -0,0 +1,%d @@" % line_count
    if lines:
        patch += "\n" + "\n".join("+%s" % line for line in lines)
    return {
        "filename": git_path,
        "status": "added",
        "additions": line_count,
        "deletions": 0,
        "changes": line_count,
        "patch": patch,
        "repository": None,
    }
