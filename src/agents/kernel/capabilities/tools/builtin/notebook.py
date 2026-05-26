from __future__ import annotations

import json
import secrets
from pathlib import Path
from typing import Any

from agents.kernel.capabilities.tools.builtin.file_safety import (
    ensure_existing_file_current,
    preserve_existing_line_endings,
    record_file_read,
    read_current_file,
    structured_text_patch,
    symlink_target_for_write,
)
from agents.kernel.capabilities.tools.builtin.lsp import notify_lsp_file_saved
from agents.kernel.capabilities.tools.context import ToolRuntimeContext


NOTEBOOK_EDIT_SCHEMA = {
    "type": "object",
    "properties": {
        "notebook_path": {
            "type": "string",
            "description": "Workspace-relative or workspace-contained absolute path to the Jupyter notebook file.",
        },
        "cell_id": {
            "type": "string",
            "description": "Cell ID to edit. For inserts, the new cell is inserted after this cell; omit to insert at the beginning.",
        },
        "new_source": {"type": "string", "description": "The new source for the cell."},
        "cell_type": {
            "type": "string",
            "enum": ["code", "markdown"],
            "description": "Cell type for inserted cells, or optional replacement cell type.",
        },
        "edit_mode": {
            "type": "string",
            "enum": ["replace", "insert", "delete"],
            "description": "Notebook edit mode. Defaults to replace.",
        },
    },
    "required": ["notebook_path", "new_source"],
}

IPYNB_INDENT = 1


def notebook_edit(
    context: ToolRuntimeContext,
    notebook_path: str,
    new_source: str,
    cell_id: str | None = None,
    cell_type: str | None = None,
    edit_mode: str = "replace",
) -> dict[str, Any]:
    relative_path, original_content, encoding = _read_current_notebook_for_edit(context, notebook_path)
    symlink_target = symlink_target_for_write(context, notebook_path)
    notebook = _parse_notebook(original_content, relative_path)
    cells = _notebook_cells(notebook, relative_path)
    mode = _edit_mode(edit_mode)
    requested_cell_type = _cell_type(cell_type) if cell_type is not None else None
    if mode == "insert" and requested_cell_type is None:
        raise ValueError("Cell type is required when using edit_mode=insert.")
    cell_index = _cell_index(cells, cell_id, edit_mode=mode)
    if mode == "replace" and cell_index == len(cells):
        mode = "insert"
        requested_cell_type = requested_cell_type or "code"
    old_cell_source = "" if mode == "insert" else _cell_source(cells[cell_index])
    updated_cell_source = "" if mode == "delete" else str(new_source)
    language = str((notebook.get("metadata") or {}).get("language_info", {}).get("name") or "python")
    output_cell_id = _apply_notebook_cell_edit(
        notebook,
        cell_index=cell_index,
        cell_id=cell_id,
        new_source=str(new_source),
        cell_type=requested_cell_type,
        edit_mode=mode,
    )
    updated_content = json.dumps(notebook, ensure_ascii=False, indent=IPYNB_INDENT)
    updated_content = preserve_existing_line_endings(original_content, updated_content)
    result = context.sandbox_client.write_text(relative_path, updated_content, encoding=encoding)
    record_file_read(
        context,
        result.path,
        updated_content,
        encoding=result.encoding,
        write_encoding=result.write_encoding,
        source="write",
    )
    notify_lsp_file_saved(context, result.path, updated_content)
    result_cell_type = requested_cell_type or _result_cell_type(cells, cell_index, mode)
    ui_metadata = _notebook_edit_ui_metadata(
        relative_path=relative_path,
        output_cell_id=output_cell_id,
        cell_index=cell_index,
        result_cell_type=result_cell_type,
        mode=mode,
        old_cell_source=old_cell_source,
        updated_cell_source=updated_cell_source,
    )
    payload = {
        "new_source": str(new_source),
        "cell_id": output_cell_id,
        "cell_type": result_cell_type,
        "language": language,
        "edit_mode": mode,
        "error": "",
        "notebook_path": relative_path,
        "path": relative_path,
        **ui_metadata,
        "original_file": original_content,
        "updated_file": updated_content,
        "originalFile": original_content,
        "updatedFile": updated_content,
        "bytes": result.bytes,
        "encoding": result.encoding,
    }
    if symlink_target:
        payload["symlinkTarget"] = symlink_target
    return payload


