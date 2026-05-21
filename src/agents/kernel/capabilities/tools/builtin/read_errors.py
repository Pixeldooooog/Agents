from __future__ import annotations

from pathlib import Path

from agents.kernel.capabilities.sandbox.text import BINARY_FILE_EXTENSIONS
from agents.kernel.capabilities.tools.context import ToolRuntimeContext


FILE_NOT_FOUND_CWD_NOTE = "Note: your current working directory is"
NATIVE_BINARY_READ_EXTENSIONS = {".gif", ".jpeg", ".jpg", ".pdf", ".png", ".webp"}
BLOCKED_DEVICE_PATHS = {
    "/dev/zero",
    "/dev/random",
    "/dev/urandom",
    "/dev/full",
    "/dev/stdin",
    "/dev/tty",
    "/dev/console",
    "/dev/stdout",
    "/dev/stderr",
    "/dev/fd/0",
    "/dev/fd/1",
    "/dev/fd/2",
}


def file_not_found_message(context: ToolRuntimeContext, path: str) -> str:
    cwd = str(context.workspace.path or context.workspace.root or ".")
    message = "File does not exist. %s %s." % (FILE_NOT_FOUND_CWD_NOTE, cwd)
    suggestion = similar_file_name(context, path)
    if suggestion:
        message += " Did you mean %s?" % suggestion
    return message


def directory_read_error(path: str) -> str:
    return "EISDIR: illegal operation on a directory, read '%s'" % path


def blocked_device_read_error(path: str) -> str:
    return "Cannot read '%s': this device file would block or produce infinite output." % path


def is_blocked_device_path(path: str) -> bool:
    if path in BLOCKED_DEVICE_PATHS:
        return True
    stdio_fd_alias = path.endswith("/fd/0") or path.endswith("/fd/1") or path.endswith("/fd/2")
    return path.startswith("/proc/") and stdio_fd_alias


def is_binary_text_read_error(exc: ValueError) -> bool:
    return "cannot read binary files" in str(exc)


def has_unsupported_binary_extension(path: str) -> bool:
    suffix = Path(path).suffix.lower()
    return suffix in BINARY_FILE_EXTENSIONS and suffix not in NATIVE_BINARY_READ_EXTENSIONS


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
