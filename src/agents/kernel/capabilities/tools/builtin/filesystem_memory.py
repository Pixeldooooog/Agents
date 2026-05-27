from __future__ import annotations

import time
from typing import Any

from agents.kernel.capabilities.tools.context import ToolRuntimeContext


SECONDS_PER_DAY = 86400
MEMORY_ROOTS = {".agents", ".claude"}
AUTO_MEMORY_DIRS = {"memory", "memories"}
AGENT_MEMORY_DIRS = {"agent-memory", "agent-memory-local"}


def add_memory_freshness(context: ToolRuntimeContext, payload: dict[str, Any]) -> None:
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
