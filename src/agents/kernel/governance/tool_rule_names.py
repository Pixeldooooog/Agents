from __future__ import annotations

from fnmatch import fnmatchcase


SHELL_RUN_TOOL = "shell.run"
SHELL_TOOL_ALIASES = {
    "Bash": SHELL_RUN_TOOL,
    "bash": SHELL_RUN_TOOL,
    "Shell": SHELL_RUN_TOOL,
    "shell": SHELL_RUN_TOOL,
}
SHELL_COLON_PREFIXES = ("shell.run", "Bash", "bash", "Shell", "shell")

TOOL_ALIASES = {
    **SHELL_TOOL_ALIASES,
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


def normalize_tool_name(name: str) -> str:
    value = str(name or "").strip()
    return TOOL_ALIASES.get(value, value)


def tool_name_matches(pattern: str, tool_name: str) -> bool:
    normalized_pattern = normalize_tool_name(pattern)
    normalized_tool = normalize_tool_name(tool_name)
    if not normalized_pattern:
        return False
    if normalized_pattern == "*":
        return True
    if mcp_server_prefix_matches(normalized_pattern, normalized_tool):
        return True
    if "*" in normalized_pattern:
        return fnmatchcase(normalized_tool, normalized_pattern)
    return normalized_tool == normalized_pattern


def mcp_server_prefix_matches(pattern: str, tool_name: str) -> bool:
    if not pattern.startswith("mcp__"):
        return False
    server_name = pattern.removeprefix("mcp__")
    if not server_name or "__" in server_name:
        return False
    return tool_name.startswith("%s__" % pattern)
