from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from fnmatch import fnmatchcase
from typing import Iterable

from agents.kernel.schema import ToolCall
from agents.kernel.governance.shell_rule_normalization import normalize_shell_segment


SHELL_RUN_TOOL = "shell.run"
_SHELL_TOOL_ALIASES = {
    "Bash": SHELL_RUN_TOOL,
    "bash": SHELL_RUN_TOOL,
    "Shell": SHELL_RUN_TOOL,
    "shell": SHELL_RUN_TOOL,
}
_TOOL_ALIASES = {
    **_SHELL_TOOL_ALIASES,
    "Read": "filesystem.read",
    "Write": "filesystem.write",
    "Edit": "patch.apply",
    "MultiEdit": "patch.apply",
    "NotebookEdit": "notebook.edit",
    "LSP": "lsp.query",
    "Grep": "search.grep",
    "Glob": "search.glob",
    "TodoWrite": "todo.write",
    "Sleep": "sleep.wait",
    "WebSearch": "web.search",
    "WebFetch": "web.extract",
    "ListMcpResourcesTool": "mcp.resources",
    "ReadMcpResourceTool": "mcp.read_resource",
    "TaskOutput": "task.output",
    "AgentOutputTool": "task.output",
    "BashOutputTool": "shell.output",
    "TaskStop": "task.stop",
    "KillShell": "shell.kill",
    "TaskCreate": "task.create",
    "TaskList": "task.list",
    "TaskGet": "task.get",
    "TaskUpdate": "task.update",
    "CronCreate": "schedule.create",
    "CronList": "schedule.list",
    "CronDelete": "schedule.delete",
    "ToolSearch": "tool.search",
    "EnterPlanMode": "plan.enter",
    "ExitPlanMode": "plan.exit",
    "Agent": "agent.run",
    "Task": "agent.run",
    "SendMessage": "team.send",
    "TeamCreate": "team.create",
    "TeamDelete": "team.delete",
    "StructuredOutput": "structured.output",
    "Skill": "skill.invoke",
    "Config": "config.manage",
    "AskUserQuestion": "user.ask",
    "SendUserMessage": "user.message",
    "Brief": "user.message",
    "EnterWorktree": "worktree.enter",
    "ExitWorktree": "worktree.exit",
}
_SHELL_COLON_PREFIXES = ("shell.run", "Bash", "bash", "Shell", "shell")
_SHELL_SEPARATORS = {"&&", "||", ";", "|", "&"}


@dataclass(frozen=True)
class ParsedToolRule:
    raw: str
    tool_name: str
    rule_content: str | None = None


@dataclass(frozen=True)
class ShellCommandParts:
    subcommands: tuple[str, ...]
    parse_error: bool = False
    too_complex: bool = False


def find_matching_tool_rule(
    rules: Iterable[str],
    call: ToolCall,
    *,
    shell_parse_error_matches: bool = False,
) -> str | None:
    for rule in rules:
        matched = matching_tool_rule_alternative(
            str(rule),
            call,
            shell_parse_error_matches=shell_parse_error_matches,
        )
        if matched is not None:
            return matched
    return None


def matching_blanket_tool_rule(rule: str, tool_name: str) -> str | None:
    for alternative in split_tool_rule_alternatives(rule):
        parsed = parse_tool_rule(alternative)
        if parsed.rule_content is None and _tool_name_matches(parsed.tool_name, tool_name):
            return alternative
    return None


def matching_tool_rule_alternative(
    rule: str,
    call: ToolCall,
    *,
    shell_parse_error_matches: bool = False,
) -> str | None:
    for alternative in split_tool_rule_alternatives(rule):
        if tool_rule_matches_call(
            alternative,
            call,
            shell_parse_error_matches=shell_parse_error_matches,
        ):
            return alternative
    return None


