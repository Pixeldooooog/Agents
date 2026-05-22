from __future__ import annotations

import difflib
import re
from typing import Any

from agents.kernel.capabilities.tools.context import ToolRuntimeContext
from agents.kernel.capabilities.sandbox.types import SandboxFileRead


MAX_SAFE_TEXT_READ_BYTES = 200000
PRE_READ_REQUIRED_ERROR = "File has not been read yet. Read it first before writing to it."
STALE_FILE_ERROR = "File has been modified since read, either by the user or by a linter. Read it again before attempting to write it."
SPECIAL_FILE_READ_ERROR_PREFIX = "refusing to read special file"


def read_current_file(context: ToolRuntimeContext, path: str) -> SandboxFileRead:
    result = context.sandbox_client.read_text(path, max_bytes=MAX_SAFE_TEXT_READ_BYTES)
    if result.truncated:
        raise ValueError("File is too large to edit safely: %s" % result.path)
    return result


def read_current_text(context: ToolRuntimeContext, path: str) -> tuple[str, str]:
    result = read_current_file(context, path)
    return result.path, result.content


def record_file_read(
    context: ToolRuntimeContext,
    path: str,
    content: str,
    encoding: str = "utf-8",
    write_encoding: str = "",
    *,
    source: str = "write",
    offset: int | None = None,
    limit: int | None = None,
    is_partial_view: bool = False,
) -> None:
    relative_path = _normalize_path(context, path)
    context.file_read_state[relative_path] = {
        "path": relative_path,
        "content": str(content),
        "encoding": str(encoding or "utf-8"),
        "write_encoding": str(write_encoding or ""),
        "timestamp": _mtime(context, relative_path),
        "full_read": True,
        "source": str(source or ""),
        "offset": offset,
        "limit": limit,
        "is_partial_view": bool(is_partial_view),
    }


def unchanged_read_stub(
    context: ToolRuntimeContext,
    path: str,
    *,
    offset: int = 1,
    limit: int | None = None,
) -> dict[str, Any] | None:
    relative_path = _normalize_path(context, path)
    record = context.file_read_state.get(relative_path)
    if not record or record.get("source") != "read":
        return None
    if bool(record.get("is_partial_view")):
        return None
    if int(record.get("offset") or 1) != max(1, int(offset or 1)):
        return None
    if record.get("limit") != limit:
        return None
    if float(record.get("timestamp") or 0.0) != _mtime(context, relative_path):
        return None
    return {
        "type": "file_unchanged",
        "path": relative_path,
        "file": {"filePath": relative_path},
        "deduplicated": True,
    }


def ensure_existing_file_current(
    context: ToolRuntimeContext,
    path: str,
    current_content: str | None = None,
) -> str:
    relative_path = _normalize_path(context, path)
    current = current_content
    if current is None:
        relative_path, current = read_current_text(context, path)
    record = context.file_read_state.get(relative_path)
    if not record or not record.get("full_read"):
        raise ValueError(PRE_READ_REQUIRED_ERROR)
    if str(record.get("content") or "") != str(current):
        raise ValueError(STALE_FILE_ERROR)
    return relative_path


def write_text_safely(context: ToolRuntimeContext, path: str, content: str) -> dict[str, Any]:
    existed = True
    try:
        current_read = read_current_file(context, path)
        relative_path = current_read.path
        current = current_read.content
        encoding = current_read.write_encoding or current_read.encoding
    except FileNotFoundError:
        existed = False
        relative_path = _normalize_path(context, path)
        current = ""
        encoding = "utf-8"
    except ValueError as exc:
        message = str(exc)
        if message.startswith(SPECIAL_FILE_READ_ERROR_PREFIX):
            raise ValueError(message.replace("refusing to read", "refusing to write", 1)) from exc
        raise
    output = normalize_text_write_content(relative_path, content)
    if existed:
        ensure_existing_file_current(context, relative_path, current)
    result = context.sandbox_client.write_text(path, output, encoding=encoding)
    record_file_read(context, result.path, output, encoding=result.encoding, write_encoding=result.write_encoding)
    payload = result.to_dict()
    payload.update(
        {
            "type": "update" if existed else "create",
            "filePath": result.path,
            "content": output,
            "structuredPatch": structured_text_patch(current, output) if existed else [],
            "originalFile": current if existed else None,
        }
    )
    payload["safety"] = {
        "required_prior_read": existed,
        "stale_checked": existed,
        "recorded_read": True,
        "line_endings": _line_ending_style(output),
        "encoding": result.encoding,
    }
    return payload


def structured_text_patch(before: str, after: str) -> list[dict[str, Any]]:
    before_lines = str(before).splitlines()
    after_lines = str(after).splitlines()
    matcher = difflib.SequenceMatcher(a=before_lines, b=after_lines, autojunk=False)
    hunks: list[dict[str, Any]] = []
    for group in matcher.get_grouped_opcodes(n=3):
        if not group:
            continue
        old_start = group[0][1] + 1
        new_start = group[0][3] + 1
        old_lines = group[-1][2] - group[0][1]
        new_lines = group[-1][4] - group[0][3]
        lines: list[str] = []
        for tag, old_a, old_b, new_a, new_b in group:
            if tag == "equal":
                lines.extend(" " + line for line in before_lines[old_a:old_b])
            elif tag == "delete":
                lines.extend("-" + line for line in before_lines[old_a:old_b])
            elif tag == "insert":
                lines.extend("+" + line for line in after_lines[new_a:new_b])
            elif tag == "replace":
                lines.extend("-" + line for line in before_lines[old_a:old_b])
                lines.extend("+" + line for line in after_lines[new_a:new_b])
        hunks.append(
            {
                "oldStart": old_start,
                "oldLines": old_lines,
                "newStart": new_start,
                "newLines": new_lines,
                "lines": lines,
            }
        )
    return hunks


def normalize_text_write_content(path: str, content: str) -> str:
    if _is_markdown_path(path):
        return str(content)
    return strip_trailing_whitespace(content)


def strip_trailing_whitespace(text: str) -> str:
    parts = re.split(r"(\r\n|\n|\r)", str(text))
    output: list[str] = []
    for index, part in enumerate(parts):
        if index % 2 == 0:
            output.append(re.sub(r"\s+$", "", part))
        else:
            output.append(part)
    return "".join(output)


def preserve_existing_line_endings(existing_content: str, new_content: str) -> str:
    if "\r\n" not in existing_content or "\r\n" in new_content:
        return new_content
    return new_content.replace("\r\n", "\n").replace("\n", "\r\n")


def _is_markdown_path(path: str) -> bool:
    normalized = str(path).lower()
    return normalized.endswith(".md") or normalized.endswith(".mdx")


def _normalize_path(context: ToolRuntimeContext, path: str) -> str:
    resolved = context.sandbox.resolve_workspace_path(path)
    return context.sandbox.relative_workspace_path(resolved)


def _mtime(context: ToolRuntimeContext, path: str) -> float:
    try:
        return float(context.sandbox.resolve_workspace_path(path).stat().st_mtime)
    except OSError:
        return 0.0


def _line_ending_style(content: str) -> str:
    if "\r\n" in content:
        return "crlf"
    if "\n" in content:
        return "lf"
    return "none"
