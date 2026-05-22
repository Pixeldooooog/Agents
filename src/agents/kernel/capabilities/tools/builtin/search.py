from __future__ import annotations

from typing import Any

from agents.kernel.capabilities.tools.builtin.read_errors import (
    FILE_NOT_FOUND_CWD_NOTE,
    similar_file_name,
)
from agents.kernel.capabilities.tools.context import ToolRuntimeContext
from agents.kernel.capabilities.tools.registry import ToolExecutionError


DEFAULT_GREP_HEAD_LIMIT = 250

GREP_SCHEMA = {
    "type": "object",
    "properties": {
        "pattern": {"type": "string", "description": "Regular expression to search for."},
        "path": {"type": "string", "description": "Workspace-relative file or directory path."},
        "glob": {"type": "string", "description": "Glob pattern to filter searched files, for example '*.py'."},
        "max_results": {"type": "integer", "minimum": 1, "maximum": 1000},
        "head_limit": {"type": "integer", "minimum": 0},
        "offset": {"type": "integer", "minimum": 0},
        "context": {"type": "integer", "minimum": 0},
        "-A": {"type": "integer", "minimum": 0},
        "-B": {"type": "integer", "minimum": 0},
        "-C": {"type": "integer", "minimum": 0},
        "-n": {"type": "boolean"},
        "-i": {"type": "boolean"},
        "type": {"type": "string", "description": "File type filter, similar to ripgrep --type, for example 'py'."},
        "multiline": {"type": "boolean", "description": "Enable multiline regex mode where '.' can match newlines."},
        "case_sensitive": {"type": "boolean"},
        "output_mode": {"type": "string", "enum": ["files_with_matches", "content", "count"]},
    },
    "required": ["pattern"],
}


GLOB_SCHEMA = {
    "type": "object",
    "properties": {
        "pattern": {"type": "string", "description": "Glob pattern to match files against."},
        "path": {
            "type": "string",
            "description": "Workspace-relative directory to search. Defaults to workspace root.",
        },
        "max_results": {"type": "integer", "minimum": 1, "maximum": 1000},
    },
    "required": ["pattern"],
}


def grep(
    runtime_context: ToolRuntimeContext,
    pattern: str,
    path: str = ".",
    max_results: int = 1000,
    case_sensitive: bool = True,
    output_mode: str = "files_with_matches",
    glob: str = "",
    head_limit: int | None = None,
    offset: int = 0,
    **options,
) -> dict[str, Any]:
    _validate_search_path(runtime_context, path or ".", require_directory=False, label="Path")
    if bool(options.get("-i", False)):
        case_sensitive = False
    context_before, context_after = _grep_context_window(options)
    show_line_numbers = bool(options.get("-n", True))
    file_type = str(options.get("type") or "")
    multiline = bool(options.get("multiline", False))
    result = runtime_context.sandbox_client.grep(
        pattern=pattern,
        path=path or ".",
        max_results=_sandbox_grep_limit(max_results=max_results, head_limit=head_limit, offset=offset),
        case_sensitive=case_sensitive,
        glob_pattern=glob,
        context_before=context_before,
        context_after=context_after,
        file_type=file_type,
        multiline=multiline,
    ).to_dict()
    result["glob"] = str(glob or "")
    result["type"] = file_type
    result["multiline"] = multiline
    return _grep_payload(
        result,
        output_mode,
        head_limit=head_limit,
        offset=offset,
        show_line_numbers=show_line_numbers,
    )


def glob(
    runtime_context: ToolRuntimeContext,
    pattern: str,
    path: str = ".",
    max_results: int = 100,
) -> dict[str, Any]:
    _validate_search_path(runtime_context, path or ".", require_directory=True, label="Directory")
    return runtime_context.sandbox_client.glob(
        pattern=pattern,
        path=path or ".",
        max_results=max_results,
    ).to_dict()