def tool_rule_matches_call(
    rule: str,
    call: ToolCall,
    *,
    shell_parse_error_matches: bool = False,
) -> bool:
    parsed = parse_tool_rule(rule)
    if not _tool_name_matches(parsed.tool_name, call.name):
        return False
    if parsed.rule_content is None:
        return True
    if call.name != SHELL_RUN_TOOL:
        return tool_call_content_matches_rule(call, parsed.rule_content)
    return shell_command_matches_rule(
        str(call.arguments.get("command") or ""),
        parsed.rule_content,
        parse_error_matches=shell_parse_error_matches,
    )


def parse_tool_rule(rule: str) -> ParsedToolRule:
    value = str(rule or "").strip()
    if not value:
        return ParsedToolRule(raw=value, tool_name="")
    colon_rule = _parse_shell_colon_rule(value)
    if colon_rule is not None:
        return colon_rule

    open_index = _find_first_unescaped(value, "(")
    if open_index < 0:
        return ParsedToolRule(raw=value, tool_name=normalize_tool_name(value))
    close_index = _find_last_unescaped(value, ")")
    if close_index <= open_index or close_index != len(value) - 1:
        return ParsedToolRule(raw=value, tool_name=normalize_tool_name(value))
    tool_name = value[:open_index].strip()
    if not tool_name:
        return ParsedToolRule(raw=value, tool_name=normalize_tool_name(value))
    raw_content = value[open_index + 1 : close_index]
    content = _unescape_rule_content(raw_content)
    if content in {"", "*"}:
        content = None
    return ParsedToolRule(raw=value, tool_name=normalize_tool_name(tool_name), rule_content=content)


def normalize_tool_name(name: str) -> str:
    value = str(name or "").strip()
    return _TOOL_ALIASES.get(value, value)


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


def shell_command_matches_rule(
    command: str,
    pattern: str,
    *,
    parse_error_matches: bool = False,
) -> bool:
    parsed = split_shell_subcommands(command)
    if parsed.parse_error and parse_error_matches:
        return True
    for subcommand in parsed.subcommands:
        if shell_subcommand_matches_rule(subcommand, pattern):
            return True
    if parsed.too_complex and parse_error_matches:
        return True
    return False


def tool_call_content_matches_rule(call: ToolCall, pattern: str) -> bool:
    return any(match_wildcard_pattern(pattern, target) for target in _tool_rule_targets(call))


def shell_subcommand_matches_rule(subcommand: str, pattern: str) -> bool:
    prefix = shell_rule_extract_prefix(pattern)
    command = str(subcommand or "").strip()
    if prefix is not None:
        if command == prefix or command.startswith("%s " % prefix):
            return True
        xargs_prefix = "xargs %s" % prefix
        return command == xargs_prefix or command.startswith("%s " % xargs_prefix)
    return match_wildcard_pattern(pattern, command)


