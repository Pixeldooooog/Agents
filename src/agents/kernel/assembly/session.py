from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from pathlib import Path
from typing import Any, Optional

from agents.kernel.capabilities.memory import MemoryStore
from agents.kernel.capabilities.sandbox.store import SandboxStore
from agents.kernel.capabilities.sandbox.recording import SandboxToolExecutionRecorder
from agents.kernel.capabilities.skills import SkillLoader, SkillRegistry
from agents.kernel.capabilities.web import create_web_search_provider
from agents.kernel.config import AgentConfigError, resolve_model_client_config
from agents.kernel.context.builder import ContextBuilder
from agents.kernel.context.memory import MemoryContextRetriever, MemoryRetrievalScope
from agents.kernel.context.pack import ContextFragment, ContextLayer, ContextScope
from agents.kernel.context.sources import build_context_pack
from agents.kernel.specs import AgentSpec
from agents.kernel.hooks import AgentHooks, CompositeHooks, SessionStateHooks, hooks_from_settings
from agents.kernel.capabilities import load_configured_mcp, load_configured_skills, resolve_active_tools
from agents.kernel.models import ModelClient
from agents.kernel.runtime import AgentRuntime, AgentSession
from agents.kernel.runtime.checkpoints import CheckpointStore
from agents.kernel.governance import build_tool_permission_policy
from agents.kernel.governance.tool_rules import matching_blanket_tool_rule
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
    await _hydrate_mcp_config(tool_context)
    tool_context.mcp_providers = await load_configured_mcp(settings, registry, roots=[str(workspace.path)])

    await _hydrate_session_state(tool_context)
    skill_registry = _skill_registry_with_session_state(settings, skill_registry, tool_context)
    tool_context.skill_registry = skill_registry
    effective_spec = _effective_spec_from_session_state(resolved_spec, tool_context)
    tool_context.agent_spec = effective_spec
    active_tools = _merge_unique(
        _resolve_active_tools(settings, skill_registry, effective_spec.enabled_tools, builtin_tools),
        _managed_extension_tools(tool_context),
        _plugin_enabled_tools(settings, tool_context),
    )
    if _has_structured_output_schema(effective_spec):
        active_tools = _merge_unique(active_tools, ["StructuredOutput"])
    active_tools = _filter_denied_active_tools(active_tools, effective_spec.tool_permissions.denied_tools)
    _validate_active_tools(active_tools, registry)
    tool_context.enabled_tools = list(active_tools)
    await _hydrate_schedules(tool_context)
    await _hydrate_teams(tool_context)
    await _hydrate_hooks(tool_context)
    memory_fragments = await _memory_fragments(settings, memory_store, workspace)
    system_prompt = settings.agent.SYSTEM_PROMPT if effective_spec.system_prompt is None else effective_spec.system_prompt
    if tool_context.system_prompt_overridden:
        system_prompt = tool_context.system_prompt_override
    context_pack = build_context_pack(
        system_prompt=system_prompt,
        skill_registry=skill_registry,
        enabled_tools=active_tools,
        workspace=workspace,
        memory_fragments=memory_fragments,
        extension_fragments=_plugin_context_fragments(settings, tool_context),
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
    runtime = AgentRuntime(
        model_client=ModelClient(config),
        tools=registry,
        protocol=config.protocol,
        model=config.model,
        enabled_tools=active_tools,
        max_tool_iterations=settings.agent.MAX_TOOL_ITERATIONS,
        hooks=active_hooks,
        permission_policy=permission_policy,
        checkpoint_store=checkpoint_store,
    )
    return AgentSession(
        runtime=runtime,
        system_prompt=compiled_context.system_text,
        max_context_tokens=settings.agent.MAX_CONTEXT_TOKENS,
        compaction_target_tokens=int(getattr(settings.agent, "CONTEXT_COMPACTION_TARGET_TOKENS", 0) or 0) or None,
        context_trace=compiled_context.trace,
        workspace=workspace,
        tool_context=tool_context,
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


def _resolve_active_tools(settings: Any, skill_registry, enabled_tools: Optional[list[str]], builtin_tools: list[str]) -> list[str]:
    if enabled_tools is not None:
        return resolve_active_tools(settings, skill_registry, enabled_tools)
    configured_tools = str(getattr(settings.agent, "ENABLED_TOOLS", "") or "").strip()
    active_tools = resolve_active_tools(settings, skill_registry, None)
    if configured_tools:
        return active_tools
    builtin_defaults = [name for name in _csv_setting(getattr(settings.agent, "BUILTIN_TOOLS", "")) if name in builtin_tools]
    return _merge_unique(builtin_defaults, active_tools)


def _validate_active_tools(active_tools: list[str], registry: ToolRegistry) -> None:
    registered = set(registry.names())
    unknown = sorted({name for name in active_tools if name not in registered})
    if unknown:
        raise AgentConfigError("unknown enabled tool(s): %s" % ", ".join(unknown))


def _filter_denied_active_tools(active_tools: list[str], denied_rules: list[str]) -> list[str]:
    if not denied_rules:
        return list(active_tools)
    return [tool for tool in active_tools if not any(matching_blanket_tool_rule(rule, tool) for rule in denied_rules)]


def _has_structured_output_schema(spec: AgentSpec) -> bool:
    metadata = getattr(spec, "metadata", {}) or {}
    return isinstance(metadata.get("structured_output_schema"), dict)


def _skill_registry_with_session_state(settings: Any, skill_registry: SkillRegistry, tool_context: ToolRuntimeContext) -> SkillRegistry:
    base_names = skill_registry.names()
    persisted = [name for name in _merge_unique(list(getattr(tool_context, "enabled_skills", set()) or [])) if name not in base_names]
    if not persisted:
        return skill_registry
    loader = SkillLoader(settings.server.ROOT_PATH)
    skills = list(skill_registry.skills)
    seen = {skill.name for skill in skills}
    for name in persisted:
        try:
            loaded = SkillRegistry.load(loader, [name])
        except FileNotFoundError:
            continue
        for skill in loaded.skills:
            if skill.name in seen:
                continue
            seen.add(skill.name)
            skills.append(skill)
    return SkillRegistry(skills)


def _managed_extension_tools(tool_context: ToolRuntimeContext) -> list[str]:
    groups: list[list[str]] = []
    for mapping_name in ("skill_tools", "plugin_tools"):
        mapping = dict(getattr(tool_context, mapping_name, {}) or {})
        groups.extend([list(tools or []) for tools in mapping.values()])
    return _merge_unique(*groups)


def _plugin_enabled_tools(settings: Any, tool_context: ToolRuntimeContext) -> list[str]:
    enabled = sorted({str(name) for name in getattr(tool_context, "enabled_plugins", set()) or set() if str(name)})
    if not enabled:
        return []
    manifests = _plugin_manifests(settings, tool_context)
    groups = []
    for plugin_name in enabled:
        manifest = manifests.get(plugin_name)
        if manifest is None:
            continue
        raw = dict(manifest.get("raw") or {})
        groups.append([str(tool) for tool in raw.get("tools", []) or [] if str(tool)])
    return _merge_unique(*groups)


def _plugin_context_fragments(settings: Any, tool_context: ToolRuntimeContext) -> list[ContextFragment]:
    fragments: list[ContextFragment] = []
    enabled = sorted({str(name) for name in getattr(tool_context, "enabled_plugins", set()) or set() if str(name)})
    if not enabled:
        return fragments
    manifests = _plugin_manifests(settings, tool_context)
    for plugin_name in enabled:
        manifest = manifests.get(plugin_name)
        if manifest is None:
            continue
        for index, text in enumerate(_plugin_prompt_fragments(manifest)):
            if not text.strip():
                continue
            fragments.append(
                ContextFragment(
                    id="plugin.%s.%s" % (plugin_name, index),
                    layer=ContextLayer.SKILLS,
                    text=text.strip(),
                    source="plugin:%s" % plugin_name,
                    priority=55,
                    scope=ContextScope.SESSION,
                )
            )
    return fragments


def _plugin_manifests(settings: Any, tool_context: ToolRuntimeContext) -> dict[str, dict[str, Any]]:
    roots = _unique_paths(
        [
            getattr(tool_context.workspace, "path", ""),
            getattr(getattr(settings, "server", None), "ROOT_PATH", ""),
        ]
    )
    manifests: dict[str, dict[str, Any]] = {}
    for root in roots:
        for manifest_path in _plugin_manifest_paths(root):
            try:
                raw = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            plugin_dir = manifest_path.parent.parent if manifest_path.parent.name == ".codex-plugin" else manifest_path.parent
            plugin_name = str(raw.get("name") or plugin_dir.name)
            manifests.setdefault(plugin_name, {"raw": raw, "path": manifest_path, "plugin_dir": plugin_dir})
    return manifests


def _plugin_manifest_paths(root: Path) -> list[Path]:
    paths: list[Path] = []
    for plugins_dir in [root / ".agents" / "plugins", root / "plugins"]:
        if not plugins_dir.exists():
            continue
        paths.extend(sorted(plugins_dir.glob("*/.codex-plugin/plugin.json")))
        paths.extend(sorted(plugins_dir.glob("*/plugin.json")))
    return paths


def _plugin_prompt_fragments(manifest: dict[str, Any]) -> list[str]:
    raw = dict(manifest.get("raw") or {})
    plugin_dir = Path(manifest["plugin_dir"]).resolve()
    fragments = [str(raw.get("prompt") or "").strip()]
    for relative_path in raw.get("prompt_fragments", []) or []:
        path = (plugin_dir / str(relative_path)).resolve()
        if not _is_relative_to(path, plugin_dir):
            continue
        try:
            fragments.append(path.read_text(encoding="utf-8").strip())
        except Exception:
            continue
    return [fragment for fragment in fragments if fragment]


def _unique_paths(values: list[Any]) -> list[Path]:
    paths: list[Path] = []
    seen: set[Path] = set()
    for value in values:
        if not value:
            continue
        path = Path(str(value)).expanduser().resolve()
        if path in seen:
            continue
        seen.add(path)
        paths.append(path)
    return paths


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _effective_spec_from_session_state(resolved_spec: AgentSpec, tool_context: ToolRuntimeContext) -> AgentSpec:
    spec = _effective_spec_from_config_overrides(resolved_spec, tool_context)
    if not tool_context.permission_overridden:
        return spec
    mode = tool_context.permission_mode_override or spec.tool_permissions.mode or "auto"
    profile = tool_context.permission_profile_override or mode
    return replace(
        spec,
        permission_profile=profile,
        tool_permissions=replace(
            spec.tool_permissions,
            mode=mode,
            allowed_tools=list(tool_context.permission_allowed_tools_override) if tool_context.permission_restrict_allowed_tools else None,
            denied_tools=list(tool_context.permission_denied_tools_override),
            approval_required_tools=list(tool_context.approval_required_tools_override),
        ),
    )


def _effective_spec_from_config_overrides(resolved_spec: AgentSpec, tool_context: ToolRuntimeContext) -> AgentSpec:
    overrides = getattr(tool_context, "config_overrides", {}) or {}
    model_value = _config_override_value(overrides, "model")
    if model_value is None:
        return resolved_spec
    model = str(model_value or "").strip()
    return replace(
        resolved_spec,
        model=replace(resolved_spec.model, model=model or None),
    )


def _config_override_value(overrides: dict[str, str], setting: str) -> Any | None:
    raw = overrides.get("config.%s" % setting)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return raw


async def _memory_fragments(settings: Any, memory_store: Optional[MemoryStore], workspace) -> list:
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
        )
    )


async def _hydrate_schedules(tool_context: ToolRuntimeContext) -> None:
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


async def _hydrate_teams(tool_context: ToolRuntimeContext) -> None:
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


async def _hydrate_hooks(tool_context: ToolRuntimeContext) -> None:
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


async def _hydrate_mcp_config(tool_context: ToolRuntimeContext) -> None:
    store = getattr(tool_context, "mcp_config_store", None)
    if store is None:
        return
    workspace = tool_context.workspace
    records = await store.list_for_scope(
        workspace.tenant_id,
        user_id=workspace.user_id,
        agent_id=workspace.agent_id,
        workspace_id=workspace.workspace_id,
    )
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


async def _hydrate_session_state(tool_context: ToolRuntimeContext) -> None:
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
    tool_context.config_overrides = dict(record.metadata)


def _csv_setting(raw: str) -> list[str]:
    return [item.strip() for item in str(raw or "").split(",") if item.strip()]


def _merge_unique(*groups: list[str]) -> list[str]:
    names: list[str] = []
    seen = set()
    for group in groups:
        for name in group:
            if name not in seen:
                seen.add(name)
                names.append(name)
    return names


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
