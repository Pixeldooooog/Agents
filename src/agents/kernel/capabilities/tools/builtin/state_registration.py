from __future__ import annotations

from agents.kernel.capabilities.tools.builtin.hooks import (
    HOOK_ADD_SCHEMA,
    HOOK_DELETE_SCHEMA,
    HOOK_EVENTS_SCHEMA,
    HOOK_LIST_SCHEMA,
    hook_add,
    hook_delete,
    hook_events,
    hook_list,
)
from agents.kernel.capabilities.tools.builtin.memory import (
    MEMORY_ADD_SCHEMA,
    MEMORY_EDIT_SCHEMA,
    MEMORY_FORGET_SCHEMA,
    MEMORY_LIST_SCHEMA,
    memory_add,
    memory_edit,
    memory_forget,
    memory_list,
)
from agents.kernel.capabilities.tools.builtin.permissions import (
    PERMISSION_EXPLAIN_SCHEMA,
    PERMISSION_REMOVE_RULE_SCHEMA,
    PERMISSION_RULE_SCHEMA,
    PERMISSION_SOURCES_SCHEMA,
    PERMISSION_STATUS_SCHEMA,
    permission_add_rule,
    permission_explain,
    permission_remove_rule,
    permission_sources,
    permission_status,
)
from agents.kernel.capabilities.tools.builtin.session_context import (
    CONTEXT_COMPACT_SCHEMA,
    CONTEXT_MESSAGES_SCHEMA,
    CONTEXT_REWIND_SCHEMA,
    CONTEXT_TRACE_SCHEMA,
    SESSION_EXPORT_SCHEMA,
    SESSION_STATUS_SCHEMA,
    SESSION_SUMMARY_SCHEMA,
    context_compact,
    context_messages,
    context_rewind,
    context_trace,
    session_export,
    session_status,
    session_summary,
)
from agents.kernel.capabilities.tools.context import ToolRuntimeContext
from agents.kernel.capabilities.tools.registry import ToolRegistry


