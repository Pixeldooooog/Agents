from __future__ import annotations

import re
import shlex
from typing import Iterable

from agents.kernel.governance.shell_rule_normalization import (
    ShellEnvMode,
    merge_shell_redirection_tokens,
    normalize_shell_segment,
)
from agents.kernel.governance.tool_rule_names import SHELL_RUN_TOOL, tool_name_matches
from agents.kernel.governance.tool_rule_parser import parse_tool_rule, split_tool_rule_alternatives
from agents.kernel.governance.tool_rule_patterns import match_wildcard_pattern
from agents.kernel.governance.tool_rule_types import ParsedToolRule, ShellCommandParts


SHELL_SEPARATORS = {"&&", "||", ";", "|", "&"}


def shell_command_matches_rule(
    command: str,
    pattern: str,
    *,
    parse_error_matches: bool = False,
    shell_env_mode: ShellEnvMode = "all",
    reject_compound_prefix: bool = False,
) -> bool:
    if shell_literal_matches_command(pattern, command):
        return True

    parsed = split_shell_subcommands(command, shell_env_mode=shell_env_mode)
    if parsed.parse_error and parse_error_matches:
        return True
    for subcommand in parsed.subcommands:
        if shell_subcommand_matches_rule(
            subcommand,
            pattern,
            reject_compound_prefix=reject_compound_prefix,
        ):
            return True
    if is_literal_shell_rule(pattern):
        unstripped = split_shell_subcommands(
            command,
            shell_env_mode=shell_env_mode,
            strip_output_redirections=False,
        )
        if unstripped.parse_error and parse_error_matches:
            return True
        for subcommand in unstripped.subcommands:
            if shell_subcommand_matches_rule(
                subcommand,
                pattern,
                reject_compound_prefix=reject_compound_prefix,
            ):
                return True
    if parsed.too_complex and parse_error_matches:
        return True
    return False


def shell_subcommand_matches_rule(
    subcommand: str,
    pattern: str,
    *,
    reject_compound_prefix: bool = False,
) -> bool:
    prefix = shell_rule_extract_prefix(pattern)
    command = str(subcommand or "").strip()
    if prefix is not None:
        if reject_compound_prefix and shell_subcommand_has_operator(command):
            return False
        if command == prefix or command.startswith("%s " % prefix):
            return True
        xargs_prefix = "xargs %s" % prefix
        return command == xargs_prefix or command.startswith("%s " % xargs_prefix)
    if reject_compound_prefix and "*" in str(pattern or "") and shell_subcommand_has_operator(command):
        return False
    return match_wildcard_pattern(pattern, command)


def matching_shell_rule_alternatives(rules: Iterable[str]) -> tuple[ParsedToolRule, ...]:
    alternatives: list[ParsedToolRule] = []
    for rule in rules:
        for alternative in split_tool_rule_alternatives(str(rule)):
            parsed = parse_tool_rule(alternative)
            if tool_name_matches(parsed.tool_name, SHELL_RUN_TOOL):
                alternatives.append(parsed)
    return tuple(alternatives)


def matching_shell_allow_subcommand_rule(
    rules: Iterable[ParsedToolRule],
    subcommand: str,
    original_subcommand: str,
    *,
    reject_compound_prefix: bool,
) -> str | None:
    for rule in rules:
        content = rule.rule_content
        if content is None:
            return rule.raw
        if shell_subcommand_matches_rule(
            subcommand,
            content,
            reject_compound_prefix=reject_compound_prefix,
        ):
            return rule.raw
        if (
            original_subcommand
            and is_literal_shell_rule(content)
            and shell_subcommand_matches_rule(
                original_subcommand,
                content,
                reject_compound_prefix=reject_compound_prefix,
            )
        ):
            return rule.raw
    return None


def shell_rule_extract_prefix(pattern: str) -> str | None:
    match = re.match(r"^(.+):\*$", str(pattern or ""))
    return match.group(1) if match else None


def split_shell_subcommands(
    command: str,
    *,
    shell_env_mode: ShellEnvMode = "all",
    strip_output_redirections: bool = True,
) -> ShellCommandParts:
    value = str(command or "").strip()
    if not value:
        return ShellCommandParts(subcommands=())
    too_complex = shell_command_too_complex_for_match(value)
    try:
        lexer = shlex.shlex(value, posix=True, punctuation_chars=";&|")
        lexer.whitespace_split = True
        tokens = merge_shell_redirection_tokens(list(lexer))
    except ValueError:
        return ShellCommandParts(subcommands=(), parse_error=True, too_complex=too_complex)
    subcommands: list[str] = []
    current: list[str] = []
    for token in tokens:
        if is_shell_separator(token):
            append_shell_segment(
                subcommands,
                current,
                shell_env_mode=shell_env_mode,
                strip_output_redirections=strip_output_redirections,
            )
            current = []
            continue
        current.append(token)
    append_shell_segment(
        subcommands,
        current,
        shell_env_mode=shell_env_mode,
        strip_output_redirections=strip_output_redirections,
    )
    return ShellCommandParts(subcommands=tuple(subcommands), too_complex=too_complex)


def append_shell_segment(
    output: list[str],
    segment: list[str],
    *,
    shell_env_mode: ShellEnvMode,
    strip_output_redirections: bool,
) -> None:
    normalized = normalize_shell_segment(
        segment,
        env_mode=shell_env_mode,
        strip_output_redirections=strip_output_redirections,
    )
    if normalized:
        output.append(normalized)


def is_shell_separator(token: str) -> bool:
    value = str(token or "")
    return value in SHELL_SEPARATORS or bool(value) and set(value).issubset(set(";&|"))


def shell_command_too_complex_for_match(command: str) -> bool:
    return any(marker in command for marker in ("$(", "`", "<(", ">(")) or "\n" in command or "\r" in command


def shell_subcommand_has_operator(command: str) -> bool:
    return any(operator in str(command or "") for operator in ("&&", "||", ";", "|"))


def is_literal_shell_rule(pattern: str) -> bool:
    return shell_rule_extract_prefix(pattern) is None and "*" not in str(pattern or "")


def shell_literal_matches_command(pattern: str, command: str) -> bool:
    return (
        is_literal_shell_rule(pattern)
        and str(pattern or "").strip() == str(command or "").strip()
    )
