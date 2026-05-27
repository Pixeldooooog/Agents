from __future__ import annotations

from agents.kernel.governance.tool_rule_names import SHELL_COLON_PREFIXES, normalize_tool_name
from agents.kernel.governance.tool_rule_patterns import (
    find_first_unescaped,
    find_last_unescaped,
    unescape_rule_content,
)
from agents.kernel.governance.tool_rule_types import ParsedToolRule


def parse_tool_rule(rule: str) -> ParsedToolRule:
    value = str(rule or "").strip()
    if not value:
        return ParsedToolRule(raw=value, tool_name="")
    colon_rule = _parse_shell_colon_rule(value)
    if colon_rule is not None:
        return colon_rule

    open_index = find_first_unescaped(value, "(")
    if open_index < 0:
        return ParsedToolRule(raw=value, tool_name=normalize_tool_name(value))
    close_index = find_last_unescaped(value, ")")
    if close_index <= open_index or close_index != len(value) - 1:
        return ParsedToolRule(raw=value, tool_name=normalize_tool_name(value))
    tool_name = value[:open_index].strip()
    if not tool_name:
        return ParsedToolRule(raw=value, tool_name=normalize_tool_name(value))
    raw_content = value[open_index + 1 : close_index]
    content = unescape_rule_content(raw_content)
    if content in {"", "*"}:
        content = None
    return ParsedToolRule(raw=value, tool_name=normalize_tool_name(tool_name), rule_content=content)


def split_tool_rule_alternatives(rule: str) -> tuple[str, ...]:
    value = str(rule or "").strip()
    if not value:
        return ("",)
    alternatives: list[str] = []
    start = 0
    depth = 0
    escaped = False
    for index, char in enumerate(value):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == "(":
            depth += 1
            continue
        if char == ")" and depth > 0:
            depth -= 1
            continue
        if char == "|" and depth == 0:
            part = value[start:index].strip()
            if part:
                alternatives.append(part)
            start = index + 1
    tail = value[start:].strip()
    if tail:
        alternatives.append(tail)
    return tuple(alternatives or (value,))


def _parse_shell_colon_rule(value: str) -> ParsedToolRule | None:
    if "(" in value:
        return None
    for prefix in SHELL_COLON_PREFIXES:
        marker = "%s:" % prefix
        if value.startswith(marker):
            content = value[len(marker) :].strip()
            return ParsedToolRule(
                raw=value,
                tool_name=normalize_tool_name(prefix),
                rule_content=None if content in {"", "*"} else content,
            )
    return None
