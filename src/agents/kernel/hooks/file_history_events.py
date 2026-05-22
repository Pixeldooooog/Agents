from __future__ import annotations

from typing import Any

from agents.kernel.governance.tool_rules import normalize_tool_name
from agents.kernel.schema import RuntimeEvent, ToolCall, ToolResult

WriteRecord = tuple[str, str]


def file_history_write_events(call: ToolCall, result: ToolResult) -> list[RuntimeEvent]:
    if result.is_error:
        return []
    canonical_name = normalize_tool_name(call.name)
    raw = _mapping(result.raw)
    if raw.get("dry_run") is True or raw.get("changed") is False:
        return []
    records = _write_records(canonical_name, _mapping(call.arguments), raw)
    return [
        RuntimeEvent(
            type="file_history_write",
            name=canonical_name,
            payload={
                "path": path,
                "operation": operation,
                "tool_name": call.name,
                "canonical_tool": canonical_name,
                "checkpoint_pending": True,
                "source": "tool_result",
            },
        )
        for path, operation in records
    ]


def _write_records(
    canonical_name: str,
    arguments: dict[str, Any],
    raw: dict[str, Any],
) -> list[WriteRecord]:
    if canonical_name == "filesystem.write":
        path = _first_text(
            raw.get("filePath"),
            raw.get("file_path"),
            raw.get("path"),
            arguments.get("path"),
            arguments.get("file_path"),
        )
        operation = _first_text(raw.get("type"), raw.get("action")) or "write"
        return _dedupe_records([(path, operation)])
    if canonical_name == "patch.apply":
        records = _patch_records(raw)
        if records:
            return records
        return _dedupe_records(
            [
                *(_argument_operation_records(arguments.get("edits"), "edit")),
                *(_argument_operation_records(arguments.get("creates"), "create")),
                (_first_text(arguments.get("file_path"), arguments.get("path")), "edit"),
            ]
        )
    if canonical_name == "notebook.edit":
        path = _first_text(
            raw.get("notebook_path"),
            raw.get("filePath"),
            raw.get("file_path"),
            raw.get("path"),
            arguments.get("notebook_path"),
            arguments.get("file_path"),
            arguments.get("path"),
        )
        operation = _first_text(raw.get("edit_mode"), arguments.get("edit_mode")) or "edit"
        return _dedupe_records([(path, operation)])
    return []


def _patch_records(raw: dict[str, Any]) -> list[WriteRecord]:
    files = raw.get("files")
    records: list[WriteRecord] = []
    for item in _dict_items(files):
        records.append(
            (
                _first_text(item.get("path"), item.get("filePath"), item.get("file_path")),
                _first_text(item.get("action")) or "edit",
            )
        )
    if records:
        return _dedupe_records(records)
    return _dedupe_records(
        [
            (
                _first_text(raw.get("filePath"), raw.get("file_path"), raw.get("path")),
                "edit",
            )
        ]
    )


def _argument_operation_records(value: Any, operation: str) -> list[WriteRecord]:
    return [
        (_first_text(item.get("path"), item.get("file_path"), item.get("filePath")), operation)
        for item in _dict_items(value)
    ]


def _dedupe_records(records: list[WriteRecord]) -> list[WriteRecord]:
    seen: set[str] = set()
    output: list[WriteRecord] = []
    for path, operation in records:
        if not path or path in seen:
            continue
        seen.add(path)
        output.append((path, operation or "write"))
    return output


def _first_text(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value:
            return value
    return ""


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _dict_items(value: Any) -> list[dict[str, Any]]:
    return [item for item in value or [] if isinstance(item, dict)]
