from __future__ import annotations

import os
import re
import shutil
import subprocess
import uuid
from dataclasses import replace
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any

from agents.kernel.capabilities.sandbox.factory import create_sandbox_client_from_profile
from agents.kernel.capabilities.sandbox.types import SandboxProfile
from agents.kernel.capabilities.tools.context import ToolRuntimeContext, _scoped_lease_id
from agents.kernel.session_state import save_session_state


NO_ACTIVE_WORKTREE_SESSION_MESSAGE = (
    "No-op: there is no active EnterWorktree session to exit. "
    "This tool only operates on worktrees created by EnterWorktree in the current session. "
    "No filesystem changes were made."
)

WORKTREE_ENTER_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {
            "type": "string",
            "description": "Optional worktree name or PR reference (#123 or a GitHub /pull/123 URL). Slash-separated name segments are flattened for the actual branch/path.",
        },
        "pr_number": {
            "type": "integer",
            "minimum": 1,
            "description": "Optional pull request number. When provided, the worktree is created from origin pull/<number>/head.",
        },
        "prNumber": {
            "type": "integer",
            "minimum": 1,
            "description": "CamelCase alias for pr_number.",
        },
    },
    "additionalProperties": False,
}

WORKTREE_EXIT_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": ["keep", "remove"],
            "description": "keep preserves the worktree; remove deletes the worktree and its branch.",
        },
        "discard_changes": {
            "type": "boolean",
            "description": "Required to remove a worktree that has uncommitted files or commits after its base.",
        },
    },
    "required": ["action"],
    "additionalProperties": False,
}

MAX_WORKTREE_SLUG_LENGTH = 64
VALID_WORKTREE_SLUG_SEGMENT = re.compile(r"^[A-Za-z0-9._-]+$")
GIT_NO_PROMPT_ENV = {
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_ASKPASS": "",
}


async def enter_worktree(
    context: ToolRuntimeContext,
    name: str = "",
    pr_number: int | None = None,
    pr_number_alias: int | None = None,
) -> dict[str, Any]:
    if context.active_worktree_session:
        session = context.active_worktree_session
        raise RuntimeError("Already in a worktree session at %s" % session.get("worktreePath", "unknown"))

    repo_root = _git_root(context.workspace.path)
    slug, resolved_pr_number = _worktree_request(name, pr_number=pr_number, pr_number_alias=pr_number_alias)
    worktree_path = _worktree_path_for(repo_root, slug)
    branch = _worktree_branch_name(slug)
    settings = _worktree_settings(context)
    _ensure_worktrees_excluded(repo_root)

    post_create: dict[str, Any] = {}
    existed = _is_git_worktree(worktree_path)
    base_ref = "HEAD"
    if not existed:
        base_ref = _prepare_worktree_base_ref(repo_root, resolved_pr_number)
        _create_git_worktree(repo_root, worktree_path, branch, base_ref=base_ref, sparse_paths=settings["sparse_paths"])
        post_create = _perform_post_creation_setup(
            repo_root,
            worktree_path,
            symlink_directories=settings["symlink_directories"],
        )
    worktree_head = _git(worktree_path, ["rev-parse", "HEAD"]).stdout.strip()

    session = {
        "originalCwd": str(repo_root),
        "worktreePath": str(worktree_path),
        "worktreeName": slug,
        "worktreeBranch": branch,
        "originalHeadCommit": worktree_head,
        "sessionId": str(context.current_run_id or context.task_id or uuid.uuid4().hex),
        "usedSparsePaths": bool(settings["sparse_paths"] and not existed),
        "prNumber": resolved_pr_number,
        **post_create,
    }
    context.active_worktree_session = session
    _switch_workspace(context, worktree_path)
    await save_session_state(context)

    action = "Resumed" if existed else "Created"
    return {
        "worktreePath": str(worktree_path),
        "worktreeBranch": branch,
        "resumed": existed,
        "copiedFiles": list(post_create.get("copiedFiles") or []),
        "copiedLocalFiles": list(post_create.get("copiedLocalFiles") or []),
        "symlinkedDirectories": list(post_create.get("symlinkedDirectories") or []),
        "hooksPath": str(post_create.get("hooksPath") or ""),
        "usedSparsePaths": bool(settings["sparse_paths"] and not existed),
        "prNumber": resolved_pr_number,
        "baseRef": base_ref,
        "headCommit": worktree_head,
        "message": "%s worktree at %s on branch %s. Session is now using that worktree." % (action, worktree_path, branch),
    }


