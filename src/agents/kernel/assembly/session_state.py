from __future__ import annotations

import json
from typing import Any, Optional

from agents.kernel.capabilities.memory import MemoryStore
from agents.kernel.capabilities.tools import ToolRuntimeContext
from agents.kernel.capabilities.tools.builtin.worktree import restore_active_worktree_session
from agents.kernel.context.memory import MemoryContextRetriever, MemoryRetrievalScope
from agents.kernel.mcp.auth import mcp_authorization_headers_for_scope


async def memory_fragments(
    settings: Any,
    memory_store: Optional[MemoryStore],
    workspace,
    *,
    memory_profile: str = "",
) -> list:
    if memory_store is None or not workspace.tenant_id or not workspace.user_id:
        return []
    limit = int(getattr(settings.agent, "MEMORY_CONTEXT_LIMIT", 20) or 0)
    if limit <= 0:
        return []
    return await MemoryContextRetriever(memory_store).fragments_for_scope(
        MemoryRetrievalScope(
            tenant_id=workspace.tenant_id,
            user_id=workspace.user_id,
            agent_id=workspace.agent_id,
            workspace_id=workspace.workspace_id,
            limit=limit,
            profile=memory_profile,
        )
    )


async def hydrate_schedules(tool_context: ToolRuntimeContext) -> None:
    store = getattr(tool_context, "schedule_store", None)
    if store is None:
        return
    workspace = tool_context.workspace
    schedules = await store.list_for_scope(
        workspace.tenant_id,
        user_id=workspace.user_id,
        agent_id=workspace.agent_id,
        workspace_id=workspace.workspace_id,
    )
    tool_context.scheduled_tasks = {schedule.schedule_id: schedule.to_dict() for schedule in schedules}


async def hydrate_teams(tool_context: ToolRuntimeContext) -> None:
    store = getattr(tool_context, "team_store", None)
    if store is None:
        return
    workspace = tool_context.workspace
    teams = await store.list_teams(
        workspace.tenant_id,
        user_id=workspace.user_id,
        agent_id=workspace.agent_id,
        workspace_id=workspace.workspace_id,
    )
    tool_context.teams = {team.team_id: team.to_dict() for team in teams}


async def hydrate_hooks(tool_context: ToolRuntimeContext) -> None:
    store = getattr(tool_context, "hook_store", None)
    if store is None:
        return
    workspace = tool_context.workspace
    hooks = await store.list_for_scope(
        workspace.tenant_id,
        user_id=workspace.user_id,
        agent_id=workspace.agent_id,
        workspace_id=workspace.workspace_id,
    )
    tool_context.hook_registry.replace_all(hooks)


async def mcp_config_records(tool_context: ToolRuntimeContext) -> list[Any]:
    store = getattr(tool_context, "mcp_config_store", None)
    if store is None:
        return []
    workspace = tool_context.workspace
    return await store.list_for_scope(
        workspace.tenant_id,
        user_id=workspace.user_id,
        agent_id=workspace.agent_id,
        workspace_id=workspace.workspace_id,
    )


async def hydrate_mcp_config(tool_context: ToolRuntimeContext, records: list[Any] | None = None) -> None:
    if records is None:
        records = await mcp_config_records(tool_context)
    active = next((record for record in records if record.enabled), None)
    if active is None:
        return
    mcp = getattr(tool_context.settings, "mcp", None)
    if mcp is None:
        return
    mcp.SERVER_NAME = active.name
    mcp.SERVER_COMMAND = active.command
    mcp.SERVER_TRANSPORT = active.transport
    mcp.SERVER_URL = active.url
    mcp.SERVER_HEADERS = dict(active.headers)
    mcp.SERVER_HEADERS_JSON = json.dumps(active.headers, ensure_ascii=False, sort_keys=True) if active.headers else ""
    mcp.EXECUTION_MODE = active.execution_mode
    mcp.SANDBOX_PROFILE = active.sandbox_profile
    mcp.AUTH_REQUIRED = active.auth_required
    mcp.AUTH_URL = active.auth_url
    mcp.AUTH_STATUS = active.auth_status
    mcp.AUTH_MESSAGE = active.auth_message


async def mcp_auth_headers(tool_context: ToolRuntimeContext, records: list[Any] | None = None) -> dict[str, str]:
    store = getattr(tool_context, "mcp_auth_store", None)
    if store is None:
        return {}
    workspace = tool_context.workspace
    names = mcp_auth_names(tool_context.settings, records)
    return await mcp_authorization_headers_for_scope(
        store,
        names=names,
        tenant_id=workspace.tenant_id,
        user_id=workspace.user_id,
        agent_id=workspace.agent_id,
        workspace_id=workspace.workspace_id,
    )


def mcp_auth_names(settings: Any, records: list[Any] | None) -> list[str]:
    if records:
        return [str(getattr(record, "name", "") or "") for record in records if bool(getattr(record, "enabled", True))]
    mcp = getattr(settings, "mcp", None)
    if mcp is None:
        return []
    command = str(getattr(mcp, "SERVER_COMMAND", "") or "").strip()
    transport = str(getattr(mcp, "SERVER_TRANSPORT", "stdio") or "stdio")
    url = str(getattr(mcp, "SERVER_URL", "") or "").strip()
    if transport == "stdio" and not command:
        return []
    if transport != "stdio" and not url:
        return []
    return [str(getattr(mcp, "SERVER_NAME", "") or "default")]


async def hydrate_session_state(tool_context: ToolRuntimeContext) -> None:
    store = getattr(tool_context, "session_state_store", None)
    if store is None:
        return
    workspace = tool_context.workspace
    record = await store.load_for_scope(
        workspace.tenant_id,
        user_id=workspace.user_id,
        agent_id=workspace.agent_id,
        workspace_id=workspace.workspace_id,
    )
    if record is None:
        return
    tool_context.todos = [dict(item) for item in record.todos]
    tool_context.plan_mode = bool(record.plan_mode)
    tool_context.plan_text = record.plan_text
    tool_context.plan_allowed_prompts = [dict(item) for item in record.plan_allowed_prompts]
    tool_context.system_prompt_override = record.system_prompt_override
    tool_context.system_prompt_overridden = bool(record.system_prompt_overridden)
    tool_context.permission_profile_override = record.permission_profile_override
    tool_context.permission_mode_override = record.permission_mode_override
    tool_context.permission_restrict_allowed_tools = bool(record.permission_restrict_allowed_tools)
    tool_context.permission_allowed_tools_override = list(record.permission_allowed_tools_override)
    tool_context.permission_denied_tools_override = list(record.permission_denied_tools_override)
    tool_context.approval_required_tools_override = list(record.approval_required_tools_override)
    tool_context.permission_overridden = bool(record.permission_overridden)
    tool_context.enabled_skills = set(record.enabled_skills)
    tool_context.enabled_plugins = set(record.enabled_plugins)
    tool_context.skill_tools = {name: list(tools) for name, tools in record.skill_tools.items()}
    tool_context.plugin_tools = {name: list(tools) for name, tools in record.plugin_tools.items()}
    restore_active_worktree_session(tool_context, record.active_worktree_session)
    tool_context.config_overrides = dict(record.metadata)