def format_glob_result(result: Any) -> str:
    payload = dict(result or {}) if isinstance(result, dict) else {}
    filenames = [str(item) for item in payload.get("filenames") or []]
    if not filenames:
        return "No files found"
    lines = list(filenames)
    if bool(payload.get("truncated")):
        lines.append("(Results are truncated. Consider using a more specific path or pattern.)")
    return "\n".join(lines)


def format_grep_result(result: Any) -> str:
    payload = dict(result or {}) if isinstance(result, dict) else {}
    mode = str(payload.get("mode") or "files_with_matches")
    if mode == "content":
        content = str(payload.get("content") or "")
        output = content or "No matches found"
        limit_info = _format_grep_limit_info(payload)
        if limit_info:
            output = "%s\n\n[Showing results with pagination = %s]" % (output, limit_info)
        if bool(payload.get("truncated")):
            output = "%s\n\n[Results are truncated. Use a narrower path or pattern.]" % output
        return output
    if mode == "count":
        content = str(payload.get("content") or "") or "No matches found"
        matches = int(payload.get("numMatches") or 0)
        files = int(payload.get("numFiles") or 0)
        suffix = "."
        limit_info = _format_grep_limit_info(payload)
        if limit_info:
            suffix = ". with pagination = %s" % limit_info
        return "%s\n\nFound %d total %s across %d %s%s" % (
            content,
            matches,
            "occurrence" if matches == 1 else "occurrences",
            files,
            "file" if files == 1 else "files",
            suffix,
        )
    filenames = [str(item) for item in payload.get("filenames") or []]
    if not filenames:
        return "No files found"
    limit_info = _format_grep_limit_info(payload)
    return "Found %d %s%s\n%s" % (
        len(filenames),
        "file" if len(filenames) == 1 else "files",
        " %s" % limit_info if limit_info else "",
        "\n".join(filenames),
    )


def _grep_payload(
    result: dict[str, Any],
    output_mode: str,
    *,
    head_limit: int | None = None,
    offset: int = 0,
    show_line_numbers: bool = True,
) -> dict[str, Any]:
    matches = [dict(item) for item in result.get("matches") or [] if isinstance(item, dict)]
    match_rows = [item for item in matches if bool(item.get("is_match", True))]
    filenames = _unique_match_paths(match_rows)
    mode = str(output_mode or "files_with_matches")
    if mode not in {"files_with_matches", "content", "count"}:
        mode = "files_with_matches"
    payload = {
        **result,
        "mode": mode,
        "filenames": filenames,
        "numFiles": len(filenames),
        "numMatches": len(match_rows),
    }
    if mode == "content":
        selected, applied_limit = _apply_grep_head_limit(matches, head_limit=head_limit, offset=offset)
        payload["content"] = "\n".join(
            _format_grep_match(item, show_line_numbers=show_line_numbers) for item in selected
        )
        payload["numLines"] = len(selected)
        _apply_grep_limit_metadata(payload, applied_limit=applied_limit, offset=offset)
    elif mode == "count":
        counts: dict[str, int] = {}
        for item in match_rows:
            path = str(item.get("path") or "")
            if path:
                counts[path] = counts.get(path, 0) + 1
        rows = list(counts.items())
        selected_counts, applied_limit = _apply_grep_head_limit(rows, head_limit=head_limit, offset=offset)
        payload["content"] = "\n".join("%s:%d" % (path, count) for path, count in selected_counts)
        payload["filenames"] = [path for path, _ in selected_counts]
        payload["numFiles"] = len(selected_counts)
        payload["numMatches"] = sum(count for _, count in selected_counts)
        _apply_grep_limit_metadata(payload, applied_limit=applied_limit, offset=offset)
    else:
        selected_filenames, applied_limit = _apply_grep_head_limit(filenames, head_limit=head_limit, offset=offset)
        payload["filenames"] = selected_filenames
        payload["numFiles"] = len(selected_filenames)
        _apply_grep_limit_metadata(payload, applied_limit=applied_limit, offset=offset)
    return payload


