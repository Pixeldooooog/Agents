from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agents.kernel.context.workspace import WorkspaceContext


SKIPPED_PARTS = {".agents", ".git", "__pycache__", ".venv", "node_modules"}


@dataclass(frozen=True)
class WorkspaceFileState:
    path: str
    size: int
    mtime: float
    sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "size": self.size,
            "mtime": self.mtime,
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class WorkspaceSnapshot:
    captured_at: float
    files: dict[str, WorkspaceFileState] = field(default_factory=dict)

    @classmethod
    def capture(cls, workspace: WorkspaceContext) -> "WorkspaceSnapshot":
        root = workspace.path.resolve()
        files: dict[str, WorkspaceFileState] = {}
        if not root.exists():
            return cls(captured_at=time.time(), files=files)
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            try:
                relative = path.relative_to(root).as_posix()
            except ValueError:
                continue
            if _should_skip(relative):
                continue
            if path.is_symlink() and not _target_stays_in_workspace(path, root):
                continue
            try:
                stat = path.stat()
                digest = _sha256(path)
            except OSError:
                continue
            files[relative] = WorkspaceFileState(
                path=relative,
                size=int(stat.st_size),
                mtime=float(stat.st_mtime),
                sha256=digest,
            )
        return cls(captured_at=time.time(), files=files)

    def diff(self, other: "WorkspaceSnapshot") -> dict[str, Any]:
        before = self.files
        after = other.files
        created = sorted(path for path in after if path not in before)
        deleted = sorted(path for path in before if path not in after)
        modified = sorted(path for path in after if path in before and after[path].sha256 != before[path].sha256)
        return {
            "created": created,
            "modified": modified,
            "deleted": deleted,
            "file_count_before": len(before),
            "file_count_after": len(after),
            "total_bytes_before": sum(item.size for item in before.values()),
            "total_bytes_after": sum(item.size for item in after.values()),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "captured_at": self.captured_at,
            "files": {path: state.to_dict() for path, state in self.files.items()},
        }


def _should_skip(relative_path: str) -> bool:
    return any(part in SKIPPED_PARTS for part in Path(relative_path).parts)


def _target_stays_in_workspace(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root)
    except (OSError, ValueError):
        return False
    return True


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
