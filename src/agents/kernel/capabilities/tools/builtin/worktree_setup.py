from __future__ import annotations

import os
import shutil
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any

from agents.kernel.capabilities.tools.context import ToolRuntimeContext
from agents.kernel.capabilities.tools.builtin.worktree_git import git, git_common_dir


def perform_post_creation_setup(
    repo_root: Path,
    worktree_path: Path,
    *,
    symlink_directories: list[str],
) -> dict[str, Any]:
    copied_files = _copy_worktree_include_files(repo_root, worktree_path)
    copied_local_files = _copy_local_settings_files(repo_root, worktree_path)
    symlinked = _symlink_directories(repo_root, worktree_path, symlink_directories)
    hooks_path = _configure_hooks_path(repo_root, worktree_path)
    return {
        "copiedFiles": copied_files,
        "copiedLocalFiles": copied_local_files,
        "symlinkedDirectories": symlinked,
        "hooksPath": hooks_path,
    }


def ensure_worktrees_excluded(repo_root: Path) -> None:
    common_dir = git_common_dir(repo_root)
    exclude = common_dir / "info" / "exclude"
    pattern = "/.agents/worktrees/"
    legacy_pattern = ".agents/worktrees/"
    lines = exclude.read_text(encoding="utf-8").splitlines() if exclude.is_file() else []
    stripped = [line.strip() for line in lines]
    if pattern in stripped:
        return
    if legacy_pattern in stripped:
        updated = [pattern if line.strip() == legacy_pattern else line for line in lines]
        exclude.write_text("%s\n" % "\n".join(updated), encoding="utf-8")
        return
    exclude.parent.mkdir(parents=True, exist_ok=True)
    with exclude.open("a", encoding="utf-8") as handle:
        if lines and lines[-1] != "":
            handle.write("\n")
        handle.write("%s\n" % pattern)


def worktree_settings(context: ToolRuntimeContext) -> dict[str, list[str]]:
    metadata = getattr(getattr(context, "agent_spec", None), "metadata", None)
    worktree = metadata.get("worktree") if isinstance(metadata, dict) else {}
    worktree = worktree if isinstance(worktree, dict) else {}
    sparse_paths = _string_list_setting(
        worktree.get("sparse_paths", worktree.get("sparsePaths")),
        _settings_value(context, "WORKTREE_SPARSE_PATHS"),
    )
    symlink_directories = _string_list_setting(
        worktree.get("symlink_directories", worktree.get("symlinkDirectories")),
        _settings_value(context, "WORKTREE_SYMLINK_DIRECTORIES"),
    )
    return {
        "sparse_paths": _safe_relative_values(sparse_paths),
        "symlink_directories": _safe_relative_values(symlink_directories),
    }


def _copy_worktree_include_files(repo_root: Path, worktree_path: Path) -> list[str]:
    include_file = repo_root / ".worktreeinclude"
    if not include_file.is_file():
        return []
    patterns = _worktree_include_patterns(include_file)
    if not patterns:
        return []
    ignored = git(repo_root, ["ls-files", "--others", "--ignored", "--exclude-standard", "-z"], check=False, timeout=60)
    if ignored.returncode != 0 or not ignored.stdout:
        return []
    copied: list[str] = []
    seen: set[str] = set()
    for relative_path in [item for item in ignored.stdout.split("\0") if item]:
        if relative_path in seen or not _matches_worktree_include(relative_path, patterns):
            continue
        seen.add(relative_path)
        if _copy_repo_file(repo_root, worktree_path, relative_path):
            copied.append(relative_path)
    return copied


def _copy_local_settings_files(repo_root: Path, worktree_path: Path) -> list[str]:
    copied: list[str] = []
    for relative_path in (".env", "config/local.toml", ".agents/settings.local.json"):
        source = repo_root / relative_path
        if not source.is_file() or not _path_is_git_ignored(repo_root, relative_path):
            continue
        if _copy_repo_file(repo_root, worktree_path, relative_path):
            copied.append(relative_path)
    return copied


