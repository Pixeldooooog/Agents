from __future__ import annotations

import base64
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from agents.kernel.capabilities.sandbox.text import format_file_size
from agents.kernel.capabilities.tools.builtin.file_safety import record_file_read
from agents.kernel.capabilities.tools.builtin.filesystem_limits import (
    effective_text_read_max_bytes,
    validate_text_read_tokens,
)
from agents.kernel.capabilities.tools.builtin.image_metadata import detect_image_media_type, image_dimensions
from agents.kernel.capabilities.tools.context import ToolRuntimeContext


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
BINARY_READ_MAX_BYTES = 5 * 1024 * 1024
NOTEBOOK_READ_MAX_BYTES = 2 * 1024 * 1024
PDF_MAX_PAGES_PER_READ = 20


def is_image_path(path: str) -> bool:
    return Path(str(path or "")).suffix.lower() in IMAGE_EXTENSIONS


def is_pdf_path(path: str) -> bool:
    return Path(str(path or "")).suffix.lower() == ".pdf"


def is_notebook_path(path: str) -> bool:
    return Path(str(path or "")).suffix.lower() == ".ipynb"


def read_image_file(context: ToolRuntimeContext, path: str) -> dict[str, Any]:
    _, relative_path, data = _read_binary_file_bytes(context, path, max_bytes=BINARY_READ_MAX_BYTES, kind="Image")
    if not data:
        raise ValueError("Image file is empty: %s" % path)
    media_type = detect_image_media_type(data)
    if media_type is None:
        raise ValueError("Unsupported or invalid image file: %s" % path)
    dimensions = image_dimensions(data, media_type)
    file_payload = {
        "filePath": relative_path,
        "base64": base64.b64encode(data).decode("ascii"),
        "type": media_type,
        "originalSize": len(data),
    }
    if dimensions:
        file_payload["dimensions"] = dimensions
    return {
        "type": "image",
        "path": relative_path,
        "bytes": len(data),
        "mimeType": media_type,
        "file": file_payload,
    }


def read_pdf_file(context: ToolRuntimeContext, path: str, pages: str | None = None) -> dict[str, Any]:
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


def read_notebook_file(
    context: ToolRuntimeContext,
    path: str,
    pages: str | None = None,
    max_bytes: int | None = None,
) -> dict[str, Any]:
    if pages:
        raise ValueError("pages is only supported for PDF files")
    decision = context.sandbox.authorize_file_read(path)
    if not decision.allowed:
        raise PermissionError(decision.reason)
    resolved = context.sandbox.resolve_workspace_path(path)
    if not resolved.is_file():
        raise FileNotFoundError(str(path))
    size = resolved.stat().st_size
    hard_max_bytes = min(NOTEBOOK_READ_MAX_BYTES, effective_text_read_max_bytes(context, max_bytes))
    if size > NOTEBOOK_READ_MAX_BYTES:
        raise ValueError("Notebook file is too large to read inline: %s (%d bytes)" % (path, size))
    raw = resolved.read_text(encoding="utf-8")
    payload = json.loads(raw)
    cells = payload.get("cells")
    if not isinstance(cells, list):
        raise ValueError("Invalid notebook file: %s" % path)
    relative_path = context.sandbox.relative_workspace_path(resolved)
    cells_json = json.dumps(cells, ensure_ascii=False)
    cells_size = len(cells_json.encode("utf-8"))
    if cells_size > hard_max_bytes:
        raise ValueError(_notebook_content_too_large_message(path, cells_size, hard_max_bytes))
    validate_text_read_tokens(context, cells_json, path)
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
        raise ValueError(
            'Page range "%s" exceeds maximum of %d pages per request. Please use a smaller range.'
            % (value, PDF_MAX_PAGES_PER_READ)
        )
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
        media_type = detect_image_media_type(data) or "image/jpeg"
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


def _notebook_content_too_large_message(path: str, size_in_bytes: int, max_size_bytes: int) -> str:
    return (
        "Notebook content (%s) exceeds maximum allowed size (%s). Use shell.run with jq to read specific portions:\n"
        '  cat "%s" | jq \'.cells[:20]\' # First 20 cells\n'
        '  cat "%s" | jq \'.cells[100:120]\' # Cells 100-120\n'
        '  cat "%s" | jq \'.cells | length\' # Count total cells\n'
        '  cat "%s" | jq \'.cells[] | select(.cell_type=="code") | .source\' # All code sources'
    ) % (
        format_file_size(size_in_bytes),
        format_file_size(max_size_bytes),
        path,
        path,
        path,
        path,
    )


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
