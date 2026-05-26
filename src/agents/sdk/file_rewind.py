from __future__ import annotations

import difflib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agents.kernel.capabilities.sandbox.text import (
    BINARY_SAMPLE_BYTES,
    decode_text_bytes,
    detect_text_encoding,
    public_encoding_name,
)
from agents.kernel.schema import RuntimeEvent
from agents.kernel.state.runs import RunRecord
from agents.sdk.event_projection import _first_non_empty, _tool_result_payload_data
from agents.sdk.types import SDKOptions


MAX_SDK_SEED_READ_BYTES = 200000


@dataclass
class _RewindFileEntry:
    path: str
    before: str = ""
    before_bytes: bytes | None = None
    existed: bool = True
    encoding: str = "utf-8"
    insertions: int = 0
    deletions: int = 0
    mode: int | None = None


def _record_cwd(record: RunRecord) -> str:
    if record.metadata.get("sdk_cwd"):
        return str(record.metadata["sdk_cwd"])
    workspace = record.spec.get("workspace") if isinstance(record.spec.get("workspace"), dict) else {}
    if isinstance(workspace, dict):
        return str(workspace.get("path") or workspace.get("root") or "")
    return ""


def _event_matches_message_id(event: RuntimeEvent, message_id: str) -> bool:
    candidates = {
        str(event.payload.get("uuid") or ""),
        str(event.payload.get("message_id") or ""),
        str(event.payload.get("id") or ""),
        str(event.payload.get("tool_call_id") or ""),
        str(event.payload.get("approval_id") or ""),
    }
    raw = event.raw if isinstance(event.raw, dict) else {}
    candidates.update(
        {
            str(raw.get("uuid") or ""),
            str(raw.get("message_id") or ""),
            str(raw.get("id") or ""),
        }
    )
    return message_id in candidates


def _rewind_entries_after_message(
    records: list[RunRecord],
    message_id: str,
) -> tuple[list[_RewindFileEntry], list[str], bool]:
    found_message = False
    entries_by_path: dict[str, _RewindFileEntry] = {}
    unsupported_paths: set[str] = set()
    read_cache: dict[str, str] = {}
    for record in sorted(records, key=lambda item: item.created_at):
        for event in record.events:
            if not found_message:
                if _event_matches_message_id(event, message_id):
                    found_message = True
                continue
            if event.type != "tool_result":
                continue
            payload = _rewind_tool_result_payload_data(event.payload)
            read_path, read_content = _read_content_from_tool_result(event, payload)
            if read_path:
                read_cache[read_path] = read_content
                continue
            entries, unsupported = _rewind_entries_from_tool_result(event, payload, read_cache)
            unsupported_paths.update(path for path in unsupported if path not in entries_by_path)
            for entry in entries:
                if entry.path in unsupported_paths:
                    continue
                existing = entries_by_path.get(entry.path)
                if existing is None:
                    entries_by_path[entry.path] = entry
                    continue
                existing.insertions += entry.insertions
                existing.deletions += entry.deletions
    entries = [entries_by_path[path] for path in sorted(entries_by_path)]
    return entries, sorted(unsupported_paths), found_message


def _read_content_from_tool_result(event: RuntimeEvent, payload: dict[str, Any]) -> tuple[str, str]:
    if str(event.name or "") not in {"filesystem.read", "Read"}:
        return "", ""
    file_payload = payload.get("file") if isinstance(payload.get("file"), dict) else {}
    path = _rewind_path_value(file_payload.get("filePath") or payload.get("path"))
    content = file_payload.get("content") if "content" in file_payload else payload.get("content")
    if not path or not isinstance(content, str):
        return "", ""
    if payload.get("truncated") or payload.get("isPartialView"):
        return "", ""
    return path, content


def _rewind_tool_result_payload_data(payload: dict[str, Any]) -> dict[str, Any]:
    data = _tool_result_payload_data(payload)
    nested = data.get("data")
    if not isinstance(nested, dict):
        return data
    merged = dict(nested)
    if isinstance(data.get("_meta"), dict) and "_meta" not in merged:
        merged["_meta"] = dict(data["_meta"])
    return merged


def _rewind_entries_from_tool_result(
    event: RuntimeEvent,
    payload: dict[str, Any],
    read_cache: dict[str, str],
) -> tuple[list[_RewindFileEntry], list[str]]:
    name = str(event.name or "")
    if payload.get("dry_run") is True or payload.get("changed") is False:
        return [], []
    if name in {"patch.apply", "Edit"}:
        return _rewind_entries_from_patch_payload(payload)
    if name in {"notebook.edit", "NotebookEdit"}:
        entry = _rewind_entry_from_notebook_payload(payload)
        return ([entry], []) if entry is not None else ([], [])
    if name in {"filesystem.write", "Write"}:
        entry, unsupported = _rewind_entry_from_write_payload(payload, read_cache)
        return ([entry], []) if entry is not None else ([], unsupported)
    return [], []


