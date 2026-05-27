from __future__ import annotations

from typing import Any

from agents.kernel.capabilities.sandbox.text import DEFAULT_TEXT_READ_MAX_BYTES
from agents.kernel.capabilities.tools.builtin.file_safety import write_text_safely
from agents.kernel.capabilities.tools.builtin.filesystem_read import read_file
from agents.kernel.capabilities.tools.builtin.filesystem_results import format_read_file_result
from agents.kernel.capabilities.tools.builtin.skill_discovery import discover_dynamic_skills_for_paths
from agents.kernel.capabilities.tools.context import ToolRuntimeContext


READ_FILE_SCHEMA = {
    "type": "object",
    "properties": {
        "path": {"type": "string", "description": "Workspace-relative file path."},
        "max_bytes": {"type": "integer", "minimum": 1, "maximum": DEFAULT_TEXT_READ_MAX_BYTES},
        "offset": {"type": "integer", "minimum": 0},
        "limit": {"type": "integer", "minimum": 1},
        "pages": {"type": "string", "description": "Page range for PDF files. Currently reserved for PDF page extraction parity."},
    },
    "required": ["path"],
}

LIST_DIR_SCHEMA = {
    "type": "object",
    "properties": {
        "path": {"type": "string", "description": "Workspace-relative directory path."},
    },
}

WRITE_FILE_SCHEMA = {
    "type": "object",
    "properties": {
        "path": {"type": "string", "description": "Workspace-relative file path."},
        "content": {"type": "string"},
    },
    "required": ["path", "content"],
}

DELETE_PATH_SCHEMA = {
    "type": "object",
    "properties": {
        "path": {"type": "string", "description": "Workspace-relative file or directory path to delete."},
        "recursive": {"type": "boolean", "description": "Required for deleting directories."},
    },
    "required": ["path"],
}

MOVE_PATH_SCHEMA = {
    "type": "object",
    "properties": {
        "source_path": {"type": "string", "description": "Workspace-relative source file or directory path."},
        "destination_path": {"type": "string", "description": "Workspace-relative destination path."},
        "overwrite": {"type": "boolean", "description": "Overwrite an existing destination file."},
    },
    "required": ["source_path", "destination_path"],
}


def list_dir(context: ToolRuntimeContext, path: str = ".") -> dict[str, Any]:
    return context.sandbox_client.list_dir(path or ".").to_dict()


def write_file(context: ToolRuntimeContext, path: str, content: str) -> dict[str, Any]:
    discover_dynamic_skills_for_paths(context, [path])
    return write_text_safely(context, path, content)


def delete_path(context: ToolRuntimeContext, path: str, recursive: bool = False) -> dict[str, Any]:
    return context.sandbox_client.delete_path(path, recursive=recursive)


def move_path(
    context: ToolRuntimeContext,
    source_path: str,
    destination_path: str,
    overwrite: bool = False,
) -> dict[str, Any]:
    return context.sandbox_client.move_path(source_path, destination_path, overwrite=overwrite)
