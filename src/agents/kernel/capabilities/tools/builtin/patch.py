from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from typing import Any

from agents.kernel.capabilities.tools.context import ToolRuntimeContext
from agents.kernel.capabilities.tools.builtin.file_safety import (
    ensure_existing_file_current,
    normalize_text_write_content,
    preserve_existing_line_endings,
    read_current_file,
    record_file_read,
    structured_text_patch,
)
from agents.kernel.capabilities.tools.builtin.skill_discovery import discover_dynamic_skills_for_paths


PATCH_APPLY_SCHEMA = {
    "type": "object",
    "properties": {
        "edits": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Workspace-relative file path."},
                    "old_text": {"type": "string", "description": "Exact text to replace."},
                    "new_text": {"type": "string", "description": "Replacement text."},
                    "replace_all": {"type": "boolean", "description": "Replace all occurrences instead of requiring exactly one."},
                },
                "required": ["path", "old_text", "new_text"],
            },
        },
        "creates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Workspace-relative file path."},
                    "content": {"type": "string"},
                    "overwrite": {"type": "boolean", "description": "Allow replacing an existing file."},
                },
                "required": ["path", "content"],
            },
        },
        "dry_run": {"type": "boolean", "description": "Validate and return a diff without writing files."},
    },
}


@dataclass
class _PlannedFile:
    path: str
    before: str
    after: str
    action: str
    encoding: str = "utf-8"
    edit_count: int = 0


@dataclass
class _PlannedEdit:
    path: str
    old_text: str
    new_text: str
    replace_all: bool
    occurrences: int
    original_file: str