async def exit_worktree(context: ToolRuntimeContext, action: str, discard_changes: bool = False) -> dict[str, Any]:
    normalized_action = str(action or "").strip()
    if normalized_action not in {"keep", "remove"}:
        raise ValueError("action must be keep or remove")
    session = dict(context.active_worktree_session or {})
    if not session:
        original_cwd = Path(context.workspace.path).expanduser().resolve()
        return {
            "action": normalized_action,
            "noop": True,
            "reason": "no_active_worktree_session",
            "originalCwd": str(original_cwd),
            "worktreePath": "",
            "worktreeBranch": "",
            "message": NO_ACTIVE_WORKTREE_SESSION_MESSAGE,
        }

    original_cwd = Path(str(session.get("originalCwd") or "")).expanduser().resolve()
    worktree_path = Path(str(session.get("worktreePath") or "")).expanduser().resolve()
    branch = str(session.get("worktreeBranch") or "")
    original_head = str(session.get("originalHeadCommit") or "")
    changes = _count_worktree_changes(worktree_path, original_head)

    if normalized_action == "remove" and not discard_changes and (changes is None or changes["changedFiles"] or changes["commits"]):
        if changes is None:
            detail = "Could not verify worktree changes."
        else:
            parts = []
            if changes["changedFiles"]:
                parts.append("%d changed file(s)" % changes["changedFiles"])
            if changes["commits"]:
                parts.append("%d commit(s)" % changes["commits"])
            detail = "Worktree contains %s." % " and ".join(parts)
        raise RuntimeError("%s Re-run with discard_changes=true to remove it." % detail)

    changed_files = int((changes or {}).get("changedFiles") or 0)
    commits = int((changes or {}).get("commits") or 0)
    _switch_workspace(context, original_cwd)
    context.active_worktree_session = {}

    if normalized_action == "keep":
        await save_session_state(context)
        return {
            "action": "keep",
            "originalCwd": str(original_cwd),
            "worktreePath": str(worktree_path),
            "worktreeBranch": branch,
            "message": "Exited worktree. Your work is preserved at %s%s. Session is now back in %s."
            % (worktree_path, " on branch %s" % branch if branch else "", original_cwd),
        }

    remove = _git(original_cwd, ["worktree", "remove", "--force", str(worktree_path)], check=False, timeout=60)
    if remove.returncode != 0:
        context.active_worktree_session = session
        _switch_workspace(context, worktree_path)
        raise RuntimeError(_git_error("Failed to remove worktree", remove))
    branch_delete_error = ""
    if branch:
        deleted = _git(original_cwd, ["branch", "-D", branch], check=False)
        if deleted.returncode != 0:
            branch_delete_error = _git_error("Could not delete worktree branch", deleted)
    await save_session_state(context)

    discard_parts = []
    if commits:
        discard_parts.append("%d commit%s" % (commits, "" if commits == 1 else "s"))
    if changed_files:
        discard_parts.append("%d uncommitted file%s" % (changed_files, "" if changed_files == 1 else "s"))
    discard_note = " Discarded %s." % " and ".join(discard_parts) if discard_parts else ""
    warning = " %s" % branch_delete_error if branch_delete_error else ""
    return {
        "action": "remove",
        "originalCwd": str(original_cwd),
        "worktreePath": str(worktree_path),
        "worktreeBranch": branch,
        "discardedFiles": changed_files,
        "discardedCommits": commits,
        "message": "Exited and removed worktree at %s.%s Session is now back in %s.%s"
        % (worktree_path, discard_note, original_cwd, warning),
    }


def restore_active_worktree_session(context: ToolRuntimeContext, session: dict[str, Any]) -> bool:
    restored = _normalized_worktree_session(session)
    if not restored:
        context.active_worktree_session = {}
        return False

    try:
        repo_root = _git_root(context.workspace.path)
    except (OSError, subprocess.SubprocessError, RuntimeError):
        context.active_worktree_session = {}
        return False

    original_cwd = Path(str(restored.get("originalCwd") or "")).expanduser().resolve()
    worktree_path = Path(str(restored.get("worktreePath") or "")).expanduser().resolve()
    if original_cwd != repo_root or not _is_known_worktree_path(repo_root, worktree_path, restored):
        context.active_worktree_session = {}
        return False
    try:
        is_worktree = _is_git_worktree(worktree_path)
    except (OSError, subprocess.SubprocessError):
        is_worktree = False
    if not is_worktree:
        context.active_worktree_session = {}
        return False

    restored["originalCwd"] = str(original_cwd)
    restored["worktreePath"] = str(worktree_path)
    context.active_worktree_session = restored
    _switch_workspace(context, worktree_path)
    return True


