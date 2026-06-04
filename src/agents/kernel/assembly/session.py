from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import Any, Optional

from agents.kernel.capabilities.memory import MemoryStore
from agents.kernel.capabilities.sandbox.store import SandboxStore
from agents.kernel.capabilities.sandbox.recording import SandboxToolExecutionRecorder
from agents.kernel.capabilities.web import create_web_search_provider
from agents.kernel.assembly.active_tools import resolve_session_active_tools
from agents.kernel.assembly.plugins import plugin_context_fragments
from agents.kernel.assembly.session_state import (
    hydrate_hooks,
    hydrate_mcp_config,
    hydrate_schedules,
    hydrate_session_state,
    hydrate_teams,
    mcp_auth_headers,
    mcp_config_records,
    memory_fragments,
)
from agents.kernel.assembly.runtime_limits import runtime_max_tool_iterations
from agents.kernel.assembly.spec_overrides import effective_spec_from_session_state, skill_registry_with_session_state
from agents.kernel.config import resolve_model_client_config
from agents.kernel.context.builder import ContextBuilder
from agents.kernel.context.compaction_model import ModelContextCompactor
from agents.kernel.context.sources import build_context_pack
from agents.kernel.specs import AgentSpec
from agents.kernel.hooks import AgentHooks, CompositeHooks, SessionStateHooks, hooks_from_settings
from agents.kernel.capabilities import load_configured_skills
from agents.kernel.mcp.loading import load_configured_mcp
from agents.kernel.mcp.elicitation_runtime import build_mcp_elicitation_complete_handler
from agents.kernel.mcp.list_changed_runtime import build_mcp_list_changed_handler
from agents.kernel.mcp.oauth_runtime import authenticate_mcp_oauth_server
from agents.kernel.models import ModelClient
from agents.kernel.runtime import AgentRuntime, AgentSession
from agents.kernel.runtime.turns import ModelToolUseSummaryGenerator
from agents.kernel.runtime.checkpoints import CheckpointStore
from agents.kernel.governance import build_tool_permission_policy
from agents.kernel.state.workspaces.factory import resolve_workspace
from agents.kernel.state.artifacts import ArtifactBlobStore, ArtifactStore
from agents.kernel.capabilities.tools import ToolRegistry, ToolRuntimeContext, register_builtin_tools


