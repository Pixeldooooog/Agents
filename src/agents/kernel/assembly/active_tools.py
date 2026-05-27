from __future__ import annotations

from typing import Any, Optional

from agents.kernel.assembly.common import csv_setting, merge_unique
from agents.kernel.assembly.plugins import managed_extension_tools, plugin_enabled_tools
from agents.kernel.capabilities import resolve_active_tools as resolve_capability_active_tools
from agents.kernel.capabilities.skills import SkillRegistry
from agents.kernel.capabilities.tools import ToolRegistry, ToolRuntimeContext
from agents.kernel.config import AgentConfigError
from agents.kernel.governance.tool_rules import matching_blanket_tool_rule
from agents.kernel.specs import AgentSpec


def resolve_session_active_tools(
    settings: Any,
    skill_registry: SkillRegistry,
    spec: AgentSpec,
    builtin_tools: list[str],
    registry: ToolRegistry,
    tool_context: ToolRuntimeContext,
) -> list[str]:
    active_tools = merge_unique(
        _resolve_configured_active_tools(settings, skill_registry, spec.enabled_tools, builtin_tools),
        loaded_mcp_canonical_tools(registry),
        managed_extension_tools(tool_context),
        plugin_enabled_tools(settings, tool_context),
    )
    if has_structured_output_schema(spec):
        active_tools = merge_unique(active_tools, ["StructuredOutput"])
    active_tools = filter_denied_active_tools(active_tools, spec.tool_permissions.denied_tools)
    validate_active_tools(active_tools, registry)
    return active_tools


def loaded_mcp_canonical_tools(registry: ToolRegistry) -> list[str]:
    names: list[str] = []
    definitions = registry.definitions_matching(
        lambda definition: isinstance(definition.metadata.get("mcp_info"), dict)
    )
    for definition in definitions:
        name = str(definition.name or "")
        if name.startswith("mcp__"):
            names.append(name)
    return names


def filter_denied_active_tools(active_tools: list[str], denied_rules: list[str]) -> list[str]:
    if not denied_rules:
        return list(active_tools)
    return [tool for tool in active_tools if not any(matching_blanket_tool_rule(rule, tool) for rule in denied_rules)]


def validate_active_tools(active_tools: list[str], registry: ToolRegistry) -> None:
    registered = set(registry.names())
    unknown = sorted({name for name in active_tools if name not in registered})
    if unknown:
        raise AgentConfigError("unknown enabled tool(s): %s" % ", ".join(unknown))


def has_structured_output_schema(spec: AgentSpec) -> bool:
    metadata = getattr(spec, "metadata", {}) or {}
    return isinstance(metadata.get("structured_output_schema"), dict)


def _resolve_configured_active_tools(
    settings: Any,
    skill_registry: SkillRegistry,
    enabled_tools: Optional[list[str]],
    builtin_tools: list[str],
) -> list[str]:
    if enabled_tools is not None:
        return resolve_capability_active_tools(settings, skill_registry, enabled_tools)
    configured_tools = str(getattr(settings.agent, "ENABLED_TOOLS", "") or "").strip()
    active_tools = resolve_capability_active_tools(settings, skill_registry, None)
    if configured_tools:
        return active_tools
    builtin_defaults = [name for name in csv_setting(getattr(settings.agent, "BUILTIN_TOOLS", "")) if name in builtin_tools]
    return merge_unique(builtin_defaults, active_tools)