def format_worktree_result(result: Any) -> str:
    payload = result if isinstance(result, dict) else {}
    return str(payload.get("message") or payload)


def validate_worktree_slug(slug: str) -> None:
    value = str(slug or "")
    if len(value) > MAX_WORKTREE_SLUG_LENGTH:
        raise ValueError("Invalid worktree name: must be %d characters or fewer" % MAX_WORKTREE_SLUG_LENGTH)
    for segment in value.split("/"):
        if segment in {"", ".", ".."}:
            raise ValueError('Invalid worktree name "%s": must not contain empty, "." or ".." path segments' % value)
        if not VALID_WORKTREE_SLUG_SEGMENT.match(segment):
            raise ValueError(
                'Invalid worktree name "%s": each "/"-separated segment must contain only letters, digits, dots, underscores, and dashes'
                % value
            )


def _worktree_slug(name: str) -> str:
    value = str(name or "").strip()
    if not value:
        value = "worktree-%s" % uuid.uuid4().hex[:8]
    validate_worktree_slug(value)
    return value


def _worktree_request(
    name: str,
    *,
    pr_number: int | None,
    pr_number_alias: int | None = None,
) -> tuple[str, int | None]:
    value = str(name or "").strip()
    parsed_pr_number = _parse_pr_reference(value) if value else None
    explicit_pr_number = _explicit_pr_number(pr_number, pr_number_alias)
    if parsed_pr_number is not None and explicit_pr_number is not None and parsed_pr_number != explicit_pr_number:
        raise ValueError("Conflicting pull request references: name=%s pr_number=%s" % (value, explicit_pr_number))
    resolved_pr_number = explicit_pr_number if explicit_pr_number is not None else parsed_pr_number
    if resolved_pr_number is not None:
        return _worktree_slug("pr-%d" % resolved_pr_number), resolved_pr_number
    return _worktree_slug(value), None


def _positive_pr_number(value: int | None) -> int | None:
    if value is None:
        return None
    number = int(value)
    if number <= 0:
        raise ValueError("pr_number must be a positive integer")
    return number


def _explicit_pr_number(pr_number: int | None, pr_number_alias: int | None) -> int | None:
    snake = _positive_pr_number(pr_number)
    camel = _positive_pr_number(pr_number_alias)
    if snake is not None and camel is not None and snake != camel:
        raise ValueError("Conflicting pull request numbers: pr_number=%s prNumber=%s" % (snake, camel))
    return snake if snake is not None else camel


def _parse_pr_reference(value: str) -> int | None:
    text = str(value or "").strip()
    url_match = re.match(r"^https?://[^/]+/[^/]+/[^/]+/pull/(\d+)/?(?:[?#].*)?$", text, flags=re.IGNORECASE)
    if url_match:
        return int(url_match.group(1))
    hash_match = re.match(r"^#(\d+)$", text)
    if hash_match:
        return int(hash_match.group(1))
    return None


def _flatten_slug(slug: str) -> str:
    return slug.replace("/", "+")


def _worktree_branch_name(slug: str) -> str:
    return "worktree-%s" % _flatten_slug(slug)


def _worktree_path_for(repo_root: Path, slug: str) -> Path:
    return (repo_root / ".agents" / "worktrees" / _flatten_slug(slug)).resolve()


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
        return worktree_path == _worktree_path_for(repo_root, slug)
    worktrees_root = (repo_root / ".agents" / "worktrees").resolve()
    try:
        worktree_path.relative_to(worktrees_root)
    except ValueError:
        return False
    return True