async def create_agent_session_async(
    settings: Any,
    spec: AgentSpec,
    hooks: Optional[AgentHooks] = None,
    checkpoint_store: Optional[CheckpointStore] = None,
    memory_store: Optional[MemoryStore] = None,
    schedule_store: Optional[Any] = None,
    team_store: Optional[Any] = None,
    hook_store: Optional[Any] = None,
    mcp_config_store: Optional[Any] = None,
    mcp_auth_store: Optional[Any] = None,
    mcp_elicitation_handler: Optional[Any] = None,
    sdk_mcp_handlers: Optional[dict[str, Any]] = None,
    session_state_store: Optional[Any] = None,
    sandbox_store: Optional[SandboxStore] = None,
    artifact_store: Optional[ArtifactStore] = None,
    artifact_blob_store: Optional[ArtifactBlobStore] = None,
    task_store: Optional[Any] = None,
    run_service: Optional[Any] = None,
    agent_profile_store: Optional[Any] = None,
    task_id: str = "",
    subagent_depth: int = 0,
) -> AgentSession:
    resolved_spec = spec.with_workspace_defaults()
    registry = ToolRegistry(max_concurrent=settings.agent.MAX_CONCURRENT_TOOLS, tool_timeout=settings.agent.TOOL_TIMEOUT)
    skill_registry = load_configured_skills(settings, skill_names=resolved_spec.skills)
    workspace = resolve_workspace(
        settings,
        tenant_id=resolved_spec.workspace.tenant_id,
        user_id=resolved_spec.workspace.user_id,
        agent_id=resolved_spec.workspace.agent_id,
        workspace_id=resolved_spec.workspace.workspace_id,
        workspace_path=resolved_spec.workspace.path,
    )
    tool_context = ToolRuntimeContext.from_settings(
        settings,
        workspace,
        sandbox_store=sandbox_store,
        artifact_store=artifact_store,
        artifact_blob_store=artifact_blob_store,
        task_store=task_store,
        run_service=run_service,
        agent_profile_store=agent_profile_store,
        memory_store=memory_store,
        schedule_store=schedule_store,
        team_store=team_store,
        hook_store=hook_store,
        mcp_config_store=mcp_config_store,
        mcp_auth_store=mcp_auth_store,
        mcp_elicitation_handler=mcp_elicitation_handler,
        sdk_mcp_handlers=sdk_mcp_handlers,
        session_state_store=session_state_store,
        skill_registry=skill_registry,
        agent_spec=resolved_spec,
        agent_session_factory=_subagent_session_factory(
            settings,
            hooks=hooks,
            checkpoint_store=checkpoint_store,
            memory_store=memory_store,
            schedule_store=schedule_store,
            team_store=team_store,
            hook_store=hook_store,
            mcp_config_store=mcp_config_store,
            mcp_auth_store=mcp_auth_store,
            mcp_elicitation_handler=mcp_elicitation_handler,
            sdk_mcp_handlers=sdk_mcp_handlers,
            session_state_store=session_state_store,
            sandbox_store=sandbox_store,
            artifact_store=artifact_store,
            artifact_blob_store=artifact_blob_store,
            task_store=task_store,
            run_service=run_service,
            agent_profile_store=agent_profile_store,
            subagent_depth=subagent_depth,
        ),
        subagent_depth=subagent_depth,
        task_id=task_id,
    )
    registry.set_execution_observer(SandboxToolExecutionRecorder(tool_context, sandbox_store))
    web_provider = create_web_search_provider(settings)
    builtin_tools = register_builtin_tools(registry, tool_context, web_provider=web_provider)
    await hydrate_session_state(tool_context)
    mcp_records = await mcp_config_records(tool_context)
    await hydrate_mcp_config(tool_context, records=mcp_records)
    auth_headers = await mcp_auth_headers(tool_context, records=mcp_records)
    mcp_load_kwargs: dict[str, Any] = {
        "roots": [str(tool_context.workspace.path)],
        "records": mcp_records if mcp_records else None,
    }
    if sdk_mcp_handlers:
        mcp_load_kwargs["sdk_mcp_handlers"] = sdk_mcp_handlers
    if mcp_elicitation_handler is not None:
        mcp_load_kwargs["elicitation_handler"] = mcp_elicitation_handler
        mcp_load_kwargs["elicitation_complete_handler"] = build_mcp_elicitation_complete_handler(tool_context)
    mcp_load_kwargs["list_changed_handler"] = build_mcp_list_changed_handler(tool_context, registry)
    mcp_load_kwargs["oauth_authenticator"] = lambda server, arguments: authenticate_mcp_oauth_server(
        tool_context,
        server,
        arguments,
    )
    if auth_headers:
        mcp_load_kwargs["auth_headers"] = auth_headers

    tool_context.mcp_providers = await load_configured_mcp(settings, registry, **mcp_load_kwargs)
    skill_registry = skill_registry_with_session_state(settings, skill_registry, tool_context)
    tool_context.skill_registry = skill_registry
    effective_spec = effective_spec_from_session_state(resolved_spec, tool_context)
    tool_context.agent_spec = effective_spec
    active_tools = resolve_session_active_tools(
        settings,
        skill_registry,
        effective_spec,
        builtin_tools,
        registry,
        tool_context,
    )
    tool_context.enabled_tools = list(active_tools)
    await hydrate_schedules(tool_context)
    await hydrate_teams(tool_context)
    await hydrate_hooks(tool_context)
    memory_context_fragments = await memory_fragments(
        settings,
        memory_store,
        tool_context.workspace,
        memory_profile=effective_spec.memory_profile,
    )
    system_prompt = settings.agent.SYSTEM_PROMPT if effective_spec.system_prompt is None else effective_spec.system_prompt
    if tool_context.system_prompt_overridden:
        system_prompt = tool_context.system_prompt_override
    context_pack = build_context_pack(
        system_prompt=system_prompt,
        skill_registry=skill_registry,
        enabled_tools=active_tools,
        workspace=tool_context.workspace,
        agent_metadata=effective_spec.metadata,
        memory_fragments=memory_context_fragments,
        extension_fragments=plugin_context_fragments(settings, tool_context),
    )
    compiled_context = ContextBuilder().compile(context_pack, budget_tokens=settings.agent.MAX_CONTEXT_TOKENS)
    active_hooks = _session_hooks(hooks if hooks is not None else hooks_from_settings(settings), tool_context)
    permission_policy = build_tool_permission_policy(effective_spec)
    config = resolve_model_client_config(
        settings,
        protocol=effective_spec.model.protocol,
        model=effective_spec.model.model,
        base_url=effective_spec.model.base_url,
        api_key=effective_spec.model.api_key,
    )
    model_client = ModelClient(config)
    summary_generator = _tool_use_summary_generator(settings, config)
    context_compactor = _context_compactor(settings, config)
    runtime = AgentRuntime(
        model_client=model_client,
        tools=registry,
        protocol=config.protocol,
        model=config.model,
        enabled_tools=active_tools,
        max_tool_iterations=runtime_max_tool_iterations(settings, effective_spec),
        hooks=active_hooks,
        permission_policy=permission_policy,
        checkpoint_store=checkpoint_store,
        tool_summary_generator=summary_generator,
    )
    return AgentSession(
        runtime=runtime,
        system_prompt=compiled_context.system_text,
        max_context_tokens=settings.agent.MAX_CONTEXT_TOKENS,
        compaction_target_tokens=int(getattr(settings.agent, "CONTEXT_COMPACTION_TARGET_TOKENS", 0) or 0) or None,
        context_trace=compiled_context.trace,
        workspace=tool_context.workspace,
        tool_context=tool_context,
        context_compactor=context_compactor,
    )


