from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from agents.kernel.context.workspace import WorkspaceContext
from agents.kernel.governance import SandboxPolicy


@dataclass(frozen=True)
class SandboxProfile:
    name: str = "restricted"
    provider: str = "local"
    image: str = "python:3.12-slim"
    network_mode: str = "none"
    memory: str = ""
    cpus: str = ""
    ttl_seconds: int = 0
    workdir: str = "/workspace"


@dataclass(frozen=True)
class SandboxLease:
    lease_id: str
    provider: str
    workspace: WorkspaceContext
    profile: SandboxProfile
    created_at: float = field(default_factory=time.time)
    expires_at: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SandboxFileRead:
    path: str
    content: str
    bytes: int
    truncated: bool = False
    encoding: str = "utf-8"
    line_endings: str = "none"
    start_line: int = 1
    num_lines: int = 0
    total_lines: int = 0
    is_partial_view: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "content": self.content,
            "bytes": self.bytes,
            "truncated": self.truncated,
            "encoding": self.encoding,
            "line_endings": self.line_endings,
            "startLine": self.start_line,
            "numLines": self.num_lines,
            "totalLines": self.total_lines,
            "isPartialView": self.is_partial_view,
        }


@dataclass(frozen=True)
class SandboxFileWrite:
    path: str
    bytes: int
    encoding: str = "utf-8"

    def to_dict(self) -> dict[str, Any]:
        return {"path": self.path, "bytes": self.bytes, "encoding": self.encoding}


@dataclass(frozen=True)
class SandboxDirectoryEntry:
    name: str
    path: str
    type: str

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "path": self.path, "type": self.type}


@dataclass(frozen=True)
class SandboxDirectoryListing:
    path: str
    entries: list[SandboxDirectoryEntry]

    def to_dict(self) -> dict[str, Any]:
        return {"path": self.path, "entries": [entry.to_dict() for entry in self.entries]}


@dataclass(frozen=True)
class SandboxCommandResult:
    command: str
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "timed_out": self.timed_out,
        }


@dataclass
class SandboxBackgroundCommand:
    task_id: str
    command: str
    output_path: str
    status: str = "running"
    exit_code: int | None = None
    error: str = ""
    timed_out: bool = False
    started_at: float = field(default_factory=time.time)
    ended_at: float | None = None
    output_bytes: int = 0
    _task: Any | None = field(default=None, repr=False, compare=False)
    _kill: Any | None = field(default=None, repr=False, compare=False)

    def done(self) -> bool:
        return self.status in {"completed", "failed", "killed", "timed_out", "error"}

    def kill(self) -> None:
        if not self.done():
            self.status = "killed"
        callback = self._kill
        if callable(callback):
            callback()

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "task_id": self.task_id,
            "command": self.command,
            "output_path": self.output_path,
            "status": self.status,
            "running": not self.done(),
            "started_at": self.started_at,
            "output_bytes": int(self.output_bytes or 0),
        }
        if self.exit_code is not None:
            payload["exit_code"] = self.exit_code
        if self.error:
            payload["error"] = self.error
        if self.timed_out:
            payload["timed_out"] = True
        if self.ended_at is not None:
            payload["ended_at"] = self.ended_at
        return payload


@dataclass(frozen=True)
class SandboxGrepMatch:
    path: str
    line_number: int
    line: str
    is_match: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {"path": self.path, "line_number": self.line_number, "line": self.line, "is_match": self.is_match}


@dataclass(frozen=True)
class SandboxGrepResult:
    pattern: str
    path: str
    matches: list[SandboxGrepMatch]
    truncated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "pattern": self.pattern,
            "path": self.path,
            "matches": [match.to_dict() for match in self.matches],
            "truncated": self.truncated,
        }


@dataclass(frozen=True)
class SandboxGlobResult:
    pattern: str
    path: str
    filenames: list[str]
    duration_ms: int = 0
    truncated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "pattern": self.pattern,
            "path": self.path,
            "filenames": list(self.filenames),
            "durationMs": self.duration_ms,
            "numFiles": len(self.filenames),
            "truncated": self.truncated,
        }


class SandboxClient(Protocol):
    lease: SandboxLease
    policy: SandboxPolicy

    def read_text(
        self,
        path: str,
        max_bytes: int = 20000,
        offset: int = 1,
        limit: int | None = None,
    ) -> SandboxFileRead:
        raise NotImplementedError()

    def list_dir(self, path: str = ".") -> SandboxDirectoryListing:
        raise NotImplementedError()

    def write_text(self, path: str, content: str, encoding: str = "utf-8") -> SandboxFileWrite:
        raise NotImplementedError()

    def delete_path(self, path: str, recursive: bool = False) -> dict[str, Any]:
        raise NotImplementedError()

    def move_path(self, source_path: str, destination_path: str, overwrite: bool = False) -> dict[str, Any]:
        raise NotImplementedError()

    async def run_command(self, command: str, timeout_seconds: float = 20.0) -> SandboxCommandResult:
        raise NotImplementedError()

    async def start_background_command(
        self,
        task_id: str,
        command: str,
        output_path: str,
        timeout_seconds: float = 20.0,
    ) -> SandboxBackgroundCommand:
        raise NotImplementedError()

    def grep(
        self,
        pattern: str,
        path: str = ".",
        max_results: int = 100,
        case_sensitive: bool = True,
        glob_pattern: str = "",
        context_before: int = 0,
        context_after: int = 0,
        file_type: str = "",
        multiline: bool = False,
    ) -> SandboxGrepResult:
        raise NotImplementedError()

    def glob(
        self,
        pattern: str,
        path: str = ".",
        max_results: int = 100,
    ) -> SandboxGlobResult:
        raise NotImplementedError()


class SandboxProvider(Protocol):
    name: str

    def acquire(
        self,
        workspace: WorkspaceContext,
        policy: SandboxPolicy,
        profile: SandboxProfile | None = None,
        lease_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> SandboxClient:
        raise NotImplementedError()

    def release(self, client: SandboxClient) -> None:
        raise NotImplementedError()
