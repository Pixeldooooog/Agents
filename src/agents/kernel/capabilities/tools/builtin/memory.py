from __future__ import annotations

from dataclasses import replace
from typing import Any

from agents.kernel.capabilities.memory import MemoryRecord, MemoryScope
from agents.kernel.capabilities.tools.context import ToolRuntimeContext


MEMORY_SCOPE_VALUES = ["user", "agent", "workspace", "run"]

MEMORY_LIST_SCHEMA = {
    "type": "object",
    "properties": {
        "scope": {"type": "string", "enum": ["", *MEMORY_SCOPE_VALUES], "description": "Optional scope filter."},
        "query": {"type": "string", "description": "Optional content substring filter."},
        "limit": {"type": "integer", "minimum": 1, "maximum": 100},
    },
}

MEMORY_ADD_SCHEMA = {
    "type": "object",
    "properties": {
        "content": {"type": "string"},
        "scope": {"type": "string", "enum": MEMORY_SCOPE_VALUES},
        "metadata": {"type": "object", "additionalProperties": {"type": "string"}},
    },
    "required": ["content"],
}

MEMORY_EDIT_SCHEMA = {
    "type": "object",
    "properties": {
        "memory_id": {"type": "string", "description": "Memory id or unambiguous short id."},
        "content": {"type": "string"},
    },
    "required": ["memory_id", "content"],
}

MEMORY_FORGET_SCHEMA = {
    "type": "object",
    "properties": {
        "memory_id": {"type": "string", "description": "Memory id or unambiguous short id."},
    },
    "required": ["memory_id"],
}


async def memory_list(
    context: ToolRuntimeContext,
    scope: str = "",
    query: str = "",
    limit: int = 50,
) -> dict[str, Any]:
    records = await _visible_memories(context)
    wanted_scope = str(scope or "").strip()
    if wanted_scope:
        _memory_scope(wanted_scope)
        records = [record for record in records if record.scope.value == wanted_scope]
    wanted_query = str(query or "").strip().lower()
    if wanted_query:
        records = [record for record in records if wanted_query in record.content.lower()]
    limit = max(1, min(int(limit or 50), 100))
    return {
        "memories": [_memory_payload(record) for record in records[-limit:]],
        "count": min(len(records), limit),
        "total": len(records),
    }


async def memory_add(
    context: ToolRuntimeContext,
    content: str,
    scope: str = "workspace",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    workspace = _workspace(context)
    memory_scope = _memory_scope(scope or "workspace")
    agent_id, workspace_id = _scope_ids(context, memory_scope)
    record = MemoryRecord.create(
        tenant_id=workspace.tenant_id,
        user_id=workspace.user_id,
        agent_id=agent_id,
        workspace_id=workspace_id,
        scope=memory_scope,
        content=_required_text(content, "content"),
        metadata={"source": "tool", **_string_metadata(metadata), **_run_metadata(context, memory_scope)},
    )
    await _memory_store(context).save(record)
    return {"memory": _memory_payload(record)}


async def memory_edit(context: ToolRuntimeContext, memory_id: str, content: str) -> dict[str, Any]:
    match = await _resolve_memory(context, memory_id)
    updated = replace(match, content=_required_text(content, "content"))
    await _memory_store(context).save(updated)
    return {"memory": _memory_payload(updated)}


async def memory_forget(context: ToolRuntimeContext, memory_id: str) -> dict[str, Any]:
    match = await _resolve_memory(context, memory_id)
    await _memory_store(context).delete(match.memory_id)
    return {"memory": _memory_payload(match), "forgotten": True}


def _memory_store(context: ToolRuntimeContext):
    store = getattr(context, "memory_store", None)
    if store is None:
        raise RuntimeError("memory store is not available")
    return store


def _workspace(context: ToolRuntimeContext):
    workspace = context.workspace
    if not getattr(workspace, "tenant_id", "") or not getattr(workspace, "user_id", ""):
        raise RuntimeError("memory identity scope is not available")
    return workspace


async def _visible_memories(context: ToolRuntimeContext) -> list[MemoryRecord]:
    workspace = _workspace(context)
    return await _memory_store(context).list_for_context(
        workspace.tenant_id,
        workspace.user_id,
        agent_id=getattr(workspace, "agent_id", ""),
        workspace_id=getattr(workspace, "workspace_id", ""),
    )


async def _resolve_memory(context: ToolRuntimeContext, memory_id: str) -> MemoryRecord:
    target = _required_text(memory_id, "memory_id")
    direct = await _memory_store(context).load(target)
    if direct is not None and direct in await _visible_memories(context):
        return direct
    matches = [record for record in await _visible_memories(context) if _memory_id_matches(record.memory_id, target)]
    if not matches:
        raise KeyError("memory not found: %s" % target)
    if len(matches) > 1:
        raise ValueError("memory id is ambiguous: %s" % target)
    return matches[0]


def _scope_ids(context: ToolRuntimeContext, scope: MemoryScope) -> tuple[str, str]:
    workspace = _workspace(context)
    if scope == MemoryScope.USER:
        return "", ""
    if scope == MemoryScope.AGENT:
        return getattr(workspace, "agent_id", ""), ""
    return getattr(workspace, "agent_id", ""), getattr(workspace, "workspace_id", "")


def _run_metadata(context: ToolRuntimeContext, scope: MemoryScope) -> dict[str, str]:
    if scope != MemoryScope.RUN:
        return {}
    run_id = str(getattr(context, "current_run_id", "") or "")
    return {"run_id": run_id} if run_id else {}


def _memory_scope(value: str) -> MemoryScope:
    try:
        return MemoryScope(str(value or "workspace"))
    except ValueError as exc:
        raise ValueError("unknown memory scope: %s" % value) from exc


def _memory_payload(memory: MemoryRecord) -> dict[str, Any]:
    return {
        "memory_id": memory.memory_id,
        "short_id": _short_memory_id(memory.memory_id),
        "scope": memory.scope.value,
        "content": memory.content,
        "agent_id": memory.agent_id,
        "workspace_id": memory.workspace_id,
        "metadata": dict(memory.metadata),
        "created_at": memory.created_at,
        "updated_at": memory.updated_at,
    }


def _memory_id_matches(memory_id: str, target: str) -> bool:
    return memory_id == target or _short_memory_id(memory_id).startswith(str(target).replace("mem_", "", 1))


def _short_memory_id(memory_id: str) -> str:
    return str(memory_id).replace("mem_", "", 1)[:12]


def _string_metadata(metadata: dict[str, Any] | None) -> dict[str, str]:
    return {str(key): str(value) for key, value in dict(metadata or {}).items()}


def _required_text(value: Any, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError("%s is required" % name)
    return text