def format_notebook_edit_result(result: Any) -> str:
    payload = dict(result or {}) if isinstance(result, dict) else {}
    error = str(payload.get("error") or "")
    if error:
        return error
    mode = str(payload.get("edit_mode") or "replace")
    cell_id = str(payload.get("cell_id") or "")
    source = str(payload.get("new_source") or "")
    if mode == "insert":
        return "Inserted cell %s with %s" % (cell_id, source)
    if mode == "delete":
        return "Deleted cell %s" % cell_id
    if mode == "replace":
        return "Updated cell %s with %s" % (cell_id, source)
    return "Unknown edit mode"


def _notebook_edit_ui_metadata(
    *,
    relative_path: str,
    output_cell_id: str,
    cell_index: int,
    result_cell_type: str,
    mode: str,
    old_cell_source: str,
    updated_cell_source: str,
) -> dict[str, Any]:
    structured_patch = structured_text_patch(old_cell_source, updated_cell_source)
    return {
        "filePath": relative_path,
        "notebookPath": relative_path,
        "cellId": output_cell_id,
        "cellIndex": cell_index,
        "cellType": result_cell_type,
        "editMode": mode,
        "oldString": old_cell_source,
        "newString": updated_cell_source,
        "replaceAll": False,
        "originalCellSource": old_cell_source,
        "updatedCellSource": updated_cell_source,
        "structuredPatch": structured_patch,
        "structuredPatches": [
            {
                "filePath": relative_path,
                "cellId": output_cell_id,
                "cellIndex": cell_index,
                "editMode": mode,
                "hunks": structured_patch,
            }
        ],
        "editSummary": [
            {
                "filePath": relative_path,
                "cellId": output_cell_id,
                "cellIndex": cell_index,
                "cellType": result_cell_type,
                "editMode": mode,
                "oldString": old_cell_source,
                "newString": updated_cell_source,
                "replaceAll": False,
                "occurrences": 0 if mode == "insert" else 1,
            }
        ],
    }


def _read_current_notebook_for_edit(context: ToolRuntimeContext, notebook_path: str) -> tuple[str, str, str]:
    path = str(notebook_path or "").strip()
    if not path:
        raise ValueError("notebook_path is required")
    if path.startswith("\\\\") or path.startswith("//"):
        raise PermissionError("refusing to edit UNC path: %s" % path)
    if Path(path).suffix != ".ipynb":
        raise ValueError("File must be a Jupyter notebook (.ipynb file). For editing other file types, use patch.apply.")
    current = read_current_file(context, path)
    ensure_existing_file_current(context, current.path, current.content)
    return current.path, current.content, current.write_encoding or current.encoding


def _parse_notebook(content: str, path: str) -> dict[str, Any]:
    try:
        notebook = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError("Notebook is not valid JSON.") from exc
    if not isinstance(notebook, dict):
        raise ValueError("Notebook is not valid JSON: %s" % path)
    return notebook


def _notebook_cells(notebook: dict[str, Any], path: str) -> list[dict[str, Any]]:
    cells = notebook.get("cells")
    if not isinstance(cells, list):
        raise ValueError("Notebook cells must be a list: %s" % path)
    if not all(isinstance(cell, dict) for cell in cells):
        raise ValueError("Notebook cells must be objects: %s" % path)
    return cells


def _edit_mode(value: str | None) -> str:
    mode = str(value or "replace").strip() or "replace"
    if mode not in {"replace", "insert", "delete"}:
        raise ValueError("Edit mode must be replace, insert, or delete.")
    return mode