def _prepare_worktree_base_ref(repo_root: Path, pr_number: int | None) -> str:
    if pr_number is None:
        return "HEAD"
    result = _git(repo_root, ["fetch", "origin", "pull/%d/head" % pr_number], check=False, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(_git_error("Failed to fetch PR #%d" % pr_number, result))
    return "FETCH_HEAD"


def _create_git_worktree(repo_root: Path, worktree_path: Path, branch: str, *, base_ref: str, sparse_paths: list[str]) -> None:
    worktree_path.parent.mkdir(parents=True, exist_ok=True)
    args = ["worktree", "add"]
    if sparse_paths:
        args.append("--no-checkout")
    args.extend(["-B", branch, str(worktree_path), base_ref])
    result = _git(repo_root, args, check=False, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(_git_error("Failed to create worktree", result))
    if not sparse_paths:
        return
    sparse = _git(
        worktree_path,
        ["sparse-checkout", "set", "--cone", "--", *sparse_paths],
        check=False,
        timeout=60,
    )
    if sparse.returncode != 0:
        _git(repo_root, ["worktree", "remove", "--force", str(worktree_path)], check=False, timeout=60)
        raise RuntimeError(_git_error("Failed to configure sparse-checkout", sparse))
    checkout = _git(worktree_path, ["checkout", "HEAD"], check=False, timeout=60)
    if checkout.returncode != 0:
        _git(repo_root, ["worktree", "remove", "--force", str(worktree_path)], check=False, timeout=60)
        raise RuntimeError(_git_error("Failed to checkout sparse worktree", checkout))


def _git_root(path: Path) -> Path:
    result = _git(Path(path), ["rev-parse", "--show-toplevel"], check=False)
    if result.returncode != 0:
        raise RuntimeError("Cannot create a worktree: current workspace is not in a git repository.")
    return Path(result.stdout.strip()).expanduser().resolve()


def _is_git_worktree(path: Path) -> bool:
    if not path.exists():
        return False
    result = _git(path, ["rev-parse", "--is-inside-work-tree"], check=False)
    return result.returncode == 0 and result.stdout.strip() == "true"


def _count_worktree_changes(worktree_path: Path, original_head: str) -> dict[str, int] | None:
    status = _git(worktree_path, ["status", "--porcelain", "--untracked-files=all"], check=False)
    if status.returncode != 0:
        return None
    changed_files = len([line for line in status.stdout.splitlines() if line.strip()])
    commits = 0
    if original_head:
        rev_list = _git(worktree_path, ["rev-list", "--count", "%s..HEAD" % original_head], check=False)
        if rev_list.returncode != 0:
            return None
        commits = int((rev_list.stdout.strip() or "0"))
    return {"changedFiles": changed_files, "commits": commits}


def _perform_post_creation_setup(
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


def _copy_worktree_include_files(repo_root: Path, worktree_path: Path) -> list[str]:
    include_file = repo_root / ".worktreeinclude"
    if not include_file.is_file():
        return []
    patterns = _worktree_include_patterns(include_file)
    if not patterns:
        return []
    ignored = _git(repo_root, ["ls-files", "--others", "--ignored", "--exclude-standard", "-z"], check=False, timeout=60)
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
    result = _git(worktree_path, ["config", "core.hooksPath", str(hooks_path)], check=False)
    return str(hooks_path) if result.returncode == 0 else ""


def _hooks_path(repo_root: Path) -> Path | None:
    husky = repo_root / ".husky"
    if husky.is_dir():
        return husky.resolve()
    common_dir = _git_common_dir(repo_root)
    hooks = common_dir / "hooks"
    return hooks.resolve() if hooks.is_dir() else None


def _ensure_worktrees_excluded(repo_root: Path) -> None:
    common_dir = _git_common_dir(repo_root)
    exclude = common_dir / "info" / "exclude"
    pattern = ".agents/worktrees/"
    lines = exclude.read_text(encoding="utf-8").splitlines() if exclude.is_file() else []
    if pattern in [line.strip() for line in lines]:
        return
    exclude.parent.mkdir(parents=True, exist_ok=True)
    with exclude.open("a", encoding="utf-8") as handle:
        if lines and lines[-1] != "":
            handle.write("\n")
        handle.write("%s\n" % pattern)


def _path_is_git_ignored(repo_root: Path, relative_path: str) -> bool:
    result = _git(repo_root, ["check-ignore", "-q", "--", relative_path], check=False)
    return result.returncode == 0


def _git_common_dir(repo_root: Path) -> Path:
    result = _git(repo_root, ["rev-parse", "--git-common-dir"])
    raw = Path(result.stdout.strip())
    if raw.is_absolute():
        return raw.resolve()
    return (repo_root / raw).resolve()


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


def _worktree_settings(context: ToolRuntimeContext) -> dict[str, list[str]]:
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


def _switch_workspace(context: ToolRuntimeContext, path: Path) -> None:
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


def _git(cwd: Path, args: list[str], *, check: bool = True, timeout: float = 30.0) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env.update(GIT_NO_PROMPT_ENV)
    result = subprocess.run(
        ["git", *args],
        cwd=str(Path(cwd).expanduser()),
        text=True,
        capture_output=True,
        env=env,
        timeout=timeout,
        check=False,
    )
    if check and result.returncode != 0:
        raise RuntimeError(_git_error("Git command failed", result))
    return result


def _git_error(prefix: str, result: subprocess.CompletedProcess[str]) -> str:
    detail = (result.stderr or result.stdout or "").strip()
    return "%s: %s" % (prefix, detail or "exit code %s" % result.returncode)