def apply_patch(
    context: ToolRuntimeContext,
    edits: list[dict[str, Any]] | None = None,
    creates: list[dict[str, Any]] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    edit_list = [dict(item) for item in (edits or []) if isinstance(item, dict)]
    create_list = [dict(item) for item in (creates or []) if isinstance(item, dict)]
    if not edit_list and not create_list:
        raise ValueError("patch.apply requires at least one edit or create operation")

    planned, planned_edits = _plan_patch(context, edit_list, create_list)
    diff = _combined_diff(planned)
    if not dry_run:
        discover_dynamic_skills_for_paths(context, [item.path for item in planned])
        for item in planned:
            output = preserve_existing_line_endings(item.before, item.after)
            result = context.sandbox_client.write_text(item.path, output, encoding=item.encoding)
            record_file_read(context, result.path, output, encoding=result.encoding)

    files = [
        {
            "path": item.path,
            "action": item.action,
            "edits": item.edit_count,
            "bytes": _encoded_length(item.after, item.encoding),
        }
        for item in planned
    ]
    payload = {
        "dry_run": bool(dry_run),
        "changed": not bool(dry_run),
        "files": files,
        "structuredPatches": [
            {
                "filePath": item.path,
                "hunks": structured_text_patch(item.before, item.after),
            }
            for item in planned
        ],
        "editSummary": [
            {
                "filePath": item.path,
                "oldString": item.old_text,
                "newString": item.new_text,
                "replaceAll": item.replace_all,
                "occurrences": item.occurrences,
            }
            for item in planned_edits
        ],
        "diff": _truncate(diff),
        "truncated": len(diff) > 20000,
    }
    if len(planned_edits) == 1 and not create_list:
        edit = planned_edits[0]
        payload.update(
            {
                "filePath": edit.path,
                "oldString": edit.old_text,
                "newString": edit.new_text,
                "replaceAll": edit.replace_all,
                "originalFile": edit.original_file,
                "structuredPatch": structured_text_patch(edit.original_file, planned[0].after),
            }
        )
    return payload


def _plan_patch(
    context: ToolRuntimeContext,
    edits: list[dict[str, Any]],
    creates: list[dict[str, Any]],
) -> tuple[list[_PlannedFile], list[_PlannedEdit]]:
    content_by_path: dict[str, str] = {}
    encoding_by_path: dict[str, str] = {}
    actions_by_path: dict[str, str] = {}
    edits_by_path: dict[str, int] = {}
    verified_paths: set[str] = set()
    applied_new_texts_by_path: dict[str, list[str]] = {}
    planned_edits: list[_PlannedEdit] = []

    for operation in edits:
        path = _required_string(operation, "path")
        old_text = _required_string(operation, "old_text")
        new_text = str(operation.get("new_text") or "")
        replace_all = bool(operation.get("replace_all"))
        if not old_text:
            raise ValueError("old_text cannot be empty for %s" % path)
        if old_text == new_text:
            raise ValueError("No changes to make: old_text and new_text are exactly the same for %s" % path)
        before = content_by_path.get(path)
        if before is None:
            current_read = read_current_file(context, path)
            relative_path = current_read.path
            before = current_read.content
            encoding_by_path[relative_path] = current_read.encoding
            ensure_existing_file_current(context, relative_path, before)
            verified_paths.add(relative_path)
            path = relative_path
        new_text = normalize_text_write_content(path, new_text)
        match_old_text, match_new_text = _normalize_edit_strings(before, old_text, new_text)
        if match_old_text == match_new_text:
            raise ValueError("No changes to make: old_text and new_text are exactly the same for %s" % path)
        _reject_editing_previous_new_text(match_old_text, applied_new_texts_by_path.get(path, []))
        actual_old_text = _find_actual_text(before, match_old_text)
        if actual_old_text is None:
            raise ValueError("String to replace not found in file.\nPath: %s\nString: %s" % (path, old_text))
        actual_new_text = _preserve_quote_style(match_old_text, actual_old_text, match_new_text)
        occurrences = before.count(actual_old_text)
        if occurrences == 0:
            raise ValueError("String to replace not found in file.\nPath: %s\nString: %s" % (path, old_text))
        if occurrences > 1 and not replace_all:
            raise ValueError(
                "Found %d matches of the string to replace, but replace_all is false. "
                "To replace all occurrences, set replace_all to true. To replace only one occurrence, "
                "provide more context to uniquely identify the instance.\nPath: %s\nString: %s"
                % (occurrences, path, old_text)
            )
        edit_old_text, edit_new_text = _edit_target_and_replacement(before, actual_old_text, actual_new_text)
        replacement_count = before.count(edit_old_text)
        count = replacement_count if replace_all else 1
        content_by_path[path] = before.replace(edit_old_text, edit_new_text, count)
        actions_by_path.setdefault(path, "edit")
        edits_by_path[path] = edits_by_path.get(path, 0) + count
        applied_new_texts_by_path.setdefault(path, []).append(match_new_text)
        planned_edits.append(
            _PlannedEdit(
                path=path,
                old_text=actual_old_text,
                new_text=match_new_text,
                replace_all=replace_all,
                occurrences=count,
                original_file=before,
            )
        )

    for operation in creates:
        path = _required_string(operation, "path")
        content = str(operation.get("content") or "")
        overwrite = bool(operation.get("overwrite"))
        before = ""
        action = "create"
        try:
            current_read = read_current_file(context, path)
            relative_path = current_read.path
            before = current_read.content
            if not overwrite and path not in content_by_path:
                raise ValueError("file already exists: %s" % path)
            if relative_path not in verified_paths:
                ensure_existing_file_current(context, relative_path, before)
                verified_paths.add(relative_path)
            path = relative_path
            encoding_by_path[path] = current_read.encoding
            action = "overwrite"
        except FileNotFoundError:
            before = ""
            encoding_by_path[path] = "utf-8"
        content_by_path[path] = content
        actions_by_path[path] = action
        edits_by_path[path] = edits_by_path.get(path, 0) + 1

    planned: list[_PlannedFile] = []
    for path, after in content_by_path.items():
        before = ""
        encoding = encoding_by_path.get(path, "utf-8")
        try:
            current_read = read_current_file(context, path)
            before = current_read.content
            encoding = current_read.encoding
        except FileNotFoundError:
            before = ""
        if before == after:
            continue
        planned.append(
            _PlannedFile(
                path=path,
                before=before,
                after=after,
                action=actions_by_path.get(path, "edit"),
                encoding=encoding,
                edit_count=edits_by_path.get(path, 0),
            )
        )
    if not planned:
        raise ValueError("patch.apply produced no changes")
    return planned, planned_edits


def _combined_diff(files: list[_PlannedFile]) -> str:
    chunks: list[str] = []
    for item in files:
        chunks.extend(
            difflib.unified_diff(
                item.before.splitlines(keepends=True),
                item.after.splitlines(keepends=True),
                fromfile="a/%s" % item.path,
                tofile="b/%s" % item.path,
                lineterm="",
            )
        )
    return "\n".join(chunks)


def _required_string(payload: dict[str, Any], key: str) -> str:
    value = str(payload.get(key) or "")
    if not value:
        raise ValueError("%s is required" % key)
    return value


LEFT_SINGLE_CURLY_QUOTE = "\u2018"
RIGHT_SINGLE_CURLY_QUOTE = "\u2019"
LEFT_DOUBLE_CURLY_QUOTE = "\u201c"
RIGHT_DOUBLE_CURLY_QUOTE = "\u201d"


def _normalize_quotes(text: str) -> str:
    return (
        str(text)
        .replace(LEFT_SINGLE_CURLY_QUOTE, "'")
        .replace(RIGHT_SINGLE_CURLY_QUOTE, "'")
        .replace(LEFT_DOUBLE_CURLY_QUOTE, '"')
        .replace(RIGHT_DOUBLE_CURLY_QUOTE, '"')
    )


def _find_actual_text(content: str, needle: str) -> str | None:
    if needle in content:
        return needle
    normalized_needle = _normalize_quotes(needle)
    normalized_content = _normalize_quotes(content)
    index = normalized_content.find(normalized_needle)
    if index < 0:
        return None
    return content[index : index + len(needle)]


DESANITIZATIONS = {
    "<fnr>": "<function_results>",
    "<n>": "<name>",
    "</n>": "</name>",
    "<o>": "<output>",
    "</o>": "</output>",
    "<e>": "<error>",
    "</e>": "</error>",
    "<s>": "<system>",
    "</s>": "</system>",
    "<r>": "<result>",
    "</r>": "</result>",
    "< META_START >": "<META_START>",
    "< META_END >": "<META_END>",
    "< EOT >": "<EOT>",
    "< META >": "<META>",
    "< SOS >": "<SOS>",
    "\n\nH:": "\n\nHuman:",
    "\n\nA:": "\n\nAssistant:",
}


def _normalize_edit_strings(content: str, old_text: str, new_text: str) -> tuple[str, str]:
    if _find_actual_text(content, old_text) is not None:
        return old_text, new_text
    desanitized_old_text, replacements = _desanitize_match_string(old_text)
    if not replacements:
        return old_text, new_text
    if _find_actual_text(content, desanitized_old_text) is None:
        return old_text, new_text
    desanitized_new_text = new_text
    for source, target in replacements:
        desanitized_new_text = desanitized_new_text.replace(source, target)
    return desanitized_old_text, desanitized_new_text


def _desanitize_match_string(text: str) -> tuple[str, list[tuple[str, str]]]:
    result = str(text)
    replacements: list[tuple[str, str]] = []
    for source, target in DESANITIZATIONS.items():
        updated = result.replace(source, target)
        if updated != result:
            replacements.append((source, target))
            result = updated
    return result, replacements


def _reject_editing_previous_new_text(old_text: str, previous_new_texts: list[str]) -> None:
    old_text_to_check = re.sub(r"\n+$", "", str(old_text))
    if not old_text_to_check:
        return
    for previous_new_text in previous_new_texts:
        if old_text_to_check in previous_new_text:
            raise ValueError("Cannot edit file: old_text is a substring of a new_text from a previous edit.")


def _preserve_quote_style(old_text: str, actual_old_text: str, new_text: str) -> str:
    if old_text == actual_old_text:
        return new_text
    output = str(new_text)
    if LEFT_DOUBLE_CURLY_QUOTE in actual_old_text or RIGHT_DOUBLE_CURLY_QUOTE in actual_old_text:
        output = _apply_curly_double_quotes(output)
    if LEFT_SINGLE_CURLY_QUOTE in actual_old_text or RIGHT_SINGLE_CURLY_QUOTE in actual_old_text:
        output = _apply_curly_single_quotes(output)
    return output


def _edit_target_and_replacement(content: str, old_text: str, new_text: str) -> tuple[str, str]:
    if new_text or old_text.endswith("\n") or old_text.endswith("\r\n"):
        return old_text, new_text
    if old_text + "\r\n" in content:
        return old_text + "\r\n", new_text
    if old_text + "\n" in content:
        return old_text + "\n", new_text
    return old_text, new_text


def _apply_curly_double_quotes(text: str) -> str:
    chars = list(str(text))
    result: list[str] = []
    for index, char in enumerate(chars):
        if char == '"':
            result.append(LEFT_DOUBLE_CURLY_QUOTE if _is_opening_quote_context(chars, index) else RIGHT_DOUBLE_CURLY_QUOTE)
        else:
            result.append(char)
    return "".join(result)


def _apply_curly_single_quotes(text: str) -> str:
    chars = list(str(text))
    result: list[str] = []
    for index, char in enumerate(chars):
        if char != "'":
            result.append(char)
            continue
        previous = chars[index - 1] if index > 0 else ""
        next_char = chars[index + 1] if index < len(chars) - 1 else ""
        if previous.isalpha() and next_char.isalpha():
            result.append(RIGHT_SINGLE_CURLY_QUOTE)
        else:
            result.append(LEFT_SINGLE_CURLY_QUOTE if _is_opening_quote_context(chars, index) else RIGHT_SINGLE_CURLY_QUOTE)
    return "".join(result)


def _is_opening_quote_context(chars: list[str], index: int) -> bool:
    if index == 0:
        return True
    return chars[index - 1] in {" ", "\t", "\n", "\r", "(", "[", "{", "\u2014", "\u2013"}


def _truncate(text: str, limit: int = 20000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n[truncated]"


def _encoded_length(content: str, encoding: str) -> int:
    normalized = str(encoding or "utf-8").lower().replace("_", "-")
    if normalized in {"utf-16", "utf-16le", "utf-16-le"}:
        return len(str(content).encode("utf-16"))
    if normalized in {"utf-8-sig", "utf8-sig"}:
        return len(str(content).encode("utf-8-sig"))
    return len(str(content).encode("utf-8"))
