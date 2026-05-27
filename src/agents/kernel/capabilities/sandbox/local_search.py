from __future__ import annotations

import fnmatch
import re
import time
from pathlib import Path, PurePosixPath

from agents.kernel.governance import SandboxPolicy

from .text import BINARY_SAMPLE_BYTES, decode_text_bytes, detect_text_encoding, looks_like_binary_file
from .types import SandboxGlobResult, SandboxGrepMatch, SandboxGrepResult


GREP_SKIP_DIRECTORIES = frozenset(
    {
        ".bzr",
        ".git",
        ".hg",
        ".jj",
        ".sl",
        ".svn",
        ".venv",
        "__pycache__",
        "node_modules",
    }
)
GREP_MAX_LINE_CHARS = 500


def grep_workspace(
    policy: SandboxPolicy,
    *,
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
    root = policy.resolve_workspace_path(path or ".")
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
    glob_patterns = grep_glob_patterns(glob_pattern)
    matches: list[SandboxGrepMatch] = []
    truncated = False
    for file_path in files:
        if should_skip_file(file_path):
            continue
        if not grep_glob_matches(policy, root, file_path, glob_patterns):
            continue
        if not grep_type_matches(file_path, file_type):
            continue
        lines = list(iter_text_lines(file_path))
        if multiline:
            matching_indexes, span_indexes = multiline_match_indexes(lines, matcher)
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
                        path=policy.relative_workspace_path(file_path),
                        line_number=line_number,
                        line=line[:GREP_MAX_LINE_CHARS],
                        is_match=output_index in matching_indexes,
                    )
                )
                if len(matches) >= limit:
                    truncated = True
                    return SandboxGrepResult(
                        pattern=pattern,
                        path=policy.relative_workspace_path(root),
                        matches=matches,
                        truncated=truncated,
                    )
    return SandboxGrepResult(
        pattern=pattern,
        path=policy.relative_workspace_path(root),
        matches=matches,
        truncated=truncated,
    )


def glob_workspace(
    policy: SandboxPolicy,
    *,
    pattern: str,
    path: str = ".",
    max_results: int = 100,
) -> SandboxGlobResult:
    started = time.time()
    root = policy.resolve_workspace_path(path or ".")
    if not root.is_dir():
        raise NotADirectoryError(str(path))
    limit = max(1, min(int(max_results or 100), 1000))
    filenames = glob_workspace_files(policy, root, pattern, limit=limit)
    return SandboxGlobResult(
        pattern=str(pattern or ""),
        path=policy.relative_workspace_path(root),
        filenames=filenames[:limit],
        duration_ms=int((time.time() - started) * 1000),
        truncated=len(filenames) > limit,
    )


def iter_text_lines(path: Path):
    try:
        data = path.read_bytes()
        if looks_like_binary_file(path, data[:BINARY_SAMPLE_BYTES]):
            return
        encoding = detect_text_encoding(path, data[:BINARY_SAMPLE_BYTES])
        for index, line in enumerate(decode_text_bytes(data, encoding).splitlines(), start=1):
            yield index, line
    except OSError:
        return


def should_skip_file(path: Path) -> bool:
    return any(part in GREP_SKIP_DIRECTORIES for part in path.parts)


def glob_workspace_files(policy: SandboxPolicy, root: Path, pattern: str, *, limit: int) -> list[str]:
    match_root = root
    patterns = expand_glob_braces(str(pattern or "*").strip() or "*")
    raw_pattern = str(pattern or "").strip()
    if raw_pattern and Path(raw_pattern).is_absolute():
        workspace_root = policy.workspace_root.resolve()
        try:
            relative = Path(raw_pattern).relative_to(workspace_root).as_posix()
        except ValueError as exc:
            raise PermissionError("path escapes workspace: %s" % raw_pattern) from exc
        match_root = workspace_root
        patterns = expand_glob_braces(relative or "*")

    matches: list[tuple[float, str]] = []
    for file_path in sorted(item for item in match_root.rglob("*") if item.is_file()):
        try:
            match_path = file_path.relative_to(match_root).as_posix()
        except ValueError:
            continue
        if not any(glob_pattern_matches(rule, match_path) for rule in patterns):
            continue
        try:
            modified = file_path.stat().st_mtime
        except OSError:
            modified = 0.0
        matches.append((modified, policy.relative_workspace_path(file_path)))
    matches.sort(key=lambda item: (item[0], item[1]))
    return [path for _, path in matches[: limit + 1]]


def glob_pattern_matches(pattern: str, path: str) -> bool:
    value = str(path or "").strip("/")
    rule = str(pattern or "*").strip() or "*"
    return PurePosixPath(value).match(rule) or fnmatch.fnmatchcase(value, rule)


def grep_glob_patterns(value: str) -> list[str]:
    patterns: list[str] = []
    for item in str(value or "").strip().split():
        if not item:
            continue
        if "{" in item and "}" in item:
            candidates = [item]
        else:
            candidates = [part.strip() for part in item.split(",") if part.strip()]
        for candidate in candidates:
            patterns.extend(expand_glob_braces(candidate))
    return patterns


def grep_glob_matches(
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
    if any(glob_pattern_matches(rule, candidate) for rule in excludes for candidate in candidates):
        return False
    if not includes:
        return True
    return any(glob_pattern_matches(rule, candidate) for rule in includes for candidate in candidates)


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


def grep_type_matches(file_path: Path, file_type: str) -> bool:
    value = str(file_type or "").strip().lower()
    if not value:
        return True
    suffixes = GREP_TYPE_SUFFIXES.get(value, {"." + value.lstrip(".")})
    return file_path.suffix.lower() in suffixes


def multiline_match_indexes(
    lines: list[tuple[int, str]],
    matcher: re.Pattern,
) -> tuple[set[int], dict[int, tuple[int, int]]]:
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


def expand_glob_braces(pattern: str) -> list[str]:
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
        expanded.extend(expand_glob_braces("%s%s%s" % (prefix, option, suffix)))
    return expanded