def _tool_rule_targets(call: ToolCall) -> tuple[str, ...]:
    arguments = dict(call.arguments or {})
    name = normalize_tool_name(call.name)
    if name in {"filesystem.read", "filesystem.list", "filesystem.write", "filesystem.delete"}:
        return _argument_values(arguments, "path", "file_path", "filePath")
    if name == "filesystem.move":
        return _argument_values(arguments, "source_path", "sourcePath", "destination_path", "destinationPath")
    if name == "notebook.edit":
        return _argument_values(arguments, "notebook_path", "notebookPath", "path", "file_path", "filePath")
    if name == "lsp.query":
        return _argument_values(arguments, "filePath", "file_path", "path")
    if name == "patch.apply":
        return _unique_values((*_patch_paths(arguments), *_argument_values(arguments, "path", "file_path", "filePath")))
    if name == "search.grep":
        return _argument_values(arguments, "pattern")
    if name == "search.glob":
        return _argument_values(arguments, "pattern")
    if name in {"web.search", "web.extract"}:
        return _argument_values(arguments, "query", "url", "prompt")
    if name in {"mcp.resources", "mcp.read_resource", "mcp.get_prompt"}:
        return _argument_values(arguments, "server", "uri", "uri_prefix", "name")
    if name in {"task.create", "task.run", "task.background"}:
        return _argument_values(arguments, "task_id", "taskId", "title", "subject", "input", "description")
    if name in {"task.get", "task.update", "task.stop", "task.output", "shell.output", "shell.kill"}:
        return _argument_values(arguments, "task_id", "taskId", "shell_id", "shellId", "title", "subject")
    if name in {"schedule.create", "schedule.run", "schedule.delete"}:
        return _argument_values(arguments, "schedule_id", "scheduleId", "id", "schedule", "cron", "title", "prompt", "input")
    if name == "tool.search":
        return _argument_values(arguments, "query")
    if name == "plan.exit":
        return _argument_values(arguments, "plan")
    if name == "agent.run":
        return _argument_values(arguments, "agent_id", "subagent_type", "description", "prompt", "name", "team_name", "cwd")
    if name in {"team.create", "team.delete", "team.members", "team.inbox", "team.run_member"}:
        return _argument_values(arguments, "team_id", "team_name", "name", "agent_id", "agent_type", "description", "prompt")
    if name == "team.send":
        return _argument_values(arguments, "to", "team_id", "team_name", "message")
    if name == "skill.invoke":
        return _argument_values(arguments, "skill", "name")
    if name == "config.manage":
        return _argument_values(arguments, "setting")
    if name == "user.ask":
        return _question_targets(arguments)
    if name == "user.message":
        return _argument_values(arguments, "message")
    if name == "worktree.enter":
        return _argument_values(arguments, "name")
    if name == "worktree.exit":
        return _argument_values(arguments, "action")
    return _argument_values(arguments, "path", "file_path", "pattern", "setting")


def _argument_values(arguments: dict, *names: str) -> tuple[str, ...]:
    values: list[str] = []
    for name in names:
        value = arguments.get(name)
        if isinstance(value, str):
            if value:
                values.append(value)
        elif isinstance(value, (list, tuple)):
            values.extend(str(item) for item in value if str(item))
    return _unique_values(values)


def _unique_values(values: Iterable[str]) -> tuple[str, ...]:
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value)
        if not text or text in seen:
            continue
        seen.add(text)
        unique.append(text)
    return tuple(unique)


def _patch_paths(arguments: dict) -> tuple[str, ...]:
    paths: list[str] = []
    for key in ("edits", "creates"):
        value = arguments.get(key)
        if not isinstance(value, list):
            continue
        for item in value:
            if isinstance(item, dict):
                path = str(item.get("path") or "")
                if path:
                    paths.append(path)
    return tuple(paths)


def _question_targets(arguments: dict) -> tuple[str, ...]:
    questions = arguments.get("questions")
    if not isinstance(questions, list):
        return ()
    targets: list[str] = []
    for item in questions:
        if isinstance(item, dict):
            question = str(item.get("question") or "")
            header = str(item.get("header") or "")
            if question:
                targets.append(question)
            if header:
                targets.append(header)
    return tuple(targets)


def shell_rule_extract_prefix(pattern: str) -> str | None:
    match = re.match(r"^(.+):\*$", str(pattern or ""))
    return match.group(1) if match else None


def split_shell_subcommands(command: str) -> ShellCommandParts:
    value = str(command or "").strip()
    if not value:
        return ShellCommandParts(subcommands=())
    too_complex = _shell_command_too_complex_for_match(value)
    try:
        lexer = shlex.shlex(value, posix=True, punctuation_chars=";&|")
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        return ShellCommandParts(subcommands=(), parse_error=True, too_complex=too_complex)
    subcommands: list[str] = []
    current: list[str] = []
    for token in tokens:
        if _is_shell_separator(token):
            _append_shell_segment(subcommands, current)
            current = []
            continue
        current.append(token)
    _append_shell_segment(subcommands, current)
    return ShellCommandParts(subcommands=tuple(subcommands), too_complex=too_complex)


