from __future__ import annotations

from typing import Any

from agents.kernel.capabilities.sandbox.text import format_file_size
from agents.kernel.capabilities.tools.builtin.file_safety import (
    ensure_existing_file_current,
    normalize_text_write_content,
    read_current_file,
    symlink_target_for_write,
)
from agents.kernel.capabilities.tools.builtin.patch_text import (
    edit_target_and_replacement,
    find_actual_text,
    normalize_edit_strings,
    preserve_quote_style,
    reject_editing_previous_new_text,
    required_string,
)
from agents.kernel.capabilities.tools.builtin.patch_types import PlannedEdit, PlannedFile
from agents.kernel.capabilities.tools.builtin.read_errors import file_not_found_message
from agents.kernel.capabilities.tools.builtin.team_memory_safety import check_team_memory_secrets
from agents.kernel.capabilities.tools.context import ToolRuntimeContext


SRC_ORIGIN_MAX_EDIT_FILE_SIZE_BYTES = 1024 * 1024 * 1024


def reject_missing_src_origin_edit_file(context: ToolRuntimeContext, file_path: str) -> None:
    resolved = context.sandbox.resolve_workspace_path(file_path)
    if not resolved.exists():
        raise ValueError(file_not_found_message(context, file_path))


def reject_oversized_src_origin_edit_file(
    context: ToolRuntimeContext,
    file_path: str,
    *,
    max_size_bytes: int = SRC_ORIGIN_MAX_EDIT_FILE_SIZE_BYTES,
) -> None:
    resolved = context.sandbox.resolve_workspace_path(file_path)
    if not resolved.exists():
        return
    size = resolved.stat().st_size
    if size > max_size_bytes:
        raise ValueError(
            "File is too large to edit (%s). Maximum editable file size is %s."
            % (format_file_size(size), format_file_size(max_size_bytes))
        )


def reject_src_origin_notebook_edit(context: ToolRuntimeContext, file_path: str) -> None:
    resolved = context.sandbox.resolve_workspace_path(file_path)
    if resolved.exists() and resolved.suffix.lower() == ".ipynb":
        raise ValueError("File is a Jupyter Notebook. Use the NotebookEdit tool to edit this file.")


def plan_patch(
    context: ToolRuntimeContext,
    edits: list[dict[str, Any]],
    creates: list[dict[str, Any]],
    *,
    src_origin_error_messages: bool = False,
) -> tuple[list[PlannedFile], list[PlannedEdit]]:
    content_by_path: dict[str, str] = {}
    encoding_by_path: dict[str, str] = {}
    actions_by_path: dict[str, str] = {}
    edits_by_path: dict[str, int] = {}
    symlink_targets_by_path: dict[str, str] = {}
    verified_paths: set[str] = set()
    applied_new_texts_by_path: dict[str, list[str]] = {}
    planned_edits: list[PlannedEdit] = []

    for operation in edits:
        path = required_string(operation, "path")
        symlink_target = symlink_target_for_write(context, path)
        old_text = required_string(operation, "old_text")
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
            encoding_by_path[relative_path] = current_read.write_encoding or current_read.encoding
            ensure_existing_file_current(context, relative_path, before)
            verified_paths.add(relative_path)
            if symlink_target:
                symlink_targets_by_path[relative_path] = symlink_target
            path = relative_path
        new_text = normalize_text_write_content(path, new_text)
        raise_team_memory_secret_error(path, new_text)
        match_old_text, match_new_text = normalize_edit_strings(before, old_text, new_text)
        if match_old_text == match_new_text:
            raise ValueError("No changes to make: old_text and new_text are exactly the same for %s" % path)
        reject_editing_previous_new_text(match_old_text, applied_new_texts_by_path.get(path, []))
        actual_old_text = find_actual_text(before, match_old_text)
        if actual_old_text is None:
            raise ValueError(string_not_found_message(path, old_text, src_origin_error_messages))
        actual_new_text = preserve_quote_style(match_old_text, actual_old_text, match_new_text)
        occurrences = before.count(actual_old_text)
        if occurrences == 0:
            raise ValueError(string_not_found_message(path, old_text, src_origin_error_messages))
        if occurrences > 1 and not replace_all:
            raise ValueError(ambiguous_edit_message(occurrences, path, old_text, src_origin_error_messages))
        edit_old_text, edit_new_text = edit_target_and_replacement(before, actual_old_text, actual_new_text)
        replacement_count = before.count(edit_old_text)
        count = replacement_count if replace_all else 1
        content_by_path[path] = before.replace(edit_old_text, edit_new_text, count)
        actions_by_path.setdefault(path, "edit")
        edits_by_path[path] = edits_by_path.get(path, 0) + count
        applied_new_texts_by_path.setdefault(path, []).append(match_new_text)
        planned_edits.append(
            PlannedEdit(
                path=path,
                old_text=actual_old_text,
                new_text=match_new_text,
                replace_all=replace_all,
                occurrences=count,
                original_file=before,
            )
        )

    for operation in creates:
        path = required_string(operation, "path")
        symlink_target = symlink_target_for_write(context, path)
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
            if symlink_target:
                symlink_targets_by_path[relative_path] = symlink_target
            path = relative_path
            encoding_by_path[path] = current_read.write_encoding or current_read.encoding
            action = "overwrite"
        except FileNotFoundError:
            before = ""
            encoding_by_path[path] = "utf-8"
            if symlink_target:
                symlink_targets_by_path[path] = symlink_target
        raise_team_memory_secret_error(path, content)
        content_by_path[path] = content
        actions_by_path[path] = action
        edits_by_path[path] = edits_by_path.get(path, 0) + 1

    planned: list[PlannedFile] = []
    for path, after in content_by_path.items():
        before = ""
        encoding = encoding_by_path.get(path, "utf-8")
        try:
            current_read = read_current_file(context, path)
            before = current_read.content
            encoding = current_read.write_encoding or current_read.encoding
        except FileNotFoundError:
            before = ""
        if before == after:
            continue
        planned.append(
            PlannedFile(
                path=path,
                before=before,
                after=after,
                action=actions_by_path.get(path, "edit"),
                encoding=encoding,
                edit_count=edits_by_path.get(path, 0),
                symlink_target=symlink_targets_by_path.get(path, ""),
            )
        )
    if not planned:
        raise ValueError("patch.apply produced no changes")
    return planned, planned_edits


def raise_team_memory_secret_error(path: str, content: str) -> None:
    secret_error = check_team_memory_secrets(path, content)
    if secret_error is not None:
        raise ValueError(secret_error)


def string_not_found_message(path: str, old_text: str, src_origin_error_messages: bool) -> str:
    if src_origin_error_messages:
        return "String to replace not found in file.\nString: %s" % old_text
    return "String to replace not found in file.\nPath: %s\nString: %s" % (path, old_text)


def ambiguous_edit_message(
    occurrences: int,
    path: str,
    old_text: str,
    src_origin_error_messages: bool,
) -> str:
    guidance = (
        "Found %d matches of the string to replace, but replace_all is false. "
        "To replace all occurrences, set replace_all to true. To replace only one occurrence, "
        "please provide more context to uniquely identify the instance."
    ) % occurrences
    if src_origin_error_messages:
        return "%s\nString: %s" % (guidance, old_text)
    return "%s\nPath: %s\nString: %s" % (guidance, path, old_text)
