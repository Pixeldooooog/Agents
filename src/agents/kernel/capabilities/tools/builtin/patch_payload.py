from __future__ import annotations

import difflib
from typing import Any

from agents.kernel.capabilities.sandbox.text import encode_text_bytes
from agents.kernel.capabilities.tools.builtin.file_safety import structured_text_patch
from agents.kernel.capabilities.tools.builtin.patch_types import PlannedEdit, PlannedFile


def patch_payload(
    planned: list[PlannedFile],
    planned_edits: list[PlannedEdit],
    *,
    dry_run: bool,
    include_single_edit_metadata: bool,
    git_diffs: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    diff = combined_diff(planned)
    payload = {
        "dry_run": bool(dry_run),
        "changed": not bool(dry_run),
        "files": [
            {
                "path": item.path,
                "action": item.action,
                "edits": item.edit_count,
                "bytes": encoded_length(item.after, item.encoding),
                **({"symlinkTarget": item.symlink_target} if item.symlink_target else {}),
            }
            for item in planned
        ],
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
        "diff": truncate(diff),
        "truncated": len(diff) > 20000,
    }
    if include_single_edit_metadata and len(planned_edits) == 1 and len(planned) == 1:
        edit = planned_edits[0]
        payload.update(
            {
                "filePath": edit.path,
                "oldString": edit.old_text,
                "newString": edit.new_text,
                "replaceAll": edit.replace_all,
                "originalFile": edit.original_file,
                "structuredPatch": structured_text_patch(edit.original_file, planned[0].after),
                "userModified": False,
            }
        )
        if planned[0].symlink_target:
            payload["symlinkTarget"] = planned[0].symlink_target
        git_diff = (git_diffs or {}).get(edit.path)
        if git_diff is not None:
            payload["gitDiff"] = git_diff
    return payload


def format_src_origin_edit_result(result: Any) -> str:
    if not isinstance(result, dict):
        return str(result)
    file_path = str(result.get("filePath") or "")
    if not file_path:
        return str(result)

    modified_note = ""
    if result.get("userModified"):
        modified_note = ".  The user modified your proposed changes before accepting them. "
    if result.get("replaceAll"):
        return "The file %s has been updated%s. All occurrences were successfully replaced." % (
            file_path,
            modified_note,
        )
    return "The file %s has been updated successfully%s." % (file_path, modified_note)


def format_src_origin_multi_edit_result(result: Any) -> str:
    if not isinstance(result, dict):
        return str(result)
    files = result.get("files") if isinstance(result.get("files"), list) else []
    first_file = files[0] if files and isinstance(files[0], dict) else {}
    file_path = str(first_file.get("path") or "")
    if not file_path:
        return str(result)
    edit_count = sum(int(item.get("edits") or 0) for item in files if isinstance(item, dict))
    return "The file %s has been updated successfully. %d edits applied." % (file_path, edit_count)


def combined_diff(files: list[PlannedFile]) -> str:
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


def truncate(text: str, limit: int = 20000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n[truncated]"


def encoded_length(content: str, encoding: str) -> int:
    return len(encode_text_bytes(str(content), encoding))
