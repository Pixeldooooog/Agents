from __future__ import annotations

from dataclasses import replace
from typing import Any

from agents.kernel.assembly.common import config_override_value, merge_unique
from agents.kernel.capabilities.skills import SkillLoader, SkillRegistry
from agents.kernel.capabilities.tools import ToolRuntimeContext
from agents.kernel.specs import AgentSpec


def skill_registry_with_session_state(
    settings: Any,
    skill_registry: SkillRegistry,
    tool_context: ToolRuntimeContext,
) -> SkillRegistry:
    base_names = skill_registry.names()
    persisted = [name for name in merge_unique(list(getattr(tool_context, "enabled_skills", set()) or [])) if name not in base_names]
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


def effective_spec_from_session_state(resolved_spec: AgentSpec, tool_context: ToolRuntimeContext) -> AgentSpec:
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
    model_value = config_override_value(overrides, "model")
    if model_value is None:
        return resolved_spec
    model = str(model_value or "").strip()
    return replace(
        resolved_spec,
        model=replace(resolved_spec.model, model=model or None),
    )
