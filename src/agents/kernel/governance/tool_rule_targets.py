from __future__ import annotations

from typing import Iterable

from agents.kernel.governance.tool_rule_names import normalize_tool_name
from agents.kernel.governance.tool_rule_patterns import match_wildcard_pattern
from agents.kernel.schema import ToolCall


def tool_call_content_matches_rule(call: ToolCall, pattern: str) -> bool:
    return any(match_wildcard_pattern(pattern, target) for target in _tool_rule_targets(call))


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