def _unique_match_paths(matches: list[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    filenames: list[str] = []
    for item in matches:
        path = str(item.get("path") or "")
        if not path or path in seen:
            continue
        seen.add(path)
        filenames.append(path)
    return filenames


def _validate_search_path(
    context: ToolRuntimeContext,
    path: str,
    *,
    require_directory: bool,
    label: str,
) -> None:
    resolved = context.sandbox.resolve_workspace_path(path)
    if not resolved.exists():
        message = _missing_search_path_message(context, path, label=label)
        raise ToolExecutionError(
            message,
            raw={"error": message, "path": path, "reason": "path_not_found"},
        )
    if require_directory and not resolved.is_dir():
        message = "Path is not a directory: %s" % path
        raise ToolExecutionError(
            message,
            raw={"error": message, "path": path, "reason": "path_not_directory"},
        )


def _missing_search_path_message(context: ToolRuntimeContext, path: str, *, label: str) -> str:
    cwd = str(context.workspace.path or context.workspace.root or ".")
    message = "%s does not exist: %s. %s %s." % (label, path, FILE_NOT_FOUND_CWD_NOTE, cwd)
    suggestion = similar_file_name(context, path)
    if suggestion:
        message += " Did you mean %s?" % suggestion
    return message


def _format_grep_match(match: dict[str, Any], *, show_line_numbers: bool = True) -> str:
    path = str(match.get("path") or "")
    line_number = int(match.get("line_number") or 0)
    line = str(match.get("line") or "")
    separator = ":" if bool(match.get("is_match", True)) else "-"
    if show_line_numbers and line_number:
        return "%s%s%d%s%s" % (path, separator, line_number, separator, line)
    return "%s%s%s" % (path, separator, line)


def _grep_context_window(options: dict[str, Any]) -> tuple[int, int]:
    context = _optional_nonnegative_int(options.get("context"))
    if context is None:
        context = _optional_nonnegative_int(options.get("-C"))
    if context is not None:
        return context, context
    return _nonnegative_int(options.get("-B")), _nonnegative_int(options.get("-A"))


def _sandbox_grep_limit(*, max_results: int, head_limit: int | None, offset: int) -> int:
    explicit_limit = _optional_nonnegative_int(head_limit)
    if explicit_limit == 0:
        return max(1, min(int(max_results or 1000), 1000))
    requested = (_nonnegative_int(offset) + (explicit_limit or DEFAULT_GREP_HEAD_LIMIT) + 1)
    return max(1, min(max(int(max_results or 1000), requested), 1000))


def _apply_grep_head_limit(items, *, head_limit: int | None, offset: int):
    start = _nonnegative_int(offset)
    explicit_limit = _optional_nonnegative_int(head_limit)
    if explicit_limit == 0:
        return list(items)[start:], None
    effective_limit = explicit_limit if explicit_limit is not None else DEFAULT_GREP_HEAD_LIMIT
    values = list(items)
    selected = values[start : start + effective_limit]
    applied_limit = effective_limit if len(values) - start > effective_limit else None
    return selected, applied_limit


def _apply_grep_limit_metadata(payload: dict[str, Any], *, applied_limit: int | None, offset: int) -> None:
    if applied_limit is not None:
        payload["appliedLimit"] = applied_limit
    clean_offset = _nonnegative_int(offset)
    if clean_offset > 0:
        payload["appliedOffset"] = clean_offset


def _format_grep_limit_info(payload: dict[str, Any]) -> str:
    parts: list[str] = []
    if payload.get("appliedLimit") is not None:
        parts.append("limit: %d" % int(payload.get("appliedLimit") or 0))
    if payload.get("appliedOffset"):
        parts.append("offset: %d" % int(payload.get("appliedOffset") or 0))
    return ", ".join(parts)


def _optional_nonnegative_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return max(0, int(value))


def _nonnegative_int(value: Any) -> int:
    parsed = _optional_nonnegative_int(value)
    return 0 if parsed is None else parsed