def _copy_repo_file(repo_root: Path, worktree_path: Path, relative_path: str) -> bool:
    try:
        source = _resolve_repo_relative(repo_root, relative_path)
        destination = _resolve_repo_relative(worktree_path, relative_path)
    except ValueError:
        return False
    if not source.is_file():
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return True


def _worktree_include_patterns(path: Path) -> list[str]:
    patterns: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        patterns.append(value)
    return patterns


def _matches_worktree_include(relative_path: str, patterns: list[str]) -> bool:
    normalized = relative_path.strip("/")
    parts = [part for part in normalized.split("/") if part]
    basename = parts[-1] if parts else normalized
    for raw_pattern in patterns:
        pattern = raw_pattern.strip()
        if not pattern:
            continue
        anchored = pattern.startswith("/")
        if anchored:
            pattern = pattern.lstrip("/")
        if pattern.endswith("/"):
            directory = pattern.rstrip("/")
            if normalized == directory or normalized.startswith("%s/" % directory):
                return True
            if not anchored and any(part == directory for part in parts[:-1]):
                return True
            continue
        if "/" in pattern or anchored:
            if fnmatchcase(normalized, pattern) or fnmatchcase("/" + normalized, "/" + pattern):
                return True
            continue
        if fnmatchcase(basename, pattern) or fnmatchcase(normalized, pattern) or fnmatchcase(normalized, "*/%s" % pattern):
            return True
    return False


def _symlink_directories(repo_root: Path, worktree_path: Path, directories: list[str]) -> list[str]:
    linked: list[str] = []
    for relative_path in directories:
        try:
            source = _resolve_repo_relative(repo_root, relative_path)
            destination = _resolve_repo_relative(worktree_path, relative_path)
        except ValueError:
            continue
        if not source.is_dir() or destination.exists() or destination.is_symlink():
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(source, destination, target_is_directory=True)
        linked.append(relative_path)
    return linked


def _configure_hooks_path(repo_root: Path, worktree_path: Path) -> str:
    hooks_path = _hooks_path(repo_root)
    if hooks_path is None:
        return ""
    result = git(worktree_path, ["config", "core.hooksPath", str(hooks_path)], check=False)
    return str(hooks_path) if result.returncode == 0 else ""


def _hooks_path(repo_root: Path) -> Path | None:
    husky = repo_root / ".husky"
    if husky.is_dir():
        return husky.resolve()
    common_dir = git_common_dir(repo_root)
    hooks = common_dir / "hooks"
    return hooks.resolve() if hooks.is_dir() else None


def _path_is_git_ignored(repo_root: Path, relative_path: str) -> bool:
    result = git(repo_root, ["check-ignore", "-q", "--", relative_path], check=False)
    return result.returncode == 0


def _resolve_repo_relative(root: Path, relative_path: str) -> Path:
    value = str(relative_path or "").strip()
    candidate = Path(value)
    if candidate.is_absolute() or any(part in {"", ".", ".."} for part in candidate.parts):
        raise ValueError("invalid relative path: %s" % relative_path)
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError("path escapes root: %s" % relative_path) from exc
    return resolved


def _settings_value(context: ToolRuntimeContext, name: str) -> Any:
    agent = getattr(getattr(context, "settings", None), "agent", None)
    return getattr(agent, name, None) if agent is not None else None


def _string_list_setting(*values: Any) -> list[str]:
    result: list[str] = []
    for value in values:
        if not value:
            continue
        if isinstance(value, str):
            result.extend(part.strip() for part in value.split(",") if part.strip())
        elif isinstance(value, (list, tuple, set)):
            result.extend(str(item).strip() for item in value if str(item).strip())
    return result


def _safe_relative_values(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.strip().strip("/")
        path = Path(normalized)
        if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
            continue
        if normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result