def _rewind_entries_from_patch_payload(payload: dict[str, Any]) -> tuple[list[_RewindFileEntry], list[str]]:
    entries: list[_RewindFileEntry] = []
    unsupported_paths: set[str] = set()
    supported_paths: set[str] = set()
    path = _rewind_path_value(payload.get("filePath") or payload.get("path"))
    before = payload.get("originalFile")
    if path and isinstance(before, str):
        after = _patch_after_content(payload, before)
        insertions, deletions = _change_stats(payload.get("structuredPatch"), before, after)
        entries.append(
            _RewindFileEntry(
                path=path,
                before=before,
                existed=True,
                encoding=str(payload.get("encoding") or "utf-8"),
                insertions=insertions,
                deletions=deletions,
            )
        )
        supported_paths.add(path)

    files = payload.get("files") if isinstance(payload.get("files"), list) else []
    for item in files:
        if not isinstance(item, dict):
            continue
        item_path = _rewind_path_value(item.get("path") or item.get("filePath"))
        if not item_path or item_path in supported_paths:
            continue
        action = str(item.get("action") or "")
        if action == "create":
            insertions, deletions = _change_stats(_structured_patch_for_path(payload, item_path), "", None)
            entries.append(
                _RewindFileEntry(
                    path=item_path,
                    before="",
                    existed=False,
                    encoding=str(payload.get("encoding") or "utf-8"),
                    insertions=insertions,
                    deletions=deletions,
                )
            )
            supported_paths.add(item_path)
        elif action == "edit":
            unsupported_paths.add(item_path)

    if not files and payload.get("structuredPatches") and not supported_paths:
        for item in payload.get("structuredPatches") or []:
            if isinstance(item, dict):
                item_path = _rewind_path_value(item.get("filePath") or item.get("path"))
                if item_path:
                    unsupported_paths.add(item_path)
    return entries, sorted(unsupported_paths)


def _rewind_entry_from_notebook_payload(payload: dict[str, Any]) -> _RewindFileEntry | None:
    path = _rewind_path_value(payload.get("notebook_path") or payload.get("path") or payload.get("filePath"))
    before = payload.get("original_file") if "original_file" in payload else payload.get("originalFile")
    after = payload.get("updated_file") if "updated_file" in payload else payload.get("updatedFile")
    if not path or not isinstance(before, str):
        return None
    insertions, deletions = _change_stats(payload.get("structuredPatch"), before, after if isinstance(after, str) else None)
    return _RewindFileEntry(
        path=path,
        before=before,
        existed=True,
        encoding=str(payload.get("encoding") or "utf-8"),
        insertions=insertions,
        deletions=deletions,
    )


def _rewind_entry_from_write_payload(
    payload: dict[str, Any],
    read_cache: dict[str, str],
) -> tuple[_RewindFileEntry | None, list[str]]:
    file_payload = payload.get("file") if isinstance(payload.get("file"), dict) else {}
    path = _rewind_path_value(payload.get("path") or payload.get("filePath") or file_payload.get("filePath"))
    if not path:
        return None, []
    original_present, original = _first_present(payload, "originalFile", "original_file", "oldContent", "old_content")
    after = _first_string(
        payload,
        "content",
        "updatedFile",
        "updated_file",
        "newContent",
        "new_content",
    )
    encoding = str(payload.get("encoding") or payload.get("charset") or "utf-8")
    if original_present:
        existed = isinstance(original, str)
        before = original if isinstance(original, str) else ""
        insertions, deletions = _change_stats(payload.get("structuredPatch"), before, after)
        return (
            _RewindFileEntry(
                path=path,
                before=before,
                existed=existed,
                encoding=encoding,
                insertions=insertions,
                deletions=deletions,
            ),
            [],
        )
    if str(payload.get("type") or "").lower() == "create":
        insertions, deletions = _change_stats(payload.get("structuredPatch"), "", after)
        return (
            _RewindFileEntry(
                path=path,
                before="",
                existed=False,
                encoding=encoding,
                insertions=insertions,
                deletions=deletions,
            ),
            [],
        )
    safety = payload.get("safety") if isinstance(payload.get("safety"), dict) else {}
    existed = bool(safety.get("required_prior_read"))
    encoding = str(payload.get("encoding") or safety.get("encoding") or "utf-8")
    if not existed:
        return _RewindFileEntry(path=path, before="", existed=False, encoding=encoding), []
    before = read_cache.get(path)
    if before is None:
        return None, [path]
    return _RewindFileEntry(path=path, before=before, existed=True, encoding=encoding), []


