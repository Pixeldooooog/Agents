from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from agents.kernel.schema import RuntimeEvent


@dataclass(frozen=True)
class FileHistoryEntry:
    path: str
    before: str = ""
    existed: bool = True
    encoding: str = "utf-8"


def entries_from_tool_result(event: RuntimeEvent) -> list[FileHistoryEntry]:
    if event.type != "tool_result":
        return []
    payload = _tool_result_data(event.payload)
    if payload.get("dry_run") is True or payload.get("changed") is False:
        return []
    name = str(event.name or "")
    if name in {"filesystem.write", "Write"}:
        entry = _write_entry(payload)
        return [entry] if entry is not None else []
    if name in {"patch.apply", "Edit"}:
        return _patch_entries(payload)
    if name in {"notebook.edit", "NotebookEdit"}:
        entry = _notebook_entry(payload)
        return [entry] if entry is not None else []
    return []


def path_value(value: Any) -> str:
    path = str(value or "").strip()
    return path[2:] if path.startswith("./") else path


def _write_entry(payload: dict[str, Any]) -> FileHistoryEntry | None:
    file_payload = payload.get("file") if isinstance(payload.get("file"), dict) else {}
    path = path_value(payload.get("filePath") or payload.get("path") or file_payload.get("filePath"))
    if not path:
        return None
    present, original = _first_present(payload, "originalFile", "original_file", "oldContent", "old_content")
    if present:
        return FileHistoryEntry(
            path=path,
            before=original if isinstance(original, str) else "",
            existed=isinstance(original, str),
            encoding=str(payload.get("encoding") or payload.get("charset") or "utf-8"),
        )
    if str(payload.get("type") or "").lower() == "create":
        return FileHistoryEntry(path=path, existed=False)
    return None


def _patch_entries(payload: dict[str, Any]) -> list[FileHistoryEntry]:
    path = path_value(payload.get("filePath") or payload.get("path"))
    original = payload.get("originalFile")
    if path and isinstance(original, str):
        return [FileHistoryEntry(path=path, before=original, encoding=str(payload.get("encoding") or "utf-8"))]
    entries: list[FileHistoryEntry] = []
    for item in _dict_items(payload.get("files")):
        item_path = path_value(item.get("path") or item.get("filePath"))
        if item_path and str(item.get("action") or "") == "create":
            entries.append(FileHistoryEntry(path=item_path, existed=False))
    return entries


def _notebook_entry(payload: dict[str, Any]) -> FileHistoryEntry | None:
    path = path_value(payload.get("notebook_path") or payload.get("filePath") or payload.get("path"))
    original = payload.get("original_file") if "original_file" in payload else payload.get("originalFile")
    if not path or not isinstance(original, str):
        return None
    return FileHistoryEntry(path=path, before=original, encoding=str(payload.get("encoding") or "utf-8"))


def _tool_result_data(payload: dict[str, Any]) -> dict[str, Any]:
    raw = payload.get("raw") if isinstance(payload, dict) else None
    if isinstance(raw, dict):
        nested = raw.get("data")
        return dict(nested) if isinstance(nested, dict) else dict(raw)
    if isinstance(raw, str):
        parsed = _json_object(raw)
        if parsed:
            nested = parsed.get("data")
            return dict(nested) if isinstance(nested, dict) else parsed
    return {}


def _json_object(value: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _first_present(payload: dict[str, Any], *keys: str) -> tuple[bool, Any]:
    for key in keys:
        if key in payload:
            return True, payload[key]
    return False, None


def _dict_items(value: Any) -> list[dict[str, Any]]:
    return [item for item in value or [] if isinstance(item, dict)]