def match_wildcard_pattern(pattern: str, command: str, *, case_insensitive: bool = False) -> bool:
    tokens = _wildcard_tokens(str(pattern or "").strip())
    wildcard_count = sum(1 for kind, _ in tokens if kind == "wildcard")
    if wildcard_count == 1 and len(tokens) >= 2 and tokens[-1][0] == "wildcard" and tokens[-2] == ("literal", " "):
        regex_pattern = _wildcard_regex(tokens[:-2]) + r"( .*)?"
    else:
        regex_pattern = _wildcard_regex(tokens)
    flags = re.DOTALL | (re.IGNORECASE if case_insensitive else 0)
    return re.match(r"^%s$" % regex_pattern, str(command or ""), flags) is not None


def _parse_shell_colon_rule(value: str) -> ParsedToolRule | None:
    if "(" in value:
        return None
    for prefix in _SHELL_COLON_PREFIXES:
        marker = "%s:" % prefix
        if value.startswith(marker):
            content = value[len(marker) :].strip()
            return ParsedToolRule(
                raw=value,
                tool_name=normalize_tool_name(prefix),
                rule_content=None if content in {"", "*"} else content,
            )
    return None


def _tool_name_matches(pattern: str, tool_name: str) -> bool:
    normalized_pattern = normalize_tool_name(pattern)
    normalized_tool = normalize_tool_name(tool_name)
    if not normalized_pattern:
        return False
    if normalized_pattern == "*":
        return True
    if _mcp_server_prefix_matches(normalized_pattern, normalized_tool):
        return True
    if "*" in normalized_pattern:
        return fnmatchcase(normalized_tool, normalized_pattern)
    return normalized_tool == normalized_pattern


def _mcp_server_prefix_matches(pattern: str, tool_name: str) -> bool:
    if not pattern.startswith("mcp__"):
        return False
    server_name = pattern.removeprefix("mcp__")
    if not server_name or "__" in server_name:
        return False
    return tool_name.startswith("%s__" % pattern)


def _append_shell_segment(output: list[str], segment: list[str]) -> None:
    normalized = normalize_shell_segment(segment)
    if normalized:
        output.append(normalized)


def _is_shell_separator(token: str) -> bool:
    value = str(token or "")
    return value in _SHELL_SEPARATORS or bool(value) and set(value).issubset(set(";&|"))


def _shell_command_too_complex_for_match(command: str) -> bool:
    return any(marker in command for marker in ("$(", "`", "<(", ">(")) or "\n" in command or "\r" in command


def _wildcard_tokens(pattern: str) -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    index = 0
    while index < len(pattern):
        char = pattern[index]
        if char == "\\" and index + 1 < len(pattern):
            next_char = pattern[index + 1]
            if next_char in {"*", "\\"}:
                tokens.append(("literal", next_char))
                index += 2
                continue
        if char == "*":
            tokens.append(("wildcard", char))
        else:
            tokens.append(("literal", char))
        index += 1
    return tokens


def _wildcard_regex(tokens: list[tuple[str, str]]) -> str:
    return "".join(".*" if kind == "wildcard" else re.escape(value) for kind, value in tokens)


def _find_first_unescaped(value: str, char: str) -> int:
    escaped = False
    for index, current in enumerate(value):
        if escaped:
            escaped = False
            continue
        if current == "\\":
            escaped = True
            continue
        if current == char:
            return index
    return -1


def _find_last_unescaped(value: str, char: str) -> int:
    escaped = False
    result = -1
    for index, current in enumerate(value):
        if escaped:
            escaped = False
            continue
        if current == "\\":
            escaped = True
            continue
        if current == char:
            result = index
    return result


def _unescape_rule_content(content: str) -> str:
    return content.replace(r"\(", "(").replace(r"\)", ")").replace(r"\\", "\\")
