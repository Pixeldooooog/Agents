from __future__ import annotations

import base64
import json
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from agents.kernel.capabilities.tools.context import ToolRuntimeContext
from agents.kernel.capabilities.tools.builtin.file_safety import record_file_read, unchanged_read_stub, write_text_safely
from agents.kernel.capabilities.tools.builtin.read_errors import (
    binary_read_error_message,
    blocked_device_read_error,
    directory_read_error,
    file_not_found_message,
    is_binary_text_read_error,
    is_blocked_device_path,
)


FILE_UNCHANGED_STUB = (
    "File unchanged since last read. The content from the earlier filesystem.read tool result "
    "in this conversation is still current; refer to that instead of re-reading."
)
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
BINARY_READ_MAX_BYTES = 5 * 1024 * 1024
NOTEBOOK_READ_MAX_BYTES = 2 * 1024 * 1024
PDF_MAX_PAGES_PER_READ = 20
SECONDS_PER_DAY = 86400
MEMORY_ROOTS = {".agents", ".claude"}
AUTO_MEMORY_DIRS = {"memory", "memories"}
AGENT_MEMORY_DIRS = {"agent-memory", "agent-memory-local"}


READ_FILE_SCHEMA = {
    "type": "object",
    "properties": {
        "path": {"type": "string", "description": "Workspace-relative file path."},
        "max_bytes": {"type": "integer", "minimum": 1, "maximum": 200000},
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


def read_file(
    context: ToolRuntimeContext,
    path: str,
    max_bytes: int = 20000,
    offset: int = 1,
    limit: int | None = None,
    pages: str | None = None,
) -> dict[str, Any]:
    if is_blocked_device_path(path):
        raise ValueError(blocked_device_read_error(path))
    try:
        return _read_file(context, path, max_bytes=max_bytes, offset=offset, limit=limit, pages=pages)
    except FileNotFoundError as exc:
        raise ValueError(file_not_found_message(context, path)) from exc
    except IsADirectoryError as exc:
        raise ValueError(directory_read_error(path)) from exc


def _read_file(
    context: ToolRuntimeContext,
    path: str,
    max_bytes: int = 20000,
    offset: int = 1,
    limit: int | None = None,
    pages: str | None = None,
) -> dict[str, Any]:
    if pages and not _is_pdf_path(path):
        raise ValueError("pages is only supported for PDF files")
    if _is_notebook_path(path):
        return _read_notebook_file(context, path, pages=pages)
    if _is_pdf_path(path):
        return _read_pdf_file(context, path, pages=pages)
    if _is_image_path(path):
        return _read_image_file(context, path)
    cached = unchanged_read_stub(context, path, offset=offset, limit=limit)
    if cached is not None:
        return cached
    try:
        result = context.sandbox_client.read_text(path, max_bytes=max_bytes, offset=offset, limit=limit)
    except ValueError as exc:
        if is_binary_text_read_error(exc):
            raise ValueError(binary_read_error_message(path)) from exc
        raise
    if not result.truncated and not result.is_partial_view:
        record_file_read(
            context,
            result.path,
            result.content,
            encoding=result.encoding,
            source="read",
            offset=max(1, int(offset or 1)),
            limit=limit,
            is_partial_view=False,
        )
    payload = _text_read_payload(result.to_dict())
    _add_memory_freshness(context, payload)
    return payload


def format_read_file_result(result: Any) -> str:
    payload = dict(result or {}) if isinstance(result, dict) else {}
    if payload.get("type") == "file_unchanged":
        return FILE_UNCHANGED_STUB
    if payload.get("type") == "image":
        file_payload = payload.get("file") if isinstance(payload.get("file"), dict) else {}
        file_path = str(file_payload.get("filePath") or payload.get("path") or "")
        original_size = int(file_payload.get("originalSize") or payload.get("bytes") or 0)
        media_type = str(file_payload.get("type") or payload.get("mimeType") or "image")
        return "Image file read: %s (%s, %d bytes)" % (file_path, media_type, original_size)
    if payload.get("type") == "pdf":
        file_payload = payload.get("file") if isinstance(payload.get("file"), dict) else {}
        file_path = str(file_payload.get("filePath") or payload.get("path") or "")
        original_size = int(file_payload.get("originalSize") or payload.get("bytes") or 0)
        return "PDF file read: %s (%d bytes)" % (file_path, original_size)
    if payload.get("type") == "parts":
        file_payload = payload.get("file") if isinstance(payload.get("file"), dict) else {}
        file_path = str(file_payload.get("filePath") or payload.get("path") or "")
        original_size = int(file_payload.get("originalSize") or payload.get("bytes") or 0)
        count = int(file_payload.get("count") or 0)
        return "PDF pages extracted: %d page(s) from %s (%d bytes)" % (count, file_path, original_size)
    if payload.get("type") == "notebook":
        file_payload = payload.get("file") if isinstance(payload.get("file"), dict) else {}
        file_path = str(file_payload.get("filePath") or payload.get("path") or "")
        cells = file_payload.get("cells") if isinstance(file_payload.get("cells"), list) else []
        return "Notebook file read: %s (%d cells)\n%s" % (
            file_path,
            len(cells),
            json.dumps(cells, ensure_ascii=False, indent=2),
        )
    file_payload = payload.get("file") if isinstance(payload.get("file"), dict) else {}
    content = str(payload.get("content") if "content" in payload else file_payload.get("content") or "")
    total_lines = int(payload.get("totalLines") if "totalLines" in payload else file_payload.get("totalLines") or 0)
    start_line = int(payload.get("startLine") if "startLine" in payload else file_payload.get("startLine") or 1)
    if not content:
        if total_lines == 0:
            return "<system-reminder>Warning: the file exists but the contents are empty.</system-reminder>"
        return (
            "<system-reminder>Warning: the file exists but is shorter than the provided offset "
            "(%d). The file has %d lines.</system-reminder>" % (start_line, total_lines)
        )
    output = _format_numbered_lines(content, start_line)
    if bool(payload.get("isPartialView")):
        output = "%s\n\n[Read partial file view: startLine=%d, numLines=%d, totalLines=%d]" % (
            output,
            start_line,
            int(payload.get("numLines") or 0),
            total_lines,
        )
    freshness_note = str(payload.get("memoryFreshnessNote") or "")
    if freshness_note:
        output = "%s%s" % (freshness_note, output)
    return output


def list_dir(context: ToolRuntimeContext, path: str = ".") -> dict[str, Any]:
    return context.sandbox_client.list_dir(path or ".").to_dict()


def write_file(context: ToolRuntimeContext, path: str, content: str) -> dict[str, Any]:
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


def _format_numbered_lines(content: str, start_line: int) -> str:
    lines = content.splitlines()
    return "\n".join("%d\t%s" % (index + start_line, line) for index, line in enumerate(lines))


def _text_read_payload(payload: dict[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    result["type"] = "text"
    result["file"] = {
        "filePath": str(result.get("path") or ""),
        "content": str(result.get("content") or ""),
        "numLines": int(result.get("numLines") or 0),
        "startLine": int(result.get("startLine") or 1),
        "totalLines": int(result.get("totalLines") or 0),
    }
    return result


def _add_memory_freshness(context: ToolRuntimeContext, payload: dict[str, Any]) -> None:
    file_payload = payload.get("file") if isinstance(payload.get("file"), dict) else {}
    relative_path = str(file_payload.get("filePath") or payload.get("path") or "")
    memory_metadata = _memory_file_metadata(relative_path)
    if memory_metadata is None:
        return
    try:
        mtime = context.sandbox.resolve_workspace_path(relative_path).stat().st_mtime
    except OSError:
        return
    age_days = max(0, int((time.time() - float(mtime)) // SECONDS_PER_DAY))
    if age_days <= 1:
        return
    note = (
        "<system-reminder>This memory is %d days old. "
        "Memories are point-in-time observations, not live state -- "
        "claims about code behavior or file:line citations may be outdated. "
        "Verify against current code before asserting as fact.</system-reminder>\n"
    ) % age_days
    payload["memoryFreshness"] = {"ageDays": age_days, "note": note, **memory_metadata}
    payload["memoryFreshnessNote"] = note


def _memory_file_metadata(path: str) -> dict[str, str] | None:
    normalized = str(path or "").replace("\\", "/").lstrip("/")
    if not normalized.endswith(".md"):
        return None
    parts = [part for part in normalized.split("/") if part and part != "."]
    if len(parts) < 3:
        return None
    root = parts[0]
    category = parts[1]
    if root == ".agents" and category in AUTO_MEMORY_DIRS:
        return _auto_memory_metadata(parts[2:])
    if root in MEMORY_ROOTS and category == "session-memory":
        return {"memoryKind": "session", "scope": "session"}
    if root in MEMORY_ROOTS and category in AGENT_MEMORY_DIRS:
        return _agent_memory_metadata(category)
    if len(parts) >= 5 and root == ".agents" and category == "projects" and parts[3] == "memory":
        return _auto_memory_metadata(parts[4:])
    if len(parts) >= 5 and root == ".agents" and category == "projects" and parts[3] in AGENT_MEMORY_DIRS:
        return _agent_memory_metadata(parts[3])
    return None


def _auto_memory_metadata(tail_parts: list[str]) -> dict[str, str]:
    if tail_parts and tail_parts[0] == "team":
        return {"memoryKind": "team", "scope": "team"}
    return {"memoryKind": "auto", "scope": "personal"}


def _agent_memory_metadata(category: str) -> dict[str, str]:
    scope = "local" if category == "agent-memory-local" else "project"
    return {"memoryKind": "agent", "scope": scope}


def _is_image_path(path: str) -> bool:
    return Path(str(path or "")).suffix.lower() in IMAGE_EXTENSIONS


def _is_pdf_path(path: str) -> bool:
    return Path(str(path or "")).suffix.lower() == ".pdf"


def _is_notebook_path(path: str) -> bool:
    return Path(str(path or "")).suffix.lower() == ".ipynb"


def _read_image_file(context: ToolRuntimeContext, path: str) -> dict[str, Any]:
    resolved, relative_path, data = _read_binary_file_bytes(context, path, max_bytes=BINARY_READ_MAX_BYTES, kind="Image")
    media_type = _detect_image_media_type(data, resolved)
    if media_type is None:
        raise ValueError("Unsupported or invalid image file: %s" % path)
    return {
        "type": "image",
        "path": relative_path,
        "bytes": len(data),
        "mimeType": media_type,
        "file": {
            "filePath": relative_path,
            "base64": base64.b64encode(data).decode("ascii"),
            "type": media_type,
            "originalSize": len(data),
        },
    }


def _read_pdf_file(context: ToolRuntimeContext, path: str, pages: str | None = None) -> dict[str, Any]:
    resolved, relative_path, data = _read_binary_file_bytes(context, path, max_bytes=BINARY_READ_MAX_BYTES, kind="PDF")
    if not data.startswith(b"%PDF"):
        raise ValueError("Unsupported or invalid PDF file: %s" % path)
    if pages:
        start_page, end_page = _parse_pdf_pages(pages)
        return _extract_pdf_pages(
            resolved=resolved,
            relative_path=relative_path,
            original_size=len(data),
            start_page=start_page,
            end_page=end_page,
        )
    pdf_base64 = base64.b64encode(data).decode("ascii")
    return {
        "type": "pdf",
        "path": relative_path,
        "bytes": len(data),
        "mimeType": "application/pdf",
        "file": {
            "filePath": relative_path,
            "base64": pdf_base64,
            "originalSize": len(data),
        },
        "newMessages": [
            {
                "role": "user",
                "isMeta": True,
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": pdf_base64,
                        },
                    }
                ],
            }
        ],
    }


def _parse_pdf_pages(pages: str) -> tuple[int, int]:
    value = str(pages or "").strip()
    match = re.fullmatch(r"(\d+)(?:\s*-\s*(\d+))?", value)
    if match is None:
        raise ValueError(
            'Invalid pages parameter: "%s". Use formats like "1-5", "3", or "10-20". Pages are 1-indexed.' % value
        )
    start_page = int(match.group(1))
    end_page = int(match.group(2) or start_page)
    if start_page < 1 or end_page < start_page:
        raise ValueError(
            'Invalid pages parameter: "%s". Use formats like "1-5", "3", or "10-20". Pages are 1-indexed.' % value
        )
    if end_page - start_page + 1 > PDF_MAX_PAGES_PER_READ:
        raise ValueError('Page range "%s" exceeds maximum of %d pages per request. Please use a smaller range.' % (value, PDF_MAX_PAGES_PER_READ))
    return start_page, end_page


def _extract_pdf_pages(
    *,
    resolved: Path,
    relative_path: str,
    original_size: int,
    start_page: int,
    end_page: int,
) -> dict[str, Any]:
    executable = shutil.which("pdftoppm")
    if not executable:
        raise RuntimeError(
            "PDF page extraction requires poppler-utils: install `pdftoppm` with `brew install poppler` on macOS "
            "or `apt-get install poppler-utils` on Debian/Ubuntu."
        )
    output_dir = Path(tempfile.mkdtemp(prefix="agents-pdf-pages-"))
    output_prefix = output_dir / "page"
    command = [
        executable,
        "-jpeg",
        "-f",
        str(start_page),
        "-l",
        str(end_page),
        str(resolved),
        str(output_prefix),
    ]
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "pdftoppm failed").strip()
        raise RuntimeError("PDF page extraction failed: %s" % detail)
    image_files = sorted(output_dir.glob("*.jpg"))
    if not image_files:
        raise RuntimeError("PDF page extraction failed: no page images were produced")
    return {
        "type": "parts",
        "path": relative_path,
        "bytes": original_size,
        "mimeType": "application/pdf",
        "pages": "%d-%d" % (start_page, end_page) if start_page != end_page else str(start_page),
        "file": {
            "filePath": relative_path,
            "originalSize": original_size,
            "count": len(image_files),
            "outputDir": str(output_dir),
        },
        "newMessages": [
            {
                "role": "user",
                "isMeta": True,
                "content": _pdf_page_image_blocks(image_files),
            }
        ],
    }


def _pdf_page_image_blocks(image_files: list[Path]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for image_file in image_files:
        data = image_file.read_bytes()
        media_type = _detect_image_media_type(data, image_file) or "image/jpeg"
        blocks.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": base64.b64encode(data).decode("ascii"),
                },
            }
        )
    return blocks


