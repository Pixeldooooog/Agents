from __future__ import annotations

import asyncio
import json
import shutil
import shlex
import subprocess
import time
import uuid
from pathlib import Path

from agents.kernel.context.workspace import WorkspaceContext
from agents.kernel.governance import SandboxPolicy

from .text import DEFAULT_TEXT_READ_MAX_BYTES, normalize_text_read_max_bytes, text_file_too_large_message
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


class DockerSandboxProvider:
    name = "docker"

    def acquire(
        self,
        workspace: WorkspaceContext,
        policy: SandboxPolicy,
        profile: SandboxProfile | None = None,
        lease_id: str = "",
        metadata: dict | None = None,
    ) -> "DockerSandboxClient":
        if shutil.which("docker") is None:
            raise RuntimeError("docker CLI is not available")
        active_profile = profile or SandboxProfile(provider=self.name)
        lease = SandboxLease(
            lease_id=lease_id or "docker-%s" % uuid.uuid4().hex,
            provider=self.name,
            workspace=workspace,
            profile=active_profile,
            metadata=dict(metadata or {}),
        )
        return DockerSandboxClient(lease=lease, policy=policy)

    def release(self, client: SandboxClient) -> None:
        return None


class DockerSandboxClient:
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
        byte_limit = normalize_text_read_max_bytes(max_bytes)
        line_offset = max(0, int(offset or 1) - 1)
        line_limit = "" if limit is None else str(max(1, int(limit)))
        if require_full and limit is None and resolved.is_file():
            size = resolved.stat().st_size
            if size > byte_limit:
                raise ValueError(text_file_too_large_message(size, byte_limit))
        script = """
import json
import pathlib
import sys
path = pathlib.Path(sys.argv[1])
byte_limit = int(sys.argv[2])
line_offset = int(sys.argv[3])
line_limit = None if sys.argv[4] == "" else int(sys.argv[4])
require_full = sys.argv[5] == "1"

def format_file_size(size_in_bytes):
    size = float(max(0, int(size_in_bytes)))
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            if unit == "B":
                return "%d B" % int(size)
            return "%.1f %s" % (size, unit)
        size /= 1024

def too_large_message(size_in_bytes, max_size_bytes):
    return (
        "File content (%s) exceeds maximum allowed size (%s). "
        "Use offset and limit parameters to read specific portions of the file, "
        "or search for specific content instead of reading the whole file."
    ) % (format_file_size(size_in_bytes), format_file_size(max_size_bytes))

if not path.is_file():
    raise FileNotFoundError(sys.argv[1])
data = path.read_bytes()
sample = data[:8192]
binary_exts = {".7z",".avi",".bin",".bmp",".class",".dmg",".doc",".docx",".exe",".gif",".gz",".ico",".jar",".jpeg",".jpg",".mov",".mp3",".mp4",".o",".pdf",".png",".pyc",".so",".tar",".wasm",".webp",".xls",".xlsx",".zip"}
if sample.startswith(b"\\xff\\xfe") or sample.startswith(b"\\xfe\\xff"):
    encoding = "utf-16"
    public_encoding = "utf-16le"
elif sample.startswith(b"\\xef\\xbb\\xbf"):
    encoding = "utf-8-sig"
    public_encoding = "utf-8-sig"
else:
    encoding = "utf-8"
    public_encoding = "utf-8"
if encoding == "utf-8" and (path.suffix.lower() in binary_exts or b"\\x00" in sample):
    raise ValueError("This text tool cannot read binary files. The file appears to be a binary file. Use an appropriate binary analysis tool instead.")
if encoding == "utf-8" and sample:
    control = sum(1 for byte in sample if byte < 32 and byte not in {9, 10, 12, 13})
    if control / len(sample) > 0.10:
        raise ValueError("This text tool cannot read binary files. The file appears to be a binary file. Use an appropriate binary analysis tool instead.")
range_requested = line_offset > 0 or line_limit is not None
if require_full and line_limit is None and len(data) > byte_limit:
    raise ValueError(too_large_message(len(data), byte_limit))
if range_requested:
    lines = data.decode(encoding, errors="replace").splitlines(keepends=True)
    selected = lines[line_offset:] if line_limit is None else lines[line_offset:line_offset + line_limit]
    content = "".join(selected)
    total_lines = len(lines)
    num_lines = len(content.splitlines()) if content else 0
    read_bytes = len(content.encode(encoding, errors="replace"))
    truncated = line_offset + num_lines < total_lines
else:
    content = data[:byte_limit].decode(encoding, errors="replace")
    total_lines = len(data.decode(encoding, errors="replace").splitlines()) if len(data) <= byte_limit else len(content.splitlines())
    num_lines = len(content.splitlines()) if content else 0
    read_bytes = min(len(data), byte_limit)
    truncated = len(data) > byte_limit
crlf = content.count("\\r\\n")
lf = content.count("\\n") - crlf
line_endings = "crlf" if crlf > lf else "lf" if crlf or lf else "none"
sys.stdout.write(json.dumps({
    "path": sys.argv[1],
    "content": content,
    "bytes": read_bytes,
    "truncated": truncated,
    "encoding": public_encoding,
    "line_endings": line_endings,
    "startLine": line_offset + 1,
    "numLines": num_lines,
    "totalLines": total_lines,
    "isPartialView": range_requested or truncated,
}))
"""
        payload = self._run_python_json(
            script,
            [relative, str(byte_limit), str(line_offset), line_limit, "1" if require_full else "0"],
        )
        return SandboxFileRead(
            path=str(payload["path"]),
            content=str(payload["content"]),
            bytes=int(payload["bytes"]),
            truncated=bool(payload["truncated"]),
            encoding=str(payload.get("encoding") or "utf-8"),
            line_endings=str(payload.get("line_endings") or "none"),
            start_line=int(payload.get("startLine") or 1),
            num_lines=int(payload.get("numLines") or 0),
            total_lines=int(payload.get("totalLines") or 0),
            is_partial_view=bool(payload.get("isPartialView", False)),
        )

    def list_dir(self, path: str = ".") -> SandboxDirectoryListing:
        decision = self.policy.authorize_file_read(path or ".")
        if not decision.allowed:
            raise PermissionError(decision.reason)
        relative = self.policy.relative_workspace_path(self.policy.resolve_workspace_path(path or "."))
        script = """
import json
import pathlib
import sys
path = pathlib.Path(sys.argv[1])
if not path.is_dir():
    raise NotADirectoryError(sys.argv[1])
entries = [
    {"name": child.name, "path": child.as_posix(), "type": "directory" if child.is_dir() else "file"}
    for child in sorted(path.iterdir(), key=lambda item: item.name)
]
sys.stdout.write(json.dumps({"path": path.as_posix(), "entries": entries}))
"""
        payload = self._run_python_json(script, [relative])
        return SandboxDirectoryListing(
            path=str(payload["path"]),
            entries=[
                SandboxDirectoryEntry(name=str(item["name"]), path=str(item["path"]), type=str(item["type"]))
                for item in payload["entries"]
            ],
        )

    def write_text(self, path: str, content: str, encoding: str = "utf-8") -> SandboxFileWrite:
        decision = self.policy.authorize_file_write(path)
        if not decision.allowed:
            raise PermissionError(decision.reason)
        relative = self.policy.relative_workspace_path(self.policy.resolve_workspace_path(path))
        target = shlex.quote(relative)
        command = "if { test -e %s || test -L %s; } && ! test -f %s; then echo %s >&2; exit 1; fi; mkdir -p -- %s && cat > %s" % (
            target,
            target,
            target,
            shlex.quote("refusing to write non-regular file: %s" % relative),
            shlex.quote(_posix_parent(relative)),
            target,
        )
        result = subprocess.run(
            self._docker_run_args(["sh", "-lc", command]),
            input=str(content).encode(_write_encoding(encoding)),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.decode("utf-8", errors="replace") or "docker write failed")
        return SandboxFileWrite(path=relative, bytes=len(str(content).encode(_write_encoding(encoding))), encoding=_public_encoding_name(encoding))

    def delete_path(self, path: str, recursive: bool = False) -> dict:
        decision = self.policy.authorize_file_write(path)
        if not decision.allowed:
            raise PermissionError(decision.reason)
        relative = self.policy.relative_workspace_path(self.policy.resolve_workspace_path(path))
        if relative == ".":
            raise PermissionError("refusing to delete workspace root")
        script = """
import json
import pathlib
import shutil
import sys
path = pathlib.Path(sys.argv[1])
recursive = sys.argv[2] == "1"
if not path.exists() and not path.is_symlink():
    print(json.dumps({"path": path.as_posix(), "deleted": False, "reason": "not_found"}))
    raise SystemExit(0)
kind = "directory" if path.is_dir() and not path.is_symlink() else "file"
if kind == "directory":
    if not recursive:
        raise IsADirectoryError("directory delete requires recursive=true: %s" % path.as_posix())
    shutil.rmtree(path)
else:
    path.unlink()
print(json.dumps({"path": path.as_posix(), "type": kind, "deleted": True, "recursive": recursive}))
"""
        return self._run_python_json(script, [relative, "1" if recursive else "0"])

    def move_path(self, source_path: str, destination_path: str, overwrite: bool = False) -> dict:
        read_decision = self.policy.authorize_file_read(source_path)
        if not read_decision.allowed:
            raise PermissionError(read_decision.reason)
        write_decision = self.policy.authorize_file_write(destination_path)
        if not write_decision.allowed:
            raise PermissionError(write_decision.reason)
        source = self.policy.relative_workspace_path(self.policy.resolve_workspace_path(source_path))
        destination = self.policy.relative_workspace_path(self.policy.resolve_workspace_path(destination_path))
        if source == "." or destination == ".":
            raise PermissionError("refusing to move workspace root")
        script = """
import json
import pathlib
import shutil
import sys
source = pathlib.Path(sys.argv[1])
destination = pathlib.Path(sys.argv[2])
overwrite = sys.argv[3] == "1"
if not source.exists() and not source.is_symlink():
    raise FileNotFoundError(source.as_posix())
if destination.exists() or destination.is_symlink():
    if not overwrite:
        raise FileExistsError(destination.as_posix())
    if destination.is_dir() and not destination.is_symlink():
        raise IsADirectoryError("refusing to overwrite directory: %s" % destination.as_posix())
    destination.unlink()
destination.parent.mkdir(parents=True, exist_ok=True)
shutil.move(source.as_posix(), destination.as_posix())
print(json.dumps({
    "source_path": source.as_posix(),
    "destination_path": destination.as_posix(),
    "moved": True,
    "overwritten": overwrite,
}))
"""
        return self._run_python_json(script, [source, destination, "1" if overwrite else "0"])

    async def run_command(self, command: str, timeout_seconds: float = 20.0) -> SandboxCommandResult:
        decision = self.policy.authorize_process(command)
        if not decision.allowed:
            raise PermissionError(decision.reason)
        process = await asyncio.create_subprocess_exec(
            *self._docker_run_args(["sh", "-lc", command]),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
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
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_bytes(b"")
        relative_output = self.policy.relative_workspace_path(output_file)
        process = await asyncio.create_subprocess_exec(
            *self._docker_run_args(["sh", "-lc", command]),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
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
        relative = self.policy.relative_workspace_path(self.policy.resolve_workspace_path(path or "."))
        script = """
import fnmatch
import json
import pathlib
import re
import sys

def expand_braces(pattern):
    start = pattern.find("{")
    if start < 0:
        return [pattern]
    end = pattern.find("}", start + 1)
    if end < 0:
        return [pattern]
    prefix = pattern[:start]
    suffix = pattern[end + 1:]
    options = [item for item in pattern[start + 1:end].split(",") if item]
    if not options:
        return [pattern]
    expanded = []
    for option in options:
        expanded.extend(expand_braces(prefix + option + suffix))
    return expanded

def split_glob_patterns(value):
    patterns = []
    for item in str(value or "").strip().split():
        if not item:
            continue
        if "{" in item and "}" in item:
            candidates = [item]
        else:
            candidates = [part.strip() for part in item.split(",") if part.strip()]
        for candidate in candidates:
            patterns.extend(expand_braces(candidate))
    return patterns

def glob_matches(pattern, path):
    value = str(path or "").strip("/")
    rule = str(pattern or "*").strip() or "*"
    return pathlib.PurePosixPath(value).match(rule) or fnmatch.fnmatchcase(value, rule)

def file_matches_globs(root, file_path, patterns):
    if not patterns:
        return True
    match_root = root if root.is_dir() else root.parent
    candidates = [file_path.as_posix()]
    try:
        candidates.append(file_path.relative_to(match_root).as_posix())
    except ValueError:
        pass
    includes = [rule for rule in patterns if not rule.startswith("!")]
    excludes = [rule[1:] for rule in patterns if rule.startswith("!") and rule[1:]]
    if any(glob_matches(rule, candidate) for rule in excludes for candidate in candidates):
        return False
    if not includes:
        return True
    return any(glob_matches(rule, candidate) for rule in includes for candidate in candidates)

TYPE_SUFFIXES = {
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

def file_matches_type(file_path, file_type):
    value = str(file_type or "").strip().lower()
    if not value:
        return True
    suffixes = TYPE_SUFFIXES.get(value, {"." + value.lstrip(".")})
    return file_path.suffix.lower() in suffixes

def multiline_match_indexes(lines, matcher):
    if not lines:
        return set(), {}
    content = "\\n".join(line for _, line in lines)
    starts = set()
    spans = {}
    for match in matcher.finditer(content):
        start_index = content.count("\\n", 0, match.start())
        end_index = content.count("\\n", 0, match.end())
        if match.end() > match.start() and match.end() <= len(content) and content[match.end() - 1] == "\\n":
            end_index = max(start_index, end_index - 1)
        starts.add(start_index)
        spans[start_index] = (start_index, min(len(lines) - 1, end_index))
    return starts, spans

pattern = sys.argv[1]
root = pathlib.Path(sys.argv[2])
limit = max(1, min(int(sys.argv[3]), 1000))
flags = 0 if sys.argv[4] == "1" else re.IGNORECASE
if sys.argv[9] == "1":
    flags |= re.DOTALL | re.MULTILINE
matcher = re.compile(pattern, flags)
glob_patterns = split_glob_patterns(sys.argv[5])
context_before = max(0, int(sys.argv[6]))
context_after = max(0, int(sys.argv[7]))
file_type = sys.argv[8]
multiline = sys.argv[9] == "1"
files = [root] if root.is_file() else sorted(item for item in root.rglob("*") if item.is_file())
matches = []
skip = {".git", "__pycache__", ".venv", "node_modules"}
for file_path in files:
    if any(part in skip for part in file_path.parts):
        continue
    if not file_matches_globs(root, file_path, glob_patterns):
        continue
    if not file_matches_type(file_path, file_type):
        continue
    try:
        if file_path.suffix.lower() in {".7z",".avi",".bin",".bmp",".class",".dmg",".doc",".docx",".exe",".gif",".gz",".ico",".jar",".jpeg",".jpg",".mov",".mp3",".mp4",".o",".pdf",".png",".pyc",".so",".tar",".wasm",".webp",".xls",".xlsx",".zip"}:
            continue
        sample = file_path.read_bytes()[:8192]
        if sample.startswith(b"\\xff\\xfe") or sample.startswith(b"\\xfe\\xff"):
            encoding = "utf-16"
        elif sample.startswith(b"\\xef\\xbb\\xbf"):
            encoding = "utf-8-sig"
        else:
            encoding = "utf-8"
        if encoding == "utf-8" and b"\\x00" in sample:
            continue
        if encoding == "utf-8" and sample:
            control = sum(1 for byte in sample if byte < 32 and byte not in {9, 10, 12, 13})
            if control / len(sample) > 0.10:
                continue
        handle = file_path.open("r", encoding=encoding, errors="replace")
    except OSError:
        continue
    with handle:
        lines = [(index, line.rstrip("\\n")) for index, line in enumerate(handle, start=1)]
        if multiline:
            matching_indexes, span_indexes = multiline_match_indexes(lines, matcher)
        else:
            matching_indexes = {index for index, item in enumerate(lines) if matcher.search(item[1])}
            span_indexes = {index: (index, index) for index in matching_indexes}
        emitted_indexes = set()
        for match_index in sorted(matching_indexes):
            span_start, span_end = span_indexes.get(match_index, (match_index, match_index))
            start = max(0, span_start - context_before)
            end = min(len(lines), span_end + context_after + 1)
            for output_index in range(start, end):
                if output_index in emitted_indexes:
                    continue
                emitted_indexes.add(output_index)
                line_number, line = lines[output_index]
                matches.append({
                    "path": file_path.as_posix(),
                    "line_number": line_number,
                    "line": line[:1000],
                    "is_match": output_index in matching_indexes,
                })
                if len(matches) >= limit:
                    print(json.dumps({"pattern": pattern, "path": root.as_posix(), "matches": matches, "truncated": True}))
                    raise SystemExit(0)
print(json.dumps({"pattern": pattern, "path": root.as_posix(), "matches": matches, "truncated": False}))
"""
        payload = self._run_python_json(
            script,
            [
                pattern,
                relative,
                str(max_results or 100),
                "1" if case_sensitive else "0",
                str(glob_pattern or ""),
                str(max(0, int(context_before or 0))),
                str(max(0, int(context_after or 0))),
                str(file_type or ""),
                "1" if multiline else "0",
            ],
        )
        return SandboxGrepResult(
            pattern=str(payload["pattern"]),
            path=str(payload["path"]),
            matches=[
                SandboxGrepMatch(
                    path=str(item["path"]),
                    line_number=int(item["line_number"]),
                    line=str(item["line"]),
                    is_match=bool(item.get("is_match", True)),
                )
                for item in payload["matches"]
            ],
            truncated=bool(payload["truncated"]),
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
        relative = self.policy.relative_workspace_path(self.policy.resolve_workspace_path(path or "."))
        normalized_pattern = _docker_glob_pattern(pattern, self.policy)
        script = """
import fnmatch
import json
import pathlib
import sys
import time

def expand_braces(pattern):
    start = pattern.find("{")
    if start < 0:
        return [pattern]
    end = pattern.find("}", start + 1)
    if end < 0:
        return [pattern]
    prefix = pattern[:start]
    suffix = pattern[end + 1:]
    options = [item for item in pattern[start + 1:end].split(",") if item]
    if not options:
        return [pattern]
    expanded = []
    for option in options:
        expanded.extend(expand_braces(prefix + option + suffix))
    return expanded

def matches(pattern, path):
    value = str(path).strip("/")
    rule = str(pattern or "*").strip() or "*"
    return pathlib.PurePosixPath(value).match(rule) or fnmatch.fnmatchcase(value, rule)

started = time.time()
root = pathlib.Path(sys.argv[1])
pattern = sys.argv[2]
limit = max(1, min(int(sys.argv[3]), 1000))
if not root.is_dir():
    raise NotADirectoryError(sys.argv[1])
match_root = pathlib.Path(".") if pattern.startswith("/") else root
if pattern.startswith("/"):
    pattern = pattern.lstrip("/")
patterns = expand_braces(pattern or "*")
rows = []
for file_path in sorted(item for item in match_root.rglob("*") if item.is_file()):
    try:
        match_path = file_path.relative_to(match_root).as_posix()
    except ValueError:
        continue
    if not any(matches(rule, match_path) for rule in patterns):
        continue
    try:
        modified = file_path.stat().st_mtime
    except OSError:
        modified = 0
    rows.append((modified, file_path.as_posix()))
rows.sort(key=lambda item: (item[0], item[1]))
selected = [path for _, path in rows[:limit]]
sys.stdout.write(json.dumps({
    "pattern": sys.argv[2],
    "path": root.as_posix(),
    "filenames": selected,
    "durationMs": int((time.time() - started) * 1000),
    "truncated": len(rows) > limit,
}))
"""
        payload = self._run_python_json(script, [relative, normalized_pattern, str(max_results or 100)])
        return SandboxGlobResult(
            pattern=str(payload["pattern"]),
            path=str(payload["path"]),
            filenames=[str(item) for item in payload["filenames"]],
            duration_ms=int(payload.get("durationMs") or 0),
            truncated=bool(payload["truncated"]),
        )

    def _run_python_json(self, script: str, args: list[str]) -> dict:
        result = subprocess.run(
            self._docker_run_args(["python3", "-c", script, *args]),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.decode("utf-8", errors="replace") or "docker command failed")
        return json.loads(result.stdout.decode("utf-8"))

    def _docker_run_args(self, command: list[str]) -> list[str]:
        profile = self.lease.profile
        args = [
            "docker",
            "run",
            "--rm",
            "-i",
            "-v",
            "%s:%s" % (self.policy.workspace_root.resolve(), profile.workdir),
            "-w",
            profile.workdir,
            "--network",
            profile.network_mode if self.policy.allow_network else "none",
        ]
        artifact_host_root = str(self.lease.metadata.get("artifact_host_root") or "")
        artifact_mount_path = str(self.lease.metadata.get("artifact_mount_path") or "/artifacts")
        if artifact_host_root:
            Path(artifact_host_root).mkdir(parents=True, exist_ok=True)
            args.extend(["-v", "%s:%s" % (Path(artifact_host_root).resolve(), artifact_mount_path)])
        if profile.memory:
            args.extend(["--memory", profile.memory])
        if profile.cpus:
            args.extend(["--cpus", profile.cpus])
        args.append(profile.image)
        args.extend(command)
        return args


def _decode(value: bytes, max_bytes: int) -> str:
    truncated = value[: max(1, max_bytes)]
    suffix = "\n[truncated]" if len(value) > len(truncated) else ""
    return truncated.decode("utf-8", errors="replace") + suffix


def _posix_parent(path: str) -> str:
    if "/" not in path:
        return "."
    return path.rsplit("/", 1)[0] or "."


def _write_encoding(encoding: str) -> str:
    normalized = str(encoding or "utf-8").lower().replace("_", "-")
    if normalized in {"utf-16", "utf-16le", "utf-16-le"}:
        return "utf-16"
    if normalized in {"utf-8-sig", "utf8-sig"}:
        return "utf-8-sig"
    return "utf-8"


def _docker_glob_pattern(pattern: str, policy: SandboxPolicy) -> str:
    raw_pattern = str(pattern or "*").strip() or "*"
    if not Path(raw_pattern).is_absolute():
        return raw_pattern
    workspace_root = policy.workspace_root.resolve()
    try:
        relative = Path(raw_pattern).relative_to(workspace_root).as_posix()
    except ValueError as exc:
        raise PermissionError("path escapes workspace: %s" % raw_pattern) from exc
    return "/%s" % relative if relative else "*"


def _public_encoding_name(encoding: str) -> str:
    write_encoding = _write_encoding(encoding)
    if write_encoding == "utf-16":
        return "utf-16le"
    if write_encoding == "utf-8-sig":
        return "utf-8-sig"
    return "utf-8"


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
