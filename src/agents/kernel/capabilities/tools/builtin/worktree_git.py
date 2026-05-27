from __future__ import annotations

import os
import subprocess
from pathlib import Path


GIT_NO_PROMPT_ENV = {
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_ASKPASS": "",
}


def git(cwd: Path, args: list[str], *, check: bool = True, timeout: float = 30.0) -> subprocess.CompletedProcess[str]:
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
        raise RuntimeError(git_error("Git command failed", result))
    return result


def git_error(prefix: str, result: subprocess.CompletedProcess[str]) -> str:
    detail = (result.stderr or result.stdout or "").strip()
    return "%s: %s" % (prefix, detail or "exit code %s" % result.returncode)


def git_root(path: Path) -> Path:
    result = git(Path(path), ["rev-parse", "--show-toplevel"], check=False)
    if result.returncode != 0:
        raise RuntimeError("Cannot create a worktree: current workspace is not in a git repository.")
    return Path(result.stdout.strip()).expanduser().resolve()


def is_git_worktree(path: Path) -> bool:
    if not path.exists():
        return False
    result = git(path, ["rev-parse", "--is-inside-work-tree"], check=False)
    return result.returncode == 0 and result.stdout.strip() == "true"


def count_worktree_changes(worktree_path: Path, original_head: str) -> dict[str, int] | None:
    status = git(worktree_path, ["status", "--porcelain", "--untracked-files=all"], check=False)
    if status.returncode != 0:
        return None
    changed_files = len([line for line in status.stdout.splitlines() if line.strip()])
    commits = 0
    if original_head:
        rev_list = git(worktree_path, ["rev-list", "--count", "%s..HEAD" % original_head], check=False)
        if rev_list.returncode != 0:
            return None
        commits = int((rev_list.stdout.strip() or "0"))
    return {"changedFiles": changed_files, "commits": commits}


def prepare_worktree_base_ref(repo_root: Path, pr_number: int | None) -> str:
    if pr_number is None:
        return "HEAD"
    result = git(repo_root, ["fetch", "origin", "pull/%d/head" % pr_number], check=False, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(git_error("Failed to fetch PR #%d" % pr_number, result))
    return "FETCH_HEAD"


def create_git_worktree(repo_root: Path, worktree_path: Path, branch: str, *, base_ref: str, sparse_paths: list[str]) -> None:
    worktree_path.parent.mkdir(parents=True, exist_ok=True)
    args = ["worktree", "add"]
    if sparse_paths:
        args.append("--no-checkout")
    args.extend(["-B", branch, str(worktree_path), base_ref])
    result = git(repo_root, args, check=False, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(git_error("Failed to create worktree", result))
    if not sparse_paths:
        return
    sparse = git(
        worktree_path,
        ["sparse-checkout", "set", "--cone", "--", *sparse_paths],
        check=False,
        timeout=60,
    )
    if sparse.returncode != 0:
        git(repo_root, ["worktree", "remove", "--force", str(worktree_path)], check=False, timeout=60)
        raise RuntimeError(git_error("Failed to configure sparse-checkout", sparse))
    checkout = git(worktree_path, ["checkout", "HEAD"], check=False, timeout=60)
    if checkout.returncode != 0:
        git(repo_root, ["worktree", "remove", "--force", str(worktree_path)], check=False, timeout=60)
        raise RuntimeError(git_error("Failed to checkout sparse worktree", checkout))


def git_common_dir(repo_root: Path) -> Path:
    result = git(repo_root, ["rev-parse", "--git-common-dir"])
    raw = Path(result.stdout.strip())
    if raw.is_absolute():
        return raw.resolve()
    return (repo_root / raw).resolve()
