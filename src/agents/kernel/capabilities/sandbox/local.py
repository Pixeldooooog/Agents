from __future__ import annotations

import asyncio
import os
import shutil
import time
import uuid
from pathlib import Path

from agents.kernel.context.workspace import WorkspaceContext
from agents.kernel.governance import SandboxPolicy

from .local_files import (
    count_text_lines,
    ensure_regular_file,
    line_count,
    optional_positive_int,
    read_text_line_range,
    write_encoding as normalize_write_encoding,
)
from .local_process import (
    close_subprocess_transport,
    collect_background_process,
    decode_process_output,
    terminate_process,
)
from .local_search import glob_workspace, grep_workspace
from .text import (
    BINARY_SAMPLE_BYTES,
    DEFAULT_TEXT_READ_MAX_BYTES,
    decode_text_bytes,
    detect_line_endings,
    detect_text_encoding,
    encode_text_bytes,
    normalize_text_read_max_bytes,
    public_encoding_name,
    text_file_too_large_message,
)
from .types import (
    SandboxClient,
    SandboxBackgroundCommand,
    SandboxCommandResult,
    SandboxDirectoryEntry,
    SandboxDirectoryListing,
    SandboxFileRead,
    SandboxFileWrite,
    SandboxGlobResult,
    SandboxGrepResult,
    SandboxLease,
    SandboxProfile,
)


class LocalSandboxProvider:
    name = "local"

    def acquire(
        self,
        workspace: WorkspaceContext,
        policy: SandboxPolicy,
        profile: SandboxProfile | None = None,
        lease_id: str = "",
        metadata: dict | None = None,
    ) -> "LocalSandboxClient":
        lease = SandboxLease(
            lease_id=lease_id or "local-%s" % uuid.uuid4().hex,
            provider=self.name,
            workspace=workspace,
            profile=profile or SandboxProfile(provider=self.name),
            metadata=dict(metadata or {}),
        )
        return LocalSandboxClient(lease=lease, policy=policy)

    def release(self, client: SandboxClient) -> None:
        return None


