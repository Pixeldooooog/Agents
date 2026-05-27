from __future__ import annotations

import json
from typing import Any


FILE_UNCHANGED_STUB = (
    "File unchanged since last read. The content from the earlier filesystem.read tool result "
    "in this conversation is still current; refer to that instead of re-reading."
)


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
    return _format_text_result(payload)


def text_read_payload(payload: dict[str, Any]) -> dict[str, Any]:
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


def _format_text_result(payload: dict[str, Any]) -> str:
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


def _format_numbered_lines(content: str, start_line: int) -> str:
    lines = content.splitlines()
    return "\n".join("%d\t%s" % (index + start_line, line) for index, line in enumerate(lines))
