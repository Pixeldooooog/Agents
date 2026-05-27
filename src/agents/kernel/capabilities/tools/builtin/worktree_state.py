from __future__ import annotations

import subprocess
from dataclasses import replace
from pathlib import Path
from typing import Any

from agents.kernel.capabilities.sandbox.factory import create_sandbox_client_from_profile
from agents.kernel.capabilities.sandbox.types import SandboxProfile
from agents.kernel.capabilities.tools.context import ToolRuntimeContext, _scoped_lease_id
from agents.kernel.capabilities.tools.builtin.worktree_git import git_root, is_git_worktree
from agents.kernel.capabilities.tools.builtin.worktree_naming import validate_worktree_slug, worktree_path_for


def restore_active_worktree_session(context: ToolRuntimeContext, session: dict[str, Any]) -> bool:
    restored = _normalized_worktree_session(session)
    if not restored:
        context.active_worktree_session = {}
        return False

    try:
        repo_root = git_root(context.workspace.path)
    except (OSError, subprocess.SubprocessError, RuntimeError):
        context.active_worktree_session = {}
        return False

    original_cwd = Path(str(restored.get("originalCwd") or "")).expanduser().resolve()
    worktree_path = Path(str(restored.get("worktreePath") or "")).expanduser().resolve()
    if original_cwd != repo_root or not _is_known_worktree_path(repo_root, worktree_path, restored):
        context.active_worktree_session = {}
        return False
    try:
        is_worktree = is_git_worktree(worktree_path)
    except (OSError, subprocess.SubprocessError):
        is_worktree = False
    if not is_worktree:
        context.active_worktree_session = {}
        return False

    restored["originalCwd"] = str(original_cwd)
    restored["worktreePath"] = str(worktree_path)
    context.active_worktree_session = restored
    switch_workspace(context, worktree_path)
    return True


def switch_workspace(context: ToolRuntimeContext, path: Path) -> None:
    workspace_path = Path(path).expanduser().resolve()
    context.workspace = replace(context.workspace, path=workspace_path)
    context.sandbox = replace(context.sandbox, workspace_root=workspace_path)
    profile = context.sandbox_profile or SandboxProfile(provider="local")
    metadata = _sandbox_metadata(context)
    lease_id = _scoped_lease_id(context.current_run_id, context.current_task_id) if context.current_run_id else ""
    context.sandbox_client = create_sandbox_client_from_profile(
        context.workspace,
        context.sandbox,
        profile,
        lease_id=lease_id,
        metadata=metadata,
    )


def _normalized_worktree_session(session: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(session, dict):
        return {}
    restored = {str(key): _json_safe_value(value) for key, value in session.items()}
    if not restored.get("originalCwd") or not restored.get("worktreePath"):
        return {}
    return restored


def _json_safe_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple, set)):
        return [_json_safe_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe_value(item) for key, item in value.items()}
    return str(value)


def _is_known_worktree_path(repo_root: Path, worktree_path: Path, session: dict[str, Any]) -> bool:
    slug = str(session.get("worktreeName") or "").strip()
    if slug:
        try:
            validate_worktree_slug(slug)
        except ValueError:
            return False
        return worktree_path == worktree_path_for(repo_root, slug)
    worktrees_root = (repo_root / ".agents" / "worktrees").resolve()
    try:
        worktree_path.relative_to(worktrees_root)
    except ValueError:
        return False
    return True


def _sandbox_metadata(context: ToolRuntimeContext) -> dict[str, str]:
    metadata: dict[str, str] = {}
    if context.current_run_id:
        metadata["run_id"] = str(context.current_run_id)
    if context.current_task_id:
        metadata["task_id"] = str(context.current_task_id)
    if context.current_run_id and context.artifact_blob_store is not None:
        artifact_root = context.artifact_blob_store.run_artifact_root(context.workspace, context.current_run_id)
        metadata.update(
            {
                "artifacts_root": artifact_root.as_posix(),
                "artifact_host_root": artifact_root.as_posix(),
                "artifact_mount_path": "/artifacts",
            }
        )
    return metadata
