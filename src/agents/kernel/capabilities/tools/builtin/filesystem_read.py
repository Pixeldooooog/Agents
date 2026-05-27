from __future__ import annotations

from typing import Any

from agents.kernel.capabilities.tools.builtin.file_safety import record_file_read, unchanged_read_stub
from agents.kernel.capabilities.tools.builtin.filesystem_limits import (
    effective_text_read_max_bytes,
    validate_text_read_tokens,
)
from agents.kernel.capabilities.tools.builtin.filesystem_media import (
    is_image_path,
    is_notebook_path,
    is_pdf_path,
    read_image_file,
    read_notebook_file,
    read_pdf_file,
)
from agents.kernel.capabilities.tools.builtin.filesystem_memory import add_memory_freshness
from agents.kernel.capabilities.tools.builtin.filesystem_results import text_read_payload
from agents.kernel.capabilities.tools.builtin.read_errors import (
    binary_read_error_message,
    blocked_device_read_error,
    directory_read_error,
    file_not_found_message,
    has_unsupported_binary_extension,
    is_binary_text_read_error,
    is_blocked_device_path,
)
from agents.kernel.capabilities.tools.builtin.read_paths import existing_alternate_screenshot_path
from agents.kernel.capabilities.tools.builtin.skill_discovery import discover_dynamic_skills_for_paths
from agents.kernel.capabilities.tools.context import ToolRuntimeContext


def read_file(
    context: ToolRuntimeContext,
    path: str,
    max_bytes: int | None = None,
    offset: int = 1,
    limit: int | None = None,
    pages: str | None = None,
) -> dict[str, Any]:
    if has_unsupported_binary_extension(path):
        raise ValueError(binary_read_error_message(path))
    if is_blocked_device_path(path):
        raise ValueError(blocked_device_read_error(path))
    try:
        return _read_file(context, path, max_bytes=max_bytes, offset=offset, limit=limit, pages=pages)
    except FileNotFoundError as exc:
        alternate_path = existing_alternate_screenshot_path(context, path)
        if alternate_path:
            return _read_file(
                context,
                alternate_path,
                max_bytes=max_bytes,
                offset=offset,
                limit=limit,
                pages=pages,
            )
        raise ValueError(file_not_found_message(context, path)) from exc
    except IsADirectoryError as exc:
        raise ValueError(directory_read_error(path)) from exc


def _read_file(
    context: ToolRuntimeContext,
    path: str,
    max_bytes: int | None = None,
    offset: int = 1,
    limit: int | None = None,
    pages: str | None = None,
) -> dict[str, Any]:
    if pages and not is_pdf_path(path):
        raise ValueError("pages is only supported for PDF files")
    is_notebook = is_notebook_path(path)
    is_pdf = is_pdf_path(path)
    is_image = is_image_path(path)
    if not (is_notebook or is_pdf or is_image):
        cached = unchanged_read_stub(context, path, offset=offset, limit=limit)
        if cached is not None:
            return cached
    discover_dynamic_skills_for_paths(context, [path])
    if is_notebook:
        return read_notebook_file(context, path, pages=pages, max_bytes=max_bytes)
    if is_pdf:
        return read_pdf_file(context, path, pages=pages)
    if is_image:
        return read_image_file(context, path)
    return _read_text_file(context, path, max_bytes=max_bytes, offset=offset, limit=limit)


def _read_text_file(
    context: ToolRuntimeContext,
    path: str,
    max_bytes: int | None,
    offset: int,
    limit: int | None,
) -> dict[str, Any]:
    effective_max_bytes = effective_text_read_max_bytes(context, max_bytes)
    try:
        result = context.sandbox_client.read_text(
            path,
            max_bytes=effective_max_bytes,
            offset=offset,
            limit=limit,
            require_full=True,
        )
    except ValueError as exc:
        if is_binary_text_read_error(exc):
            raise ValueError(binary_read_error_message(path)) from exc
        raise
    validate_text_read_tokens(context, result.content, path)
    if not result.truncated and not result.is_partial_view:
        record_file_read(
            context,
            result.path,
            result.content,
            encoding=result.encoding,
            write_encoding=result.write_encoding,
            source="read",
            offset=max(1, int(offset or 1)),
            limit=limit,
            is_partial_view=False,
        )
    _notify_file_read_listeners(context, result.path, result.content)
    payload = text_read_payload(result.to_dict())
    add_memory_freshness(context, payload)
    return payload


def _notify_file_read_listeners(context: ToolRuntimeContext, path: str, content: str) -> None:
    listeners = list(getattr(context, "file_read_listeners", []) or [])
    if not listeners:
        return
    resolved_path = str(context.sandbox.resolve_workspace_path(path))
    for listener in listeners:
        listener(resolved_path, content)
