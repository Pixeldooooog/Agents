from __future__ import annotations

import shlex
from typing import Any

from agents.kernel.capabilities.tools.context import ToolRuntimeContext


GIT_STATUS_SCHEMA = {
    "type": "object",
    "properties": {
        "short": {"type": "boolean", "description": "Use short porcelain output."},
    },
}

GIT_DIFF_SCHEMA = {
    "type": "object",
    "properties": {
        "path": {"type": "string", "description": "Optional workspace-relative path to diff."},
        "staged": {"type": "boolean", "description": "Show staged changes."},
        "max_bytes": {"type": "integer", "minimum": 1, "maximum": 200000},
    },
}

GIT_ADD_SCHEMA = {
    "type": "object",
    "properties": {
        "paths": {"type": "array", "items": {"type": "string"}, "description": "Workspace-relative paths to stage."},
        "all": {"type": "boolean", "description": "Stage all workspace changes with git add -A."},
    },
}

GIT_COMMIT_SCHEMA = {
    "type": "object",
    "properties": {
        "message": {"type": "string", "description": "Commit message."},
        "all": {"type": "boolean", "description": "Also stage modified/deleted tracked files with git commit -a."},
        "paths": {"type": "array", "items": {"type": "string"}, "description": "Optional paths to commit."},
        "allow_empty": {"type": "boolean", "description": "Allow an empty commit."},
    },
    "required": ["message"],
}

GIT_LOG_SCHEMA = {
    "type": "object",
    "properties": {
        "max_count": {"type": "integer", "minimum": 1, "maximum": 100},
        "path": {"type": "string", "description": "Optional workspace-relative path."},
        "oneline": {"type": "boolean", "description": "Use compact one-line output."},
        "max_bytes": {"type": "integer", "minimum": 1, "maximum": 200000},
    },
}

GIT_SHOW_SCHEMA = {
    "type": "object",
    "properties": {
        "revision": {"type": "string", "description": "Commit, tag, or revision to show."},
        "path": {"type": "string", "description": "Optional workspace-relative path."},
        "stat": {"type": "boolean", "description": "Include diffstat."},
        "patch": {"type": "boolean", "description": "Include patch."},
        "max_bytes": {"type": "integer", "minimum": 1, "maximum": 200000},
    },
}


async def git_status(context: ToolRuntimeContext, short: bool = True) -> dict[str, Any]:
    command = "git status --short" if short else "git status"
    return (await context.sandbox_client.run_command(command, timeout_seconds=20.0)).to_dict()


async def git_diff(
    context: ToolRuntimeContext,
    path: str = "",
    staged: bool = False,
    max_bytes: int = 20000,
) -> dict[str, Any]:
    command = "git diff"
    if staged:
        command += " --staged"
    if path:
        decision = context.sandbox.authorize_file_read(path)
        if not decision.allowed:
            raise PermissionError(decision.reason)
        command += " -- %s" % shlex.quote(path)
    result = await context.sandbox_client.run_command(command, timeout_seconds=20.0)
    payload = result.to_dict()
    limit = max(1, min(int(max_bytes or 20000), 200000))
    stdout = str(payload["stdout"])
    payload["stdout"] = stdout[:limit]
    payload["truncated"] = len(stdout) > limit
    return payload


async def git_add(context: ToolRuntimeContext, paths: list[str] | None = None, all: bool = False) -> dict[str, Any]:
    raw_paths = _path_list(paths)
    if not all and not raw_paths:
        raise ValueError("git.add requires paths or all=true")
    if all:
        command = "git add -A"
    else:
        _authorize_paths(context, raw_paths, write=True)
        command = "git add -- %s" % " ".join(shlex.quote(path) for path in raw_paths)
    return (await context.sandbox_client.run_command(command, timeout_seconds=30.0)).to_dict()


async def git_commit(
    context: ToolRuntimeContext,
    message: str,
    all: bool = False,
    paths: list[str] | None = None,
    allow_empty: bool = False,
) -> dict[str, Any]:
    clean_message = str(message or "").strip()
    if not clean_message:
        raise ValueError("git.commit requires a non-empty message")
    raw_paths = _path_list(paths)
    if raw_paths:
        _authorize_paths(context, raw_paths, read=True)
    parts = ["git", "commit"]
    if all:
        parts.append("-a")
    if allow_empty:
        parts.append("--allow-empty")
    parts.extend(["-m", clean_message])
    command = " ".join(shlex.quote(part) for part in parts)
    if raw_paths:
        command += " -- %s" % " ".join(shlex.quote(path) for path in raw_paths)
    return (await context.sandbox_client.run_command(command, timeout_seconds=60.0)).to_dict()


async def git_log(
    context: ToolRuntimeContext,
    max_count: int = 10,
    path: str = "",
    oneline: bool = True,
    max_bytes: int = 20000,
) -> dict[str, Any]:
    count = max(1, min(int(max_count or 10), 100))
    command = "git log --no-ext-diff --max-count=%d" % count
    if oneline:
        command += " --oneline"
    else:
        command += " --stat"
    if path:
        decision = context.sandbox.authorize_file_read(path)
        if not decision.allowed:
            raise PermissionError(decision.reason)
        command += " -- %s" % shlex.quote(path)
    result = await context.sandbox_client.run_command(command, timeout_seconds=20.0)
    return _limited_payload(result.to_dict(), max_bytes)


async def git_show(
    context: ToolRuntimeContext,
    revision: str = "HEAD",
    path: str = "",
    stat: bool = True,
    patch: bool = True,
    max_bytes: int = 20000,
) -> dict[str, Any]:
    rev = _safe_revision(revision or "HEAD")
    parts = ["git", "show", "--no-ext-diff"]
    if stat:
        parts.append("--stat")
    if not patch:
        parts.append("--no-patch")
    parts.append(rev)
    command = " ".join(shlex.quote(part) for part in parts)
    if path:
        decision = context.sandbox.authorize_file_read(path)
        if not decision.allowed:
            raise PermissionError(decision.reason)
        command += " -- %s" % shlex.quote(path)
    result = await context.sandbox_client.run_command(command, timeout_seconds=20.0)
    return _limited_payload(result.to_dict(), max_bytes)


def _authorize_paths(context: ToolRuntimeContext, paths: list[str], *, read: bool = False, write: bool = False) -> None:
    for path in paths:
        if read:
            read_decision = context.sandbox.authorize_file_read(path)
            if not read_decision.allowed:
                raise PermissionError(read_decision.reason)
        if write:
            write_decision = context.sandbox.authorize_file_write(path)
            if not write_decision.allowed:
                raise PermissionError(write_decision.reason)


def _path_list(paths: list[str] | None) -> list[str]:
    return [str(path).strip() for path in (paths or []) if str(path).strip()]


def _safe_revision(value: str) -> str:
    revision = str(value or "HEAD").strip()
    if not revision or revision.startswith("-") or any(char.isspace() for char in revision):
        raise ValueError("unsafe git revision: %s" % value)
    return revision


def _limited_payload(payload: dict[str, Any], max_bytes: int) -> dict[str, Any]:
    limit = max(1, min(int(max_bytes or 20000), 200000))
    stdout = str(payload.get("stdout") or "")
    payload["stdout"] = stdout[:limit]
    payload["truncated"] = len(stdout) > limit
    return payload
