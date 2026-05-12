from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any


def diff_rows(state: Any) -> list[list[str]]:
    workspace = _workspace_path(state)
    if workspace is None:
        return [["workspace", "not bound"]]
    root = _git(["rev-parse", "--show-toplevel"], workspace)
    if root.returncode != 0:
        return [["git", root.stderr.strip() or "not a git workspace"]]

    rows: list[list[str]] = []
    for line in _git(["status", "--short", "--untracked-files=normal"], workspace).stdout.splitlines()[:30]:
        if not line:
            continue
        rows.append([line[:2].strip() or "changed", line[3:] if len(line) > 3 else line])
    if rows:
        return rows
    return [["diff", "clean"]]


def _workspace_path(state: Any) -> Path | None:
    workspace = getattr(state, "active_workspace", None)
    if workspace:
        return Path(workspace)
    session_workspace = getattr(getattr(state, "session", None), "workspace", None)
    path = getattr(session_workspace, "path", None)
    return Path(path) if path else None


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(["git", *args], cwd=str(cwd), text=True, capture_output=True, timeout=3, check=False)
    except Exception as exc:  # noqa: BLE001 - human-facing bridge command should return a row instead of crashing.
        return subprocess.CompletedProcess(args=["git", *args], returncode=1, stdout="", stderr=str(exc))