def _read_notebook_file(context: ToolRuntimeContext, path: str, pages: str | None = None) -> dict[str, Any]:
    if pages:
        raise ValueError("pages is only supported for PDF files")
    decision = context.sandbox.authorize_file_read(path)
    if not decision.allowed:
        raise PermissionError(decision.reason)
    resolved = context.sandbox.resolve_workspace_path(path)
    if not resolved.is_file():
        raise FileNotFoundError(str(path))
    size = resolved.stat().st_size
    if size > NOTEBOOK_READ_MAX_BYTES:
        raise ValueError("Notebook file is too large to read inline: %s (%d bytes)" % (path, size))
    raw = resolved.read_text(encoding="utf-8")
    payload = json.loads(raw)
    cells = payload.get("cells")
    if not isinstance(cells, list):
        raise ValueError("Invalid notebook file: %s" % path)
    relative_path = context.sandbox.relative_workspace_path(resolved)
    record_file_read(
        context,
        relative_path,
        raw,
        encoding="utf-8",
        source="read",
        offset=1,
        limit=None,
        is_partial_view=False,
    )
    return {
        "type": "notebook",
        "path": relative_path,
        "bytes": size,
        "file": {
            "filePath": relative_path,
            "cells": cells,
        },
    }


def _read_binary_file_bytes(context: ToolRuntimeContext, path: str, *, max_bytes: int, kind: str) -> tuple[Path, str, bytes]:
    decision = context.sandbox.authorize_file_read(path)
    if not decision.allowed:
        raise PermissionError(decision.reason)
    resolved = context.sandbox.resolve_workspace_path(path)
    if not resolved.is_file():
        raise FileNotFoundError(str(path))
    size = resolved.stat().st_size
    if size > max_bytes:
        raise ValueError("%s file is too large to read inline: %s (%d bytes)" % (kind, path, size))
    return resolved, context.sandbox.relative_workspace_path(resolved), resolved.read_bytes()


def _detect_image_media_type(data: bytes, path: Path) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return "image/gif"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    fallback = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }.get(path.suffix.lower())
    return fallback if data else None
