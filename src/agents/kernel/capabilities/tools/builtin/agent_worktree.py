from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

from agents.kernel.capabilities.tools.builtin.worktree_git import count_worktree_changes, create_git_worktree, git, git_error, git_root
from agents.kernel.capabilities.tools.builtin.worktree_naming import worktree_branch_name, worktree_path_for, worktree_slug
from agents.kernel.capabilities.tools.builtin.worktree_setup import ensure_worktrees_excluded, perform_post_creation_setup, worktree_settings
from agents.kernel.capabilities.tools.context import ToolRuntimeContext


@dataclass(frozen=True)
class AgentWorktree:
    repo_root: Path
    path: Path
    branch: str
    original_head: str
    clean_ignored_paths: frozenset[str] = field(default_factory=frozenset)


def create_agent_worktree(context: ToolRuntimeContext, child_agent_id: str) -> AgentWorktree:
    repo_root = git_root(Path(context.workspace.path))
    slug = _agent_worktree_slug(child_agent_id)
    branch = worktree_branch_name(slug)
    path = worktree_path_for(repo_root, slug)
    original_head = git(repo_root, ["rev-parse", "HEAD"]).stdout.strip()
    settings = worktree_settings(context)
    ensure_worktrees_excluded(repo_root)
    create_git_worktree(repo_root, path, branch, base_ref="HEAD", sparse_paths=settings["sparse_paths"])
    setup = perform_post_creation_setup(repo_root, path, symlink_directories=settings["symlink_directories"])
    return AgentWorktree(
        repo_root=repo_root,
        path=path,
        branch=branch,
        original_head=original_head,
        clean_ignored_paths=frozenset(_setup_clean_ignored_paths(setup)),
    )


def cleanup_agent_worktree(worktree: AgentWorktree) -> dict[str, Any]:
    changes = count_worktree_changes(worktree.path, worktree.original_head, clean_ignored_paths=worktree.clean_ignored_paths)
    if changes is None:
        return _kept_worktree_fields(worktree, cleanup_error="could not inspect worktree changes")
    if int(changes.get("changedFiles", 0)) or int(changes.get("commits", 0)):
        return _kept_worktree_fields(worktree, changes=changes)
    removed = git(worktree.repo_root, ["worktree", "remove", "--force", str(worktree.path)], check=False, timeout=60)
    if removed.returncode != 0:
        return _kept_worktree_fields(worktree, changes=changes, cleanup_error=git_error("Failed to remove clean agent worktree", removed))
    deleted = git(worktree.repo_root, ["branch", "-D", worktree.branch], check=False, timeout=60)
    fields = {"worktreeKept": False, "worktreeChangedFiles": 0, "worktreeCommits": 0}
    if deleted.returncode != 0:
        fields["worktreeCleanupError"] = git_error("Failed to delete clean agent worktree branch", deleted)
    return fields


def _kept_worktree_fields(
    worktree: AgentWorktree,
    *,
    changes: dict[str, int] | None = None,
    cleanup_error: str = "",
) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "worktreePath": str(worktree.path),
        "worktreeBranch": worktree.branch,
        "worktreeKept": True,
    }
    if changes is not None:
        fields["worktreeChangedFiles"] = int(changes.get("changedFiles", 0))
        fields["worktreeCommits"] = int(changes.get("commits", 0))
    if cleanup_error:
        fields["worktreeCleanupError"] = cleanup_error
    return fields


def _agent_worktree_slug(child_agent_id: str) -> str:
    token = "".join(ch for ch in str(child_agent_id or "") if ch.isalnum() or ch in ("_", "-", ".")).strip(".-_")
    token = token[:32] or "subagent"
    return worktree_slug("agent-%s-%s" % (token, uuid4().hex[:8]))


def _setup_clean_ignored_paths(setup: dict[str, Any]) -> list[str]:
    return [str(path).strip("/") for key in ("copiedFiles", "copiedLocalFiles", "symlinkedDirectories") for path in setup.get(key, []) if path]