def _cell_type(value: str | None) -> str:
    cell_type = str(value or "").strip()
    if cell_type not in {"code", "markdown"}:
        raise ValueError("Cell type must be code or markdown.")
    return cell_type


def _cell_index(cells: list[dict[str, Any]], cell_id: str | None, *, edit_mode: str) -> int:
    if not cell_id:
        if edit_mode == "insert":
            return 0
        raise ValueError("Cell ID must be specified when not inserting a new cell.")
    cell_id_text = str(cell_id)
    for index, cell in enumerate(cells):
        if str(cell.get("id") or "") == cell_id_text:
            return index + 1 if edit_mode == "insert" else index
    parsed_index = _parse_cell_id(cell_id_text)
    if parsed_index is None:
        raise ValueError('Cell with ID "%s" not found in notebook.' % cell_id_text)
    if parsed_index == len(cells) and edit_mode == "replace":
        return parsed_index
    if parsed_index < 0 or parsed_index >= len(cells):
        raise ValueError("Cell with index %d does not exist in notebook." % parsed_index)
    return parsed_index + 1 if edit_mode == "insert" else parsed_index


def _parse_cell_id(cell_id: str) -> int | None:
    value = str(cell_id or "").strip()
    if value.startswith("cell-"):
        value = value.removeprefix("cell-")
    if not value.isdigit():
        return None
    return int(value)


def _cell_source(cell: dict[str, Any]) -> str:
    source = cell.get("source", "")
    if isinstance(source, list):
        return "".join(str(item) for item in source)
    return str(source or "")


def _apply_notebook_cell_edit(
    notebook: dict[str, Any],
    *,
    cell_index: int,
    cell_id: str | None,
    new_source: str,
    cell_type: str | None,
    edit_mode: str,
) -> str:
    cells = _notebook_cells(notebook, "")
    if edit_mode == "delete":
        deleted = cells.pop(cell_index)
        return str(deleted.get("id") or cell_id or "cell-%d" % cell_index)
    if edit_mode == "insert":
        new_cell_id = _new_notebook_cell_id(notebook)
        cells.insert(cell_index, _new_notebook_cell(cell_type or "code", new_source, new_cell_id))
        return new_cell_id or "cell-%d" % cell_index
    target = cells[cell_index]
    target["source"] = new_source
    if target.get("cell_type") == "code":
        target["execution_count"] = None
        target["outputs"] = []
    if cell_type:
        target["cell_type"] = cell_type
        if cell_type == "code":
            target.setdefault("execution_count", None)
            target.setdefault("outputs", [])
        else:
            target.pop("execution_count", None)
            target.pop("outputs", None)
    return str(target.get("id") or cell_id or "cell-%d" % cell_index)


def _new_notebook_cell(cell_type: str, source: str, cell_id: str) -> dict[str, Any]:
    if cell_type == "markdown":
        return {"cell_type": "markdown", "id": cell_id, "source": source, "metadata": {}}
    return {
        "cell_type": "code",
        "id": cell_id,
        "source": source,
        "metadata": {},
        "execution_count": None,
        "outputs": [],
    }


def _new_notebook_cell_id(notebook: dict[str, Any]) -> str:
    if _notebook_supports_cell_ids(notebook):
        return secrets.token_hex(6)
    return ""


def _notebook_supports_cell_ids(notebook: dict[str, Any]) -> bool:
    try:
        nbformat = int(notebook.get("nbformat") or 0)
        minor = int(notebook.get("nbformat_minor") or 0)
    except (TypeError, ValueError):
        return False
    return nbformat > 4 or (nbformat == 4 and minor >= 5)


def _result_cell_type(cells: list[dict[str, Any]], cell_index: int, edit_mode: str) -> str:
    if edit_mode == "delete":
        return "code"
    if 0 <= cell_index < len(cells):
        return str(cells[cell_index].get("cell_type") or "code")
    return "code"
