from __future__ import annotations


DOCKER_GREP_SCRIPT = """
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

def detect_utf16_without_bom(sample):
    pair_count = len(sample) // 2
    if pair_count < 2:
        return ""
    even_nuls = sum(1 for index in range(0, pair_count * 2, 2) if sample[index] == 0)
    odd_nuls = sum(1 for index in range(1, pair_count * 2, 2) if sample[index] == 0)
    even_ratio = even_nuls / pair_count
    odd_ratio = odd_nuls / pair_count
    if odd_ratio >= 0.25 and even_ratio <= 0.05:
        return "utf-16le-no-bom"
    if even_ratio >= 0.25 and odd_ratio <= 0.05:
        return "utf-16be-no-bom"
    return ""

def detect_encoding(sample):
    if sample.startswith(b"\\xff\\xfe"):
        return "utf-16"
    if sample.startswith(b"\\xfe\\xff"):
        return "utf-16be-bom"
    if sample.startswith(b"\\xef\\xbb\\xbf"):
        return "utf-8-sig"
    utf16 = detect_utf16_without_bom(sample)
    if utf16:
        return utf16
    return "utf-8"

def python_codec(encoding):
    if encoding == "utf-16be-bom":
        return "utf-16"
    if encoding == "utf-16le-no-bom":
        return "utf-16le"
    if encoding == "utf-16be-no-bom":
        return "utf-16be"
    return encoding

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
skip = {
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
max_line_chars = 500
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
        encoding = detect_encoding(sample)
        if encoding == "utf-8" and b"\\x00" in sample:
            continue
        if encoding == "utf-8" and sample:
            control = sum(1 for byte in sample if byte < 32 and byte not in {9, 10, 12, 13})
            if control / len(sample) > 0.10:
                continue
        handle = file_path.open("r", encoding=python_codec(encoding), errors="replace")
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
                    "line": line[:max_line_chars],
                    "is_match": output_index in matching_indexes,
                })
                if len(matches) >= limit:
                    print(json.dumps({"pattern": pattern, "path": root.as_posix(), "matches": matches, "truncated": True}))
                    raise SystemExit(0)
print(json.dumps({"pattern": pattern, "path": root.as_posix(), "matches": matches, "truncated": False}))
"""


DOCKER_GLOB_SCRIPT = """
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
