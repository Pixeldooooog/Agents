from __future__ import annotations

from typing import Any

from agents.kernel.capabilities.tools.builtin.file_diff import single_file_git_diff
from agents.kernel.capabilities.tools.builtin.file_safety import (
    normalize_text_write_content,
    preserve_existing_line_endings,
    read_current_file,
    record_file_read,
    symlink_target_for_write,
)
from agents.kernel.capabilities.tools.builtin.lsp import notify_lsp_file_saved
from agents.kernel.capabilities.tools.builtin.patch_payload import (
    format_src_origin_edit_result,
    format_src_origin_multi_edit_result,
    patch_payload,
)
from agents.kernel.capabilities.tools.builtin.patch_planner import (
    SRC_ORIGIN_MAX_EDIT_FILE_SIZE_BYTES,
    plan_patch,
    raise_team_memory_secret_error,
    reject_missing_src_origin_edit_file,
    reject_oversized_src_origin_edit_file,
    reject_src_origin_notebook_edit,
)
from agents.kernel.capabilities.tools.builtin.patch_text import required_string, required_text
from agents.kernel.capabilities.tools.builtin.patch_types import PlannedEdit, PlannedFile
from agents.kernel.capabilities.tools.builtin.skill_discovery import discover_dynamic_skills_for_paths
from agents.kernel.capabilities.tools.context import ToolRuntimeContext


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
                    "replace_all": {
                        "type": "boolean",
                        "description": "Replace all occurrences instead of requiring exactly one.",
                    },
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


def apply_patch(
    context: ToolRuntimeContext,
    edits: list[dict[str, Any]] | None = None,
    creates: list[dict[str, Any]] | None = None,
    dry_run: bool = False,
    src_origin_error_messages: bool = False,
) -> dict[str, Any]:
    edit_list = [dict(item) for item in (edits or []) if isinstance(item, dict)]
    create_list = [dict(item) for item in (creates or []) if isinstance(item, dict)]
    if not edit_list and not create_list:
        raise ValueError("patch.apply requires at least one edit or create operation")

    planned, planned_edits = plan_patch(
        context,
        edit_list,
        create_list,
        src_origin_error_messages=src_origin_error_messages,
    )
    git_diffs: dict[str, dict[str, Any]] = {}
    if not dry_run:
        discover_dynamic_skills_for_paths(context, [item.path for item in planned])
        for item in planned:
            output = preserve_existing_line_endings(item.before, item.after)
            result = context.sandbox_client.write_text(item.path, output, encoding=item.encoding)
            record_file_read(context, result.path, output, encoding=result.encoding, write_encoding=result.write_encoding)
            notify_lsp_file_saved(context, result.path, output)
            git_diff = single_file_git_diff(context, result.path)
            if git_diff is not None:
                git_diffs[result.path] = git_diff

    return patch_payload(
        planned,
        planned_edits,
        dry_run=dry_run,
        include_single_edit_metadata=len(planned_edits) == 1 and not create_list,
        git_diffs=git_diffs,
    )


def apply_src_origin_edit(
    context: ToolRuntimeContext,
    file_path: str,
    old_string: str,
    new_string: str,
    replace_all: bool = False,
) -> dict[str, Any]:
    if old_string == new_string:
        raise ValueError("No changes to make: old_string and new_string are exactly the same.")
    reject_oversized_src_origin_edit_file(
        context,
        file_path,
        max_size_bytes=SRC_ORIGIN_MAX_EDIT_FILE_SIZE_BYTES,
    )
    if old_string != "":
        reject_missing_src_origin_edit_file(context, file_path)
        reject_src_origin_notebook_edit(context, file_path)
        return apply_patch(
            context,
            edits=[
                {
                    "path": file_path,
                    "old_text": old_string,
                    "new_text": new_string,
                    "replace_all": bool(replace_all),
                }
            ],
            src_origin_error_messages=True,
        )
    return _apply_empty_src_origin_edit(
        context,
        file_path=file_path,
        new_string=new_string,
        replace_all=replace_all,
    )


def apply_src_origin_multi_edit(
    context: ToolRuntimeContext,
    file_path: str,
    edits: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    path = required_text(file_path, "file_path")
    if not edits:
        raise ValueError("MultiEdit requires at least one edit.")
    reject_oversized_src_origin_edit_file(
        context,
        path,
        max_size_bytes=SRC_ORIGIN_MAX_EDIT_FILE_SIZE_BYTES,
    )
    reject_missing_src_origin_edit_file(context, path)
    reject_src_origin_notebook_edit(context, path)
    return apply_patch(
        context,
        edits=[
            {
                "path": path,
                "old_text": required_string(edit, "old_string"),
                "new_text": str(edit.get("new_string") or ""),
                "replace_all": bool(edit.get("replace_all")),
            }
            for edit in edits
            if isinstance(edit, dict)
        ],
        src_origin_error_messages=True,
    )


def _apply_empty_src_origin_edit(
    context: ToolRuntimeContext,
    *,
    file_path: str,
    new_string: str,
    replace_all: bool,
) -> dict[str, Any]:
    path = required_text(file_path, "file_path")
    before = ""
    encoding = "utf-8"
    action = "create"
    try:
        symlink_target = symlink_target_for_write(context, path)
        current_read = read_current_file(context, path)
        path = current_read.path
        before = current_read.content
        encoding = current_read.write_encoding or current_read.encoding
        action = "overwrite"
    except FileNotFoundError:
        symlink_target = symlink_target_for_write(context, path)
        path = context.sandbox.relative_workspace_path(context.sandbox.resolve_workspace_path(path))
    if before.strip():
        raise ValueError("Cannot create new file - file already exists.")

    after = normalize_text_write_content(path, str(new_string or ""))
    raise_team_memory_secret_error(path, after)
    if before == after:
        raise ValueError("Original and edited file match exactly. Failed to apply edit.")
    discover_dynamic_skills_for_paths(context, [path])
    output = preserve_existing_line_endings(before, after)
    result = context.sandbox_client.write_text(path, output, encoding=encoding)
    record_file_read(context, result.path, output, encoding=result.encoding, write_encoding=result.write_encoding)
    notify_lsp_file_saved(context, result.path, output)
    git_diff = single_file_git_diff(context, result.path)

    planned = PlannedFile(
        path=result.path,
        before=before,
        after=output,
        action=action,
        encoding=result.encoding,
        edit_count=1,
        symlink_target=symlink_target,
    )
    planned_edit = PlannedEdit(
        path=result.path,
        old_text="",
        new_text=after,
        replace_all=bool(replace_all),
        occurrences=1,
        original_file=before,
    )
    return patch_payload(
        [planned],
        [planned_edit],
        dry_run=False,
        include_single_edit_metadata=True,
        git_diffs={result.path: git_diff} if git_diff is not None else {},
    )
