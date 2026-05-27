from __future__ import annotations

from typing import Any

from agents.kernel.capabilities.tools.context import ToolRuntimeContext
from agents.kernel.hooks import HOOK_ACTIONS, HOOK_EVENTS
from agents.kernel.hooks.store import delete_hook_record, hydrate_hook_registry, save_hook_record


HOOK_EVENTS_SCHEMA = {"type": "object", "properties": {}}

HOOK_LIST_SCHEMA = {
    "type": "object",
    "properties": {
        "event": {"type": "string", "description": "Optional event filter."},
        "enabled": {"type": "boolean", "description": "Optional enabled-state filter."},
        "limit": {"type": "integer", "minimum": 1, "maximum": 100},
    },
}

HOOK_ADD_SCHEMA = {
    "type": "object",
    "properties": {
        "event": {"type": "string", "enum": HOOK_EVENTS},
        "name": {"type": "string"},
        "action": {"type": "string", "enum": HOOK_ACTIONS},
        "content": {"type": "string"},
        "enabled": {"type": "boolean"},
        "tool": {"type": "string", "description": "Optional tool matcher for pre/post hooks, e.g. filesystem.* or Bash(git *)."},
        "metadata": {"type": "object", "additionalProperties": {"type": "string"}},
    },
    "required": ["event", "name", "action"],
}

HOOK_DELETE_SCHEMA = {
    "type": "object",
    "properties": {
        "hook_id": {"type": "string", "description": "Hook id or unambiguous short id."},
    },
    "required": ["hook_id"],
}


def hook_events(context: ToolRuntimeContext) -> dict[str, Any]:
    return {"events": list(HOOK_EVENTS), "actions": list(HOOK_ACTIONS)}


async def hook_list(
    context: ToolRuntimeContext,
    event: str = "",
    enabled: bool | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    await _hydrate_hooks(context)
    hooks = context.hook_registry.list(event=event, enabled=enabled, limit=limit)
    return {"hooks": [hook.to_dict() for hook in hooks], "count": len(hooks)}


async def hook_add(
    context: ToolRuntimeContext,
    event: str,
    name: str,
    action: str,
    content: str = "",
    enabled: bool = True,
    tool: str = "",
    metadata: dict[str, str] | None = None,
) -> dict[str, Any]:
    hook = context.hook_registry.add(
        event=event,
        name=name,
        action=action,
        content=content,
        enabled=enabled,
        tool=tool,
        metadata={"source": "tool", **_string_metadata(metadata)},
    )
    await _save_hook(context, hook)
    return {"hook": hook.to_dict()}


async def hook_delete(context: ToolRuntimeContext, hook_id: str) -> dict[str, Any]:
    await _hydrate_hooks(context)
    hook = context.hook_registry.delete(hook_id)
    await _delete_hook(context, hook.hook_id)
    return {"hook": hook.to_dict(), "deleted": True}


async def _hydrate_hooks(context: ToolRuntimeContext) -> None:
    await hydrate_hook_registry(context.hook_registry, getattr(context, "hook_store", None), context.workspace)


async def _save_hook(context: ToolRuntimeContext, hook) -> None:
    await save_hook_record(hook, getattr(context, "hook_store", None), context.workspace)


async def _delete_hook(context: ToolRuntimeContext, hook_id: str) -> None:
    await delete_hook_record(hook_id, getattr(context, "hook_store", None), context.workspace)


def _string_metadata(metadata: dict[str, Any] | None) -> dict[str, str]:
    return {str(key): str(value) for key, value in dict(metadata or {}).items()}
