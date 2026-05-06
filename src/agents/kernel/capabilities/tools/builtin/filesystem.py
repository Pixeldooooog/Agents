from __future__ import annotations

from typing import Any

from agents.kernel.capabilities.tools.context import ToolRuntimeContext


READ_FILE_SCHEMA = {
    "type": "object",
    "properties": {
        "path": {"type": "string", "description": "Workspace-relative file path."},
        "max_bytes": {"type": "integer", "minimum": 1, "maximum": 200000},
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


def read_file(context: ToolRuntimeContext, path: str, max_bytes: int = 20000) -> dict[str, Any]:
    return context.sandbox_client.read_text(path, max_bytes=max_bytes).to_dict()


def list_dir(context: ToolRuntimeContext, path: str = ".") -> dict[str, Any]:
    return context.sandbox_client.list_dir(path or ".").to_dict()


def write_file(context: ToolRuntimeContext, path: str, content: str) -> dict[str, Any]:
    return context.sandbox_client.write_text(path, content).to_dict()


def delete_path(context: ToolRuntimeContext, path: str, recursive: bool = False) -> dict[str, Any]:
    return context.sandbox_client.delete_path(path, recursive=recursive)


def move_path(
    context: ToolRuntimeContext,
    source_path: str,
    destination_path: str,
    overwrite: bool = False,
) -> dict[str, Any]:
    return context.sandbox_client.move_path(source_path, destination_path, overwrite=overwrite)
