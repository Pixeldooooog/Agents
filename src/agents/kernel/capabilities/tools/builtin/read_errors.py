from __future__ import annotations

from pathlib import Path

from agents.kernel.capabilities.tools.context import ToolRuntimeContext


FILE_NOT_FOUND_CWD_NOTE = "Note: your current working directory is"


def file_not_found_message(context: ToolRuntimeContext, path: str) -> str:
    cwd = str(context.workspace.path or context.workspace.root or ".")
    message = "File does not exist. %s %s." % (FILE_NOT_FOUND_CWD_NOTE, cwd)
    suggestion = similar_file_name(context, path)
    if suggestion:
        message += " Did you mean %s?" % suggestion
    return message


def directory_read_error(path: str) -> str:
    return "EISDIR: illegal operation on a directory, read '%s'" % path


def is_binary_text_read_error(exc: ValueError) -> bool:
    return "cannot read binary files" in str(exc)


def binary_read_error_message(path: str) -> str:
    suffix = Path(path).suffix.lower()
    kind = " %s" % suffix if suffix else ""
    return (
        "This tool cannot read binary files. The file appears to be a binary%s file. "
        "Please use appropriate tools for binary file analysis." % kind
    )


def similar_file_name(context: ToolRuntimeContext, path: str) -> str:
    try:
        requested = context.sandbox.resolve_workspace_path(path)
    except Exception:
        return ""
    directory = requested.parent
    try:
        entries = list(directory.iterdir())
    except OSError:
        return ""
    requested_stem = requested.stem
    requested_name = requested.name
    for entry in sorted(entries, key=lambda item: item.name):
        if entry.name == requested_name:
            continue
        if entry.stem == requested_stem and entry.is_file():
            return entry.name
    return ""
