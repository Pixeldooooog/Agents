from __future__ import annotations

import asyncio
import fnmatch
import os
import re
import shutil
import stat
import time
import uuid
from pathlib import Path, PurePosixPath

from agents.kernel.context.workspace import WorkspaceContext
from agents.kernel.governance import SandboxPolicy

from .text import (
    BINARY_SAMPLE_BYTES,
    DEFAULT_TEXT_READ_MAX_BYTES,
    decode_text_bytes,
    detect_line_endings,
    detect_text_encoding,
    looks_like_binary_file,
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
    SandboxGrepMatch,
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
    ) -> SandboxFileRead:
        decision = self.policy.authorize_file_read(path)
        if not decision.allowed:
            raise PermissionError(decision.reason)
        resolved = self.policy.resolve_workspace_path(path)
        relative = self.policy.relative_workspace_path(resolved)
        _ensure_regular_file(resolved, relative, operation="read")
        if not resolved.is_file():
            raise FileNotFoundError(str(path))
        byte_limit = normalize_text_read_max_bytes(max_bytes)
        line_offset = max(0, int(offset or 1) - 1)
        line_limit = _optional_positive_int(limit)
        range_requested = line_offset > 0 or line_limit is not None
        with resolved.open("rb") as handle:
            sample = handle.read(BINARY_SAMPLE_BYTES)
        encoding = detect_text_encoding(resolved, sample)
        size = resolved.stat().st_size
        if line_limit is None and size > byte_limit:
            raise ValueError(text_file_too_large_message(size, byte_limit))
        if range_requested:
            content = _read_text_line_range(
                resolved,
                encoding=encoding,
                line_offset=line_offset,
                line_limit=line_limit,
            )
            total_lines = _count_text_lines(resolved, encoding)
            data = content.encode(_write_encoding(public_encoding_name(encoding)), errors="replace")
            byte_count = len(data)
            truncated = line_offset + _line_count(content) < total_lines
            num_lines = _line_count(content)
        else:
            with resolved.open("rb") as handle:
                data = handle.read(byte_limit)
            content = decode_text_bytes(data, encoding)
            truncated = size > byte_limit
            num_lines = _line_count(content)
            total_lines = num_lines
            if not truncated:
                total_lines = _count_text_lines(resolved, encoding)
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
        _ensure_regular_file(resolved, relative, operation="write")
        resolved.parent.mkdir(parents=True, exist_ok=True)
        text = str(content)
        write_encoding = _write_encoding(encoding)
        resolved.write_text(text, encoding=write_encoding)
        return SandboxFileWrite(
            path=relative,
            bytes=resolved.stat().st_size,
            encoding=public_encoding_name(write_encoding),
        )

    def delete_path(self, path: str, recursive: bool = False) -> dict:
        decision = self.policy.authorize_file_write(path)
        if not decision.allowed:
            raise PermissionError(decision.reason)
        resolved = self.policy.resolve_workspace_path(path)
        relative = self.policy.relative_workspace_path(resolved)
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
        source = self.policy.resolve_workspace_path(source_path)
        destination = self.policy.resolve_workspace_path(destination_path)
        source_relative = self.policy.relative_workspace_path(source)
        destination_relative = self.policy.relative_workspace_path(destination)
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
        return SandboxCommandResult(
            command=command,
            exit_code=int(process.returncode or 0),
            stdout=_decode(stdout, self.policy.max_output_bytes),
            stderr=_decode(stderr, self.policy.max_output_bytes),
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
        _ensure_regular_file(output_file, self.policy.relative_workspace_path(output_file), operation="write")
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
        handle._kill = lambda: _terminate_process(process)
        handle._task = asyncio.create_task(
            _collect_background_process(
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
        root = self.policy.resolve_workspace_path(path or ".")
        flags = 0 if case_sensitive else re.IGNORECASE
        if multiline:
            flags |= re.DOTALL | re.MULTILINE
        try:
            matcher = re.compile(pattern, flags)
        except re.error as exc:
            raise ValueError("invalid regex pattern: %s" % exc) from exc
        limit = max(1, min(int(max_results or 100), 1000))
        before = max(0, int(context_before or 0))
        after = max(0, int(context_after or 0))
        files = [root] if root.is_file() else sorted(item for item in root.rglob("*") if item.is_file())
        glob_patterns = _grep_glob_patterns(glob_pattern)
        matches: list[SandboxGrepMatch] = []
        truncated = False
        for file_path in files:
            if _should_skip_file(file_path):
                continue
            if not _grep_glob_matches(self.policy, root, file_path, glob_patterns):
                continue
            if not _grep_type_matches(file_path, file_type):
                continue
            lines = list(_iter_text_lines(file_path))
            if multiline:
                matching_indexes, span_indexes = _multiline_match_indexes(lines, matcher)
            else:
                matching_indexes = {index for index, (_, line) in enumerate(lines) if matcher.search(line)}
                span_indexes = {index: (index, index) for index in matching_indexes}
            emitted_indexes: set[int] = set()
            for index in sorted(matching_indexes):
                span_start, span_end = span_indexes.get(index, (index, index))
                start = max(0, span_start - before)
                end = min(len(lines), span_end + after + 1)
                for output_index in range(start, end):
                    if output_index in emitted_indexes:
                        continue
                    emitted_indexes.add(output_index)
                    line_number, line = lines[output_index]
                    matches.append(
                        SandboxGrepMatch(
                            path=self.policy.relative_workspace_path(file_path),
                            line_number=line_number,
                            line=line[:1000],
                            is_match=output_index in matching_indexes,
                        )
                    )
                    if len(matches) >= limit:
                        truncated = True
                        return SandboxGrepResult(
                            pattern=pattern,
                            path=self.policy.relative_workspace_path(root),
                            matches=matches,
                            truncated=truncated,
                        )
        return SandboxGrepResult(
            pattern=pattern,
            path=self.policy.relative_workspace_path(root),
            matches=matches,
            truncated=truncated,
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
        started = time.time()
        root = self.policy.resolve_workspace_path(path or ".")
        if not root.is_dir():
            raise NotADirectoryError(str(path))
        limit = max(1, min(int(max_results or 100), 1000))
        filenames = _glob_workspace_files(self.policy, root, pattern, limit=limit)
        return SandboxGlobResult(
            pattern=str(pattern or ""),
            path=self.policy.relative_workspace_path(root),
            filenames=filenames[:limit],
            duration_ms=int((time.time() - started) * 1000),
            truncated=len(filenames) > limit,
        )

    def _tool_env(self) -> dict[str, str]:
        workspace = str(self.policy.workspace_root)
        return {
            "PATH": os.environ.get("PATH", ""),
            "HOME": workspace,
            "PWD": workspace,
            "AGENT_WORKSPACE": workspace,
        }


def _decode(value: bytes, max_bytes: int) -> str:
    truncated = value[: max(1, max_bytes)]
    suffix = "\n[truncated]" if len(value) > len(truncated) else ""
    return truncated.decode("utf-8", errors="replace") + suffix


def _iter_text_lines(path: Path):
    try:
        data = path.read_bytes()
        if looks_like_binary_file(path, data[:BINARY_SAMPLE_BYTES]):
            return
        encoding = detect_text_encoding(path, data[:BINARY_SAMPLE_BYTES])
        for index, line in enumerate(decode_text_bytes(data, encoding).splitlines(), start=1):
            yield index, line
    except OSError:
        return


def _should_skip_file(path: Path) -> bool:
    return any(part in {".git", "__pycache__", ".venv", "node_modules"} for part in path.parts)


def _ensure_regular_file(path: Path, display_path: str, *, operation: str) -> None:
    if not path.exists() and not path.is_symlink():
        return
    if path.is_file():
        return
    if path.is_dir():
        raise IsADirectoryError("refusing to %s directory: %s" % (operation, display_path))
    special_kind = _special_file_kind(path) or "non-regular file"
    raise ValueError("refusing to %s special file (%s): %s" % (operation, special_kind, display_path))


def _special_file_kind(path: Path) -> str | None:
    try:
        mode = path.lstat().st_mode
    except OSError:
        return None
    if stat.S_ISFIFO(mode):
        return "fifo"
    if stat.S_ISSOCK(mode):
        return "socket"
    if stat.S_ISCHR(mode):
        return "character device"
    if stat.S_ISBLK(mode):
        return "block device"
    return None


def _write_encoding(encoding: str) -> str:
    normalized = str(encoding or "utf-8").lower().replace("_", "-")
    if normalized in {"utf-16", "utf-16le", "utf-16-le"}:
        return "utf-16"
    if normalized in {"utf-8-sig", "utf8-sig"}:
        return "utf-8-sig"
    return "utf-8"


def _optional_positive_int(value: int | None) -> int | None:
    if value is None or value == "":
        return None
    return max(1, int(value))


def _read_text_line_range(path: Path, *, encoding: str, line_offset: int, line_limit: int | None) -> str:
    selected: list[str] = []
    with path.open("r", encoding=encoding, errors="replace", newline="") as handle:
        for index, line in enumerate(handle):
            if index < line_offset:
                continue
            if line_limit is not None and len(selected) >= line_limit:
                break
            selected.append(line)
    return "".join(selected)


def _count_text_lines(path: Path, encoding: str) -> int:
    count = 0
    with path.open("r", encoding=encoding, errors="replace", newline="") as handle:
        for count, _ in enumerate(handle, start=1):
            pass
    return count


def _line_count(content: str) -> int:
    if not content:
        return 0
    return len(content.splitlines())


def _glob_workspace_files(policy: SandboxPolicy, root: Path, pattern: str, *, limit: int) -> list[str]:
    match_root = root
    patterns = _expand_glob_braces(str(pattern or "*").strip() or "*")
    raw_pattern = str(pattern or "").strip()
    if raw_pattern and Path(raw_pattern).is_absolute():
        workspace_root = policy.workspace_root.resolve()
        try:
            relative = Path(raw_pattern).relative_to(workspace_root).as_posix()
        except ValueError as exc:
            raise PermissionError("path escapes workspace: %s" % raw_pattern) from exc
        match_root = workspace_root
        patterns = _expand_glob_braces(relative or "*")

    matches: list[tuple[float, str]] = []
    for file_path in sorted(item for item in match_root.rglob("*") if item.is_file()):
        try:
            match_path = file_path.relative_to(match_root).as_posix()
        except ValueError:
            continue
        if not any(_glob_pattern_matches(rule, match_path) for rule in patterns):
            continue
        try:
            modified = file_path.stat().st_mtime
        except OSError:
            modified = 0.0
        matches.append((modified, policy.relative_workspace_path(file_path)))
    matches.sort(key=lambda item: (item[0], item[1]))
    return [path for _, path in matches[: limit + 1]]


def _glob_pattern_matches(pattern: str, path: str) -> bool:
    value = str(path or "").strip("/")
    rule = str(pattern or "*").strip() or "*"
    return PurePosixPath(value).match(rule) or fnmatch.fnmatchcase(value, rule)


def _grep_glob_patterns(value: str) -> list[str]:
    patterns: list[str] = []
    for item in str(value or "").strip().split():
        if not item:
            continue
        if "{" in item and "}" in item:
            candidates = [item]
        else:
            candidates = [part.strip() for part in item.split(",") if part.strip()]
        for candidate in candidates:
            patterns.extend(_expand_glob_braces(candidate))
    return patterns


def _grep_glob_matches(
    policy: SandboxPolicy,
    root: Path,
    file_path: Path,
    patterns: list[str],
) -> bool:
    if not patterns:
        return True
    match_root = root if root.is_dir() else root.parent
    candidates = [policy.relative_workspace_path(file_path)]
    try:
        candidates.append(file_path.relative_to(match_root).as_posix())
    except ValueError:
        pass
    includes = [rule for rule in patterns if not rule.startswith("!")]
    excludes = [rule[1:] for rule in patterns if rule.startswith("!") and rule[1:]]
    if any(_glob_pattern_matches(rule, candidate) for rule in excludes for candidate in candidates):
        return False
    if not includes:
        return True
    return any(_glob_pattern_matches(rule, candidate) for rule in includes for candidate in candidates)


GREP_TYPE_SUFFIXES = {
    "bash": {".bash", ".sh", ".zsh"},
    "c": {".c", ".h"},
    "cpp": {".cc", ".cpp", ".cxx", ".hh", ".hpp", ".hxx"},
    "cs": {".cs"},
    "csharp": {".cs"},
    "css": {".css"},
    "go": {".go"},
    "html": {".htm", ".html"},
    "java": {".java"},
    "js": {".cjs", ".js", ".jsx", ".mjs"},
    "json": {".json", ".jsonc"},
    "jsx": {".jsx"},
    "kt": {".kt", ".kts"},
    "kotlin": {".kt", ".kts"},
    "md": {".md", ".markdown"},
    "php": {".php"},
    "py": {".py", ".pyi"},
    "python": {".py", ".pyi"},
    "rb": {".rb"},
    "ruby": {".rb"},
    "rs": {".rs"},
    "rust": {".rs"},
    "scala": {".scala", ".sc"},
    "sh": {".bash", ".sh", ".zsh"},
    "sql": {".sql"},
    "swift": {".swift"},
    "toml": {".toml"},
    "ts": {".ts", ".tsx"},
    "tsx": {".tsx"},
    "xml": {".xml"},
    "yaml": {".yaml", ".yml"},
    "yml": {".yaml", ".yml"},
}


def _grep_type_matches(file_path: Path, file_type: str) -> bool:
    value = str(file_type or "").strip().lower()
    if not value:
        return True
    suffixes = GREP_TYPE_SUFFIXES.get(value, {"." + value.lstrip(".")})
    return file_path.suffix.lower() in suffixes


def _multiline_match_indexes(lines: list[tuple[int, str]], matcher: re.Pattern) -> tuple[set[int], dict[int, tuple[int, int]]]:
    if not lines:
        return set(), {}
    content = "\n".join(line for _, line in lines)
    starts: set[int] = set()
    spans: dict[int, tuple[int, int]] = {}
    for match in matcher.finditer(content):
        start_index = content.count("\n", 0, match.start())
        end_index = content.count("\n", 0, match.end())
        if match.end() > match.start() and match.end() <= len(content) and content[match.end() - 1] == "\n":
            end_index = max(start_index, end_index - 1)
        starts.add(start_index)
        spans[start_index] = (start_index, min(len(lines) - 1, end_index))
    return starts, spans


def _expand_glob_braces(pattern: str) -> list[str]:
    start = pattern.find("{")
    if start < 0:
        return [pattern]
    end = pattern.find("}", start + 1)
    if end < 0:
        return [pattern]
    prefix = pattern[:start]
    suffix = pattern[end + 1 :]
    options = [item for item in pattern[start + 1 : end].split(",") if item]
    if not options:
        return [pattern]
    expanded: list[str] = []
    for option in options:
        expanded.extend(_expand_glob_braces("%s%s%s" % (prefix, option, suffix)))
    return expanded


def _terminate_process(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    try:
        process.terminate()
    except ProcessLookupError:
        return


async def _collect_background_process(
    *,
    process: asyncio.subprocess.Process,
    output_file: Path,
    handle: SandboxBackgroundCommand,
    timeout_seconds: float,
    max_output_bytes: int,
) -> None:
    async def read_output() -> None:
        stream = process.stdout
        if stream is None:
            return
        with output_file.open("ab") as file_handle:
            while True:
                chunk = await stream.read(4096)
                if not chunk:
                    break
                file_handle.write(chunk)
                file_handle.flush()
                handle.output_bytes += len(chunk)

    reader = asyncio.create_task(read_output())
    try:
        await asyncio.wait_for(process.wait(), timeout=float(timeout_seconds or 20.0))
    except asyncio.TimeoutError:
        handle.timed_out = True
        handle.status = "timed_out"
        _terminate_process(process)
        try:
            await asyncio.wait_for(process.wait(), timeout=2.0)
        except asyncio.TimeoutError:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            await process.wait()
    except asyncio.CancelledError:
        handle.status = "killed"
        _terminate_process(process)
        await process.wait()
        raise
    except Exception as exc:  # noqa: BLE001 - background command errors are model-visible state.
        handle.status = "error"
        handle.error = str(exc)
    finally:
        await asyncio.gather(reader, return_exceptions=True)
        handle.output_bytes = _safe_size(output_file)
        handle.ended_at = time.time()
        if handle.status == "running":
            handle.exit_code = int(process.returncode or 0)
            handle.status = "completed" if handle.exit_code == 0 else "failed"
        elif handle.status in {"timed_out", "killed"}:
            handle.exit_code = int(process.returncode or -1)
        if handle.output_bytes > max_output_bytes:
            pass


def _safe_size(path: Path) -> int:
    try:
        return int(path.stat().st_size)
    except OSError:
        return 0
