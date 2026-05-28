from __future__ import annotations

from dataclasses import replace

from agents.kernel.capabilities.tools.builtin.src_origin.agent_metadata import (
    metadata_value,
    parse_src_origin_tool_list,
)
from agents.kernel.governance.tool_rule_parser import parse_tool_rule
from agents.kernel.specs import AgentSpec


def apply_src_origin_agent_tool_rules(
    spec: AgentSpec,
    metadata: dict[str, object],
) -> AgentSpec:
    return _apply_disallowed_tools(_apply_enabled_tools(spec, metadata), metadata)


def _apply_enabled_tools(spec: AgentSpec, metadata: dict[str, object]) -> AgentSpec:
    found, value = metadata_value(metadata, "tools", "enabled_tools")
    if not found:
        return spec
    tools = parse_src_origin_tool_list(value)
    return replace(spec, enabled_tools=None if "*" in tools else _enabled_tool_names(tools))


def _apply_disallowed_tools(spec: AgentSpec, metadata: dict[str, object]) -> AgentSpec:
    found, value = metadata_value(metadata, "disallowedTools", "disallowed_tools", "denied_tools")
    if not found:
        return spec
    rules = parse_src_origin_tool_list(value)
    if not rules or "*" in rules:
        return spec
    permissions = spec.tool_permissions
    denied_tools = _merge_unique(permissions.denied_tools, rules)
    if denied_tools == permissions.denied_tools:
        return spec
    return replace(spec, tool_permissions=replace(permissions, denied_tools=denied_tools))


def _merge_unique(existing: list[str], additions: tuple[str, ...]) -> list[str]:
    merged = list(existing)
    seen = set(merged)
    for rule in additions:
        if rule in seen:
            continue
        seen.add(rule)
        merged.append(rule)
    return merged


def _enabled_tool_names(rules: tuple[str, ...]) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for rule in rules:
        name = parse_tool_rule(rule).tool_name
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names