class LocalSandboxClient:
    def __init__(self, lease: SandboxLease, policy: SandboxPolicy):
        self.lease = lease
        self.policy = policy

    def read_text(
        self,
        path: str,
        max_bytes: int = DEFAULT_TEXT_READ_MAX_BYTES,
        offset: int = 1,
        limit: int | None = None,
        require_full: bool = False,
    ) -> SandboxFileRead:
        decision = self.policy.authorize_file_read(path)
        if not decision.allowed:
            raise PermissionError(decision.reason)
        resolved = self.policy.resolve_workspace_path(path)
        relative = self.policy.relative_workspace_path(resolved)
        ensure_regular_file(resolved, relative, operation="read")
        if not resolved.is_file():
            raise FileNotFoundError(str(path))
        byte_limit = normalize_text_read_max_bytes(max_bytes)
        line_offset = max(0, int(offset or 1) - 1)
        line_limit = optional_positive_int(limit)
        range_requested = line_offset > 0 or line_limit is not None
        with resolved.open("rb") as handle:
            sample = handle.read(BINARY_SAMPLE_BYTES)
        encoding = detect_text_encoding(resolved, sample)
        write_encoding = normalize_write_encoding(encoding)
        size = resolved.stat().st_size
        if require_full and line_limit is None and size > byte_limit:
            raise ValueError(text_file_too_large_message(size, byte_limit))
        if range_requested:
            content = read_text_line_range(
                resolved,
                encoding=encoding,
                line_offset=line_offset,
                line_limit=line_limit,
            )
            total_lines = count_text_lines(resolved, encoding)
            data = encode_text_bytes(content, write_encoding)
            byte_count = len(data)
            truncated = line_offset + line_count(content) < total_lines
            num_lines = line_count(content)
        else:
            with resolved.open("rb") as handle:
                data = handle.read(byte_limit)
            content = decode_text_bytes(data, encoding)
            truncated = size > byte_limit
            num_lines = line_count(content)
            total_lines = num_lines
            if not truncated:
                total_lines = count_text_lines(resolved, encoding)
            byte_count = len(data)
        return SandboxFileRead(
            path=relative,
            content=content,
            bytes=byte_count,
            truncated=truncated,
            encoding=public_encoding_name(encoding),
            line_endings=detect_line_endings(content),
            start_line=line_offset + 1,
            num_lines=num_lines,
            total_lines=total_lines,
            is_partial_view=range_requested or truncated,
            write_encoding=write_encoding,
        )

    def list_dir(self, path: str = ".") -> SandboxDirectoryListing:
        decision = self.policy.authorize_file_read(path or ".")
        if not decision.allowed:
            raise PermissionError(decision.reason)
        resolved = self.policy.resolve_workspace_path(path or ".")
        if not resolved.is_dir():
            raise NotADirectoryError(str(path))
        entries = [
            SandboxDirectoryEntry(
                name=child.name,
                path=self.policy.relative_workspace_path(child),
                type="directory" if child.is_dir() else "file",
            )
            for child in sorted(resolved.iterdir(), key=lambda item: item.name)
        ]
        return SandboxDirectoryListing(path=self.policy.relative_workspace_path(resolved), entries=entries)

    def write_text(self, path: str, content: str, encoding: str = "utf-8") -> SandboxFileWrite:
        decision = self.policy.authorize_file_write(path)
        if not decision.allowed:
            raise PermissionError(decision.reason)
        resolved = self.policy.resolve_workspace_path(path)
        relative = self.policy.relative_workspace_path(resolved)
        ensure_regular_file(resolved, relative, operation="write")
        resolved.parent.mkdir(parents=True, exist_ok=True)
        text = str(content)
        write_encoding = normalize_write_encoding(encoding)
        data = encode_text_bytes(text, write_encoding)
        resolved.write_bytes(data)
        return SandboxFileWrite(
            path=relative,
            bytes=len(data),
            encoding=public_encoding_name(write_encoding),
            write_encoding=write_encoding,
        )

    def delete_path(self, path: str, recursive: bool = False) -> dict:
        decision = self.policy.authorize_file_write(path)
        if not decision.allowed:
            raise PermissionError(decision.reason)
        resolved = self.policy.resolve_workspace_entry_path(path)
        relative = self.policy.relative_workspace_entry_path(resolved)
        if relative == ".":
            raise PermissionError("refusing to delete workspace root")
        if not resolved.exists() and not resolved.is_symlink():
            return {"path": relative, "deleted": False, "reason": "not_found"}
        kind = "directory" if resolved.is_dir() and not resolved.is_symlink() else "file"
        if kind == "directory":
            if not recursive:
                raise IsADirectoryError("directory delete requires recursive=true: %s" % relative)
            shutil.rmtree(resolved)
        else:
            resolved.unlink()
        return {"path": relative, "type": kind, "deleted": True, "recursive": bool(recursive)}

    def move_path(self, source_path: str, destination_path: str, overwrite: bool = False) -> dict:
        read_decision = self.policy.authorize_file_read(source_path)
        if not read_decision.allowed:
            raise PermissionError(read_decision.reason)
        write_decision = self.policy.authorize_file_write(destination_path)
        if not write_decision.allowed:
            raise PermissionError(write_decision.reason)
        source = self.policy.resolve_workspace_entry_path(source_path)
        destination = self.policy.resolve_workspace_entry_path(destination_path)
        source_relative = self.policy.relative_workspace_entry_path(source)
        destination_relative = self.policy.relative_workspace_entry_path(destination)
        if source_relative == "." or destination_relative == ".":
            raise PermissionError("refusing to move workspace root")
        if not source.exists() and not source.is_symlink():
            raise FileNotFoundError(source_relative)
        if destination.exists() or destination.is_symlink():
            if not overwrite:
                raise FileExistsError(destination_relative)
            if destination.is_dir() and not destination.is_symlink():
                raise IsADirectoryError("refusing to overwrite directory: %s" % destination_relative)
            destination.unlink()
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(destination))
        return {
            "source_path": source_relative,
            "destination_path": destination_relative,
            "moved": True,
            "overwritten": bool(overwrite),
        }

    async def run_command(self, command: str, timeout_seconds: float = 20.0) -> SandboxCommandResult:
        decision = self.policy.authorize_process(command)
        if not decision.allowed:
            raise PermissionError(decision.reason)
        process = await asyncio.create_subprocess_shell(
            command,
            cwd=str(self.policy.workspace_root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=self._tool_env(),
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=float(timeout_seconds or 20.0))
        except asyncio.TimeoutError:
            process.kill()
            await process.communicate()
            return SandboxCommandResult(command=command, exit_code=-1, stderr="command timed out", timed_out=True)
        finally:
            await close_subprocess_transport(process)
        return SandboxCommandResult(
            command=command,
            exit_code=int(process.returncode or 0),
            stdout=decode_process_output(stdout, self.policy.max_output_bytes),
            stderr=decode_process_output(stderr, self.policy.max_output_bytes),
        )

    async def start_background_command(
        self,
        task_id: str,
        command: str,
        output_path: str,
        timeout_seconds: float = 20.0,
    ) -> SandboxBackgroundCommand:
        decision = self.policy.authorize_process(command)
        if not decision.allowed:
            raise PermissionError(decision.reason)
        output_file = self.policy.resolve_workspace_path(output_path)
        ensure_regular_file(output_file, self.policy.relative_workspace_path(output_file), operation="write")
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_bytes(b"")
        relative_output = self.policy.relative_workspace_path(output_file)
        process = await asyncio.create_subprocess_shell(
            command,
            cwd=str(self.policy.workspace_root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=self._tool_env(),
        )
        handle = SandboxBackgroundCommand(
            task_id=task_id,
            command=command,
            output_path=relative_output,
            started_at=time.time(),
        )
        handle._kill = lambda: terminate_process(process)
        handle._task = asyncio.create_task(
            collect_background_process(
                process=process,
                output_file=output_file,
                handle=handle,
                timeout_seconds=timeout_seconds,
                max_output_bytes=self.policy.max_output_bytes,
            )
        )
        return handle

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
        decision = self.policy.authorize_file_read(path or ".")
        if not decision.allowed:
            raise PermissionError(decision.reason)
        return grep_workspace(
            self.policy,
            pattern=pattern,
            path=path,
            max_results=max_results,
            case_sensitive=case_sensitive,
            glob_pattern=glob_pattern,
            context_before=context_before,
            context_after=context_after,
            file_type=file_type,
            multiline=multiline,
        )

    def glob(
        self,
        pattern: str,
        path: str = ".",
        max_results: int = 100,
    ) -> SandboxGlobResult:
        decision = self.policy.authorize_file_read(path or ".")
        if not decision.allowed:
            raise PermissionError(decision.reason)
        return glob_workspace(
            self.policy,
            pattern=str(pattern or ""),
            path=path,
            max_results=max_results,
        )

    def _tool_env(self) -> dict[str, str]:
        workspace = str(self.policy.workspace_root)
        return {
            "PATH": os.environ.get("PATH", ""),
            "HOME": workspace,
            "PWD": workspace,
            "AGENT_WORKSPACE": workspace,
        }