def register_state_tools(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    _register_session_context(registry, context)
    _register_permissions(registry, context)
    _register_hooks(registry, context)
    _register_memory(registry, context)


def _register_session_context(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    registry.register(
        "session.status",
        "Read current session, workspace, model, enabled tool, and context-window status.",
        SESSION_STATUS_SCHEMA,
        lambda: session_status(context),
        metadata={"risk": "low", "model_call": True},
    )
    registry.register(
        "session.export",
        "Export current session messages to a workspace JSON or Markdown file.",
        SESSION_EXPORT_SCHEMA,
        lambda path="", format="json", include_system=False: session_export(
            context,
            path=path,
            format=format,
            include_system=include_system,
        ),
        metadata={"risk": "medium", "writes_files": True, "model_call": True},
    )
    registry.register(
        "session.summary",
        "Summarize recent current-session messages for handoff or status review.",
        SESSION_SUMMARY_SCHEMA,
        lambda include_system=False, max_messages=50, max_chars=2000: session_summary(
            context,
            include_system=include_system,
            max_messages=max_messages,
            max_chars=max_chars,
        ),
        metadata={"risk": "low", "model_call": True},
    )
    registry.register(
        "context.trace",
        "Read compiled context trace items and their sources.",
        CONTEXT_TRACE_SCHEMA,
        lambda include_text=False, max_chars=240: context_trace(
            context,
            include_text=include_text,
            max_chars=max_chars,
        ),
        metadata={"risk": "low", "model_call": True},
    )
    registry.register(
        "context.messages",
        "Read recent session message summaries.",
        CONTEXT_MESSAGES_SCHEMA,
        lambda include_system=False, max_messages=50, max_chars=240: context_messages(
            context,
            include_system=include_system,
            max_messages=max_messages,
            max_chars=max_chars,
        ),
        metadata={"risk": "low", "model_call": True},
    )
    registry.register(
        "context.compact",
        "Compact older session messages using the configured context compaction strategy.",
        CONTEXT_COMPACT_SCHEMA,
        lambda target_tokens=None: context_compact(context, target_tokens=target_tokens),
        metadata={"risk": "medium", "writes_state": True, "model_call": True},
    )
    registry.register(
        "context.rewind",
        "Remove recent non-system messages from the current session context.",
        CONTEXT_REWIND_SCHEMA,
        lambda drop_last=1: context_rewind(context, drop_last=drop_last),
        metadata={"risk": "medium", "writes_state": True, "model_call": True},
    )


def _register_permissions(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    registry.register(
        "permission.status",
        "Read current tool permission profile and configured approval/deny lists.",
        PERMISSION_STATUS_SCHEMA,
        lambda: permission_status(context),
        metadata={"risk": "low", "model_call": True},
    )
    registry.register(
        "permission.sources",
        "Read tool permission rules grouped by source and behavior.",
        PERMISSION_SOURCES_SCHEMA,
        lambda: permission_sources(context),
        metadata={"risk": "low", "model_call": True},
    )
    registry.register(
        "permission.explain",
        "Explain the permission decision and impact for a hypothetical tool call.",
        PERMISSION_EXPLAIN_SCHEMA,
        lambda tool, arguments=None: permission_explain(context, tool=tool, arguments=arguments),
        metadata={"risk": "low", "model_call": True},
    )
    registry.register(
        "permission.add_rule",
        "Add a session-scoped allow, deny, or ask rule for a tool.",
        PERMISSION_RULE_SCHEMA,
        lambda behavior, tool: permission_add_rule(context, behavior=behavior, tool=tool),
        metadata={"risk": "medium", "writes_state": True, "model_call": True},
    )
    registry.register(
        "permission.remove_rule",
        "Remove session-scoped permission rules for a tool.",
        PERMISSION_REMOVE_RULE_SCHEMA,
        lambda tool, behavior="": permission_remove_rule(context, tool=tool, behavior=behavior),
        metadata={"risk": "medium", "writes_state": True, "model_call": True},
    )


def _register_hooks(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    registry.register(
        "hook.events",
        "List supported session hook events and actions.",
        HOOK_EVENTS_SCHEMA,
        lambda: hook_events(context),
        metadata={"risk": "low", "model_call": True},
    )
    registry.register(
        "hook.list",
        "List session hooks configured for the current agent session.",
        HOOK_LIST_SCHEMA,
        lambda event="", enabled=None, limit=50: hook_list(context, event=event, enabled=enabled, limit=limit),
        metadata={"risk": "low", "model_call": True},
    )
    registry.register(
        "hook.add",
        "Add a session hook that can append request guidance, record events, or gate tool use.",
        HOOK_ADD_SCHEMA,
        lambda event, name, action, content="", enabled=True, tool="", metadata=None: hook_add(
            context,
            event=event,
            name=name,
            action=action,
            content=content,
            enabled=enabled,
            tool=tool,
            metadata=metadata,
        ),
        metadata={"risk": "medium", "writes_state": True, "model_call": True},
    )
    registry.register(
        "hook.delete",
        "Delete a session hook by id or short id.",
        HOOK_DELETE_SCHEMA,
        lambda hook_id: hook_delete(context, hook_id=hook_id),
        metadata={"risk": "medium", "writes_state": True, "model_call": True},
    )


def _register_memory(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    registry.register(
        "memory.list",
        "List memories visible to the current user, agent, and workspace scope.",
        MEMORY_LIST_SCHEMA,
        lambda scope="", query="", limit=50: memory_list(context, scope=scope, query=query, limit=limit),
        metadata={"risk": "low"},
    )
    registry.register(
        "memory.add",
        "Save a memory for future context retrieval.",
        MEMORY_ADD_SCHEMA,
        lambda content, scope="workspace", metadata=None: memory_add(
            context,
            content=content,
            scope=scope,
            metadata=metadata,
        ),
        metadata={"risk": "medium", "writes_state": True, "model_call": True},
    )
    registry.register(
        "memory.edit",
        "Update a visible memory by id or short id.",
        MEMORY_EDIT_SCHEMA,
        lambda memory_id, content: memory_edit(context, memory_id=memory_id, content=content),
        metadata={"risk": "medium", "writes_state": True, "model_call": True},
    )
    registry.register(
        "memory.forget",
        "Delete a visible memory by id or short id.",
        MEMORY_FORGET_SCHEMA,
        lambda memory_id: memory_forget(context, memory_id=memory_id),
        metadata={"risk": "medium", "writes_state": True, "model_call": True},
    )