def _first_present(payload: dict[str, Any], *keys: str) -> tuple[bool, Any]:
    for key in keys:
        if key in payload:
            return True, payload[key]
    return False, None


def _first_string(payload: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str):
            return value
    return None


def _rewind_response_payload(entries: list[_RewindFileEntry]) -> dict[str, Any]:
    ordered = sorted(entries, key=lambda item: item.path)
    return {
        "canRewind": True,
        "filesChanged": [entry.path for entry in ordered],
        "insertions": sum(max(0, entry.insertions) for entry in ordered),
        "deletions": sum(max(0, entry.deletions) for entry in ordered),
    }


def _rewind_workspace_root(options: SDKOptions, records: list[RunRecord]) -> Path:
    root = str(options.cwd or "")
    if not root:
        root = _first_non_empty(_record_cwd(record) for record in reversed(records))
    return Path(root or ".").resolve()


def _safe_workspace_path(root: Path, path: str) -> Path:
    target = Path(path)
    resolved = target.resolve() if target.is_absolute() else (root / target).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError("path escapes workspace: %s" % path) from exc
    return resolved


def _safe_rewind_path(root: Path, path: str) -> Path:
    try:
        return _safe_workspace_path(root, path)
    except ValueError as exc:
        raise ValueError("rewind path escapes workspace: %s" % path) from exc


def _apply_rewind_entry(entry: _RewindFileEntry, target: Path) -> None:
    if not entry.existed:
        if target.exists():
            if target.is_dir():
                raise ValueError("cannot rewind file path because it is a directory: %s" % entry.path)
            target.unlink()
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    if entry.before_bytes is not None:
        target.write_bytes(entry.before_bytes)
    else:
        target.write_text(entry.before, encoding=entry.encoding or "utf-8")
    if entry.mode is not None:
        os.chmod(target, entry.mode)


def _rewind_path_value(value: Any) -> str:
    path = str(value or "").strip()
    if path.startswith("./"):
        path = path[2:]
    return path


def _read_state_seed_key(options: SDKOptions) -> str:
    return str(options.session_id or "")


def _is_seed_observation_stale(disk_mtime: float, observed_mtime: float) -> bool:
    observed = float(observed_mtime or 0.0)
    if observed > 10_000_000_000:
        return int(disk_mtime * 1000) > int(observed)
    return disk_mtime > observed


def _read_seed_text(path: Path) -> tuple[str, str]:
    with path.open("rb") as handle:
        data = handle.read(MAX_SDK_SEED_READ_BYTES + 1)
    if len(data) > MAX_SDK_SEED_READ_BYTES:
        raise ValueError("file is too large to seed read state: %s" % path)
    encoding = detect_text_encoding(path, data[:BINARY_SAMPLE_BYTES])
    return decode_text_bytes(data, encoding), public_encoding_name(encoding)


def _patch_after_content(payload: dict[str, Any], before: str) -> str | None:
    old = payload.get("oldString")
    new = payload.get("newString")
    if isinstance(old, str) and isinstance(new, str) and old in before:
        return before.replace(old, new, 1)
    return None


def _structured_patch_for_path(payload: dict[str, Any], path: str) -> list[dict[str, Any]] | None:
    patches = payload.get("structuredPatches")
    if not isinstance(patches, list):
        return None
    for item in patches:
        if not isinstance(item, dict):
            continue
        item_path = _rewind_path_value(item.get("filePath") or item.get("path"))
        if item_path == path and isinstance(item.get("hunks"), list):
            return list(item["hunks"])
    return None


def _change_stats(patch: Any, before: str, after: str | None) -> tuple[int, int]:
    insertions, deletions = _structured_patch_stats(patch)
    if insertions or deletions or after is None:
        return insertions, deletions
    return _text_change_stats(before, after)


def _structured_patch_stats(patch: Any) -> tuple[int, int]:
    if not isinstance(patch, list):
        return 0, 0
    insertions = 0
    deletions = 0
    for hunk in patch:
        if not isinstance(hunk, dict):
            continue
        for line in hunk.get("lines") or []:
            text = str(line)
            if text.startswith("+"):
                insertions += 1
            elif text.startswith("-"):
                deletions += 1
    return insertions, deletions


def _text_change_stats(before: str, after: str) -> tuple[int, int]:
    insertions = 0
    deletions = 0
    matcher = difflib.SequenceMatcher(a=before.splitlines(), b=after.splitlines(), autojunk=False)
    for tag, old_start, old_end, new_start, new_end in matcher.get_opcodes():
        if tag in {"replace", "delete"}:
            deletions += old_end - old_start
        if tag in {"replace", "insert"}:
            insertions += new_end - new_start
    return insertions, deletions
