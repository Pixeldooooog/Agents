from __future__ import annotations

from typing import Iterable

from agents.kernel.governance.shell_rule_normalization import ShellEnvMode
from agents.kernel.governance.tool_rule_names import (
    SHELL_RUN_TOOL,
    normalize_tool_name,
    tool_name_matches,
)
from agents.kernel.governance.tool_rule_parser import parse_tool_rule, split_tool_rule_alternatives
from agents.kernel.governance.tool_rule_patterns import match_wildcard_pattern
from agents.kernel.governance.tool_rule_shell import (
    is_literal_shell_rule,
    matching_shell_allow_subcommand_rule,
    matching_shell_rule_alternatives,
    shell_command_matches_rule,
    shell_rule_extract_prefix,
    shell_subcommand_matches_rule,
    split_shell_subcommands,
)
from agents.kernel.governance.tool_rule_targets import tool_call_content_matches_rule
from agents.kernel.governance.tool_rule_types import ParsedToolRule, ShellCommandParts
from agents.kernel.schema import ToolCall


def find_matching_tool_rule(
    rules: Iterable[str],
    call: ToolCall,
    *,
    shell_parse_error_matches: bool = False,
    shell_env_mode: ShellEnvMode = "all",
    shell_reject_compound_prefix: bool = False,
) -> str | None:
    for rule in rules:
        matched = matching_tool_rule_alternative(
            str(rule),
            call,
            shell_parse_error_matches=shell_parse_error_matches,
            shell_env_mode=shell_env_mode,
            shell_reject_compound_prefix=shell_reject_compound_prefix,
        )
        if matched is not None:
            return matched
    return None


def find_matching_shell_allow_rule(
    rules: Iterable[str],
    call: ToolCall,
    *,
    shell_env_mode: ShellEnvMode = "safe",
    shell_reject_compound_prefix: bool = True,
) -> str | None:
    if normalize_tool_name(call.name) != SHELL_RUN_TOOL:
        return find_matching_tool_rule(
            rules,
            call,
            shell_parse_error_matches=False,
            shell_env_mode=shell_env_mode,
            shell_reject_compound_prefix=shell_reject_compound_prefix,
        )

    command = str(call.arguments.get("command") or "").strip()
    if not command:
        return None

    parsed_rules = matching_shell_rule_alternatives(rules)
    for parsed in parsed_rules:
        if parsed.rule_content is None:
            return parsed.raw
        if is_literal_shell_rule(parsed.rule_content) and parsed.rule_content == command:
            return parsed.raw

    parsed = split_shell_subcommands(command, shell_env_mode=shell_env_mode)
    if parsed.parse_error or not parsed.subcommands:
        return None
    unstripped = split_shell_subcommands(
        command,
        shell_env_mode=shell_env_mode,
        strip_output_redirections=False,
    )

    matched_rules: list[str] = []
    for index, subcommand in enumerate(parsed.subcommands):
        original_subcommand = unstripped.subcommands[index] if index < len(unstripped.subcommands) else ""
        matched = matching_shell_allow_subcommand_rule(
            parsed_rules,
            subcommand,
            original_subcommand,
            reject_compound_prefix=shell_reject_compound_prefix,
        )
        if matched is None:
            return None
        matched_rules.append(matched)
    return matched_rules[0] if matched_rules else None


def matching_blanket_tool_rule(rule: str, tool_name: str) -> str | None:
    for alternative in split_tool_rule_alternatives(rule):
        parsed = parse_tool_rule(alternative)
        if parsed.rule_content is None and tool_name_matches(parsed.tool_name, tool_name):
            return alternative
    return None


def matching_tool_rule_alternative(
    rule: str,
    call: ToolCall,
    *,
    shell_parse_error_matches: bool = False,
    shell_env_mode: ShellEnvMode = "all",
    shell_reject_compound_prefix: bool = False,
) -> str | None:
    for alternative in split_tool_rule_alternatives(rule):
        if tool_rule_matches_call(
            alternative,
            call,
            shell_parse_error_matches=shell_parse_error_matches,
            shell_env_mode=shell_env_mode,
            shell_reject_compound_prefix=shell_reject_compound_prefix,
        ):
            return alternative
    return None


def tool_rule_matches_call(
    rule: str,
    call: ToolCall,
    *,
    shell_parse_error_matches: bool = False,
    shell_env_mode: ShellEnvMode = "all",
    shell_reject_compound_prefix: bool = False,
) -> bool:
    parsed = parse_tool_rule(rule)
    if not tool_name_matches(parsed.tool_name, call.name):
        return False
    if parsed.rule_content is None:
        return True
    if call.name != SHELL_RUN_TOOL:
        return tool_call_content_matches_rule(call, parsed.rule_content)
    return shell_command_matches_rule(
        str(call.arguments.get("command") or ""),
        parsed.rule_content,
        parse_error_matches=shell_parse_error_matches,
        shell_env_mode=shell_env_mode,
        reject_compound_prefix=shell_reject_compound_prefix,
    )