def create_agent_session(
    settings: Any,
    spec: AgentSpec,
    hooks: Optional[AgentHooks] = None,
    checkpoint_store: Optional[CheckpointStore] = None,
    memory_store: Optional[MemoryStore] = None,
    schedule_store: Optional[Any] = None,
    team_store: Optional[Any] = None,
    hook_store: Optional[Any] = None,
    mcp_config_store: Optional[Any] = None,
    mcp_auth_store: Optional[Any] = None,
    mcp_elicitation_handler: Optional[Any] = None,
    sdk_mcp_handlers: Optional[dict[str, Any]] = None,
    session_state_store: Optional[Any] = None,
    sandbox_store: Optional[SandboxStore] = None,
    artifact_store: Optional[ArtifactStore] = None,
    artifact_blob_store: Optional[ArtifactBlobStore] = None,
    task_store: Optional[Any] = None,
    run_service: Optional[Any] = None,
    agent_profile_store: Optional[Any] = None,
    task_id: str = "",
    subagent_depth: int = 0,
) -> AgentSession:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(
            create_agent_session_async(
                settings,
                spec,
                hooks=hooks,
                checkpoint_store=checkpoint_store,
                memory_store=memory_store,
                schedule_store=schedule_store,
                team_store=team_store,
                hook_store=hook_store,
                mcp_config_store=mcp_config_store,
                mcp_auth_store=mcp_auth_store,
                mcp_elicitation_handler=mcp_elicitation_handler,
                sdk_mcp_handlers=sdk_mcp_handlers,
                session_state_store=session_state_store,
                sandbox_store=sandbox_store,
                artifact_store=artifact_store,
                artifact_blob_store=artifact_blob_store,
                task_store=task_store,
                run_service=run_service,
                agent_profile_store=agent_profile_store,
                task_id=task_id,
                subagent_depth=subagent_depth,
            )
        )
    raise RuntimeError("create_agent_session cannot run inside an active event loop; use create_agent_session_async")


def _tool_use_summary_generator(settings: Any, config: Any) -> ModelToolUseSummaryGenerator | None:
    summary_model = str(getattr(settings.agent, "TOOL_USE_SUMMARY_MODEL", "") or "").strip()
    if not summary_model:
        return None
    summary_config = replace(config, model=summary_model, max_tokens=min(int(config.max_tokens or 64), 128))
    return ModelToolUseSummaryGenerator(
        ModelClient(summary_config),
        protocol=summary_config.protocol,
        model=summary_config.model,
    )


def _context_compactor(settings: Any, config: Any) -> ModelContextCompactor | None:
    compaction_model = str(getattr(settings.agent, "CONTEXT_COMPACTION_MODEL", "") or "").strip()
    if not compaction_model:
        return None
    compaction_config = replace(config, model=compaction_model, max_tokens=min(int(config.max_tokens or 2048), 2048))
    return ModelContextCompactor(
        ModelClient(compaction_config),
        protocol=compaction_config.protocol,
        model=compaction_config.model,
        max_summary_tokens=compaction_config.max_tokens,
    )


def _session_hooks(base_hooks: AgentHooks, tool_context: ToolRuntimeContext) -> AgentHooks:
    session_hooks = SessionStateHooks(tool_context.hook_registry, store=tool_context.hook_store, workspace=tool_context.workspace)
    if isinstance(base_hooks, CompositeHooks):
        return CompositeHooks([session_hooks, *base_hooks.hooks])
    return CompositeHooks([session_hooks, base_hooks])


def _subagent_session_factory(
    settings: Any,
    *,
    hooks: Optional[AgentHooks],
    checkpoint_store: Optional[CheckpointStore],
    memory_store: Optional[MemoryStore],
    schedule_store: Optional[Any],
    team_store: Optional[Any],
    hook_store: Optional[Any],
    mcp_config_store: Optional[Any],
    mcp_auth_store: Optional[Any],
    mcp_elicitation_handler: Optional[Any],
    sdk_mcp_handlers: Optional[dict[str, Any]],
    session_state_store: Optional[Any],
    sandbox_store: Optional[SandboxStore],
    artifact_store: Optional[ArtifactStore],
    artifact_blob_store: Optional[ArtifactBlobStore],
    task_store: Optional[Any],
    run_service: Optional[Any],
    agent_profile_store: Optional[Any],
    subagent_depth: int,
):
    async def create_child(spec: AgentSpec, task_id: str = "") -> AgentSession:
        return await create_agent_session_async(
            settings,
            spec,
            hooks=hooks,
            checkpoint_store=checkpoint_store,
            memory_store=memory_store,
            schedule_store=schedule_store,
            team_store=team_store,
            hook_store=hook_store,
            mcp_config_store=mcp_config_store,
            mcp_auth_store=mcp_auth_store,
            mcp_elicitation_handler=mcp_elicitation_handler,
            sdk_mcp_handlers=sdk_mcp_handlers,
            session_state_store=session_state_store,
            sandbox_store=sandbox_store,
            artifact_store=artifact_store,
            artifact_blob_store=artifact_blob_store,
            task_store=task_store,
            run_service=run_service,
            agent_profile_store=agent_profile_store,
            task_id=task_id,
            subagent_depth=subagent_depth + 1,
        )

    return create_child
