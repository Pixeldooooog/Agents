from __future__ import annotations

from typing import Any

from agents.kernel.governance.tool_rules import normalize_tool_name
from agents.kernel.memory_paths import is_team_memory_path
from agents.kernel.schema import RuntimeEvent, ToolCall, ToolResult


def memory_access_events(call: ToolCall, result: ToolResult) -> list[RuntimeEvent]:
    if result.is_error:
        return []
    paths = sorted(_team_memory_write_paths(call))
    return [
        RuntimeEvent(
            type="team_memory_write",
            name=normalize_tool_name(call.name),
            payload={
                "path": path,
                "tool_name": call.name,
                "memoryKind": "team",
                "scope": "team",
                "sync_pending": True,
            },
        )
        for path in paths
    ]


def _team_memory_write_paths(call: ToolCall) -> set[str]:
    name = normalize_tool_name(call.name)
    arguments = dict(call.arguments or {})
    paths: set[str] = set()
    if name == "filesystem.write":
        _add_team_memory_path(paths, arguments.get("path") or arguments.get("file_path"))
    elif name == "patch.apply":
        _add_team_memory_path(paths, arguments.get("file_path"))
        for operation in _dict_items(arguments.get("edits")):
            _add_team_memory_path(paths, operation.get("path") or operation.get("file_path"))
        for operation in _dict_items(arguments.get("creates")):
            _add_team_memory_path(paths, operation.get("path") or operation.get("file_path"))
    return paths


def _add_team_memory_path(paths: set[str], value: Any) -> None:
    path = str(value or "")
    if path and is_team_memory_path(path):
        paths.add(path)


def _dict_items(value: Any) -> list[dict[str, Any]]:
    return [item for item in value or [] if isinstance(item, dict)]
