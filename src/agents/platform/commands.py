from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SlashCommand:
    name: str
    action: str
    aliases: tuple[str, ...] = ()
    argument_hint: str = ""
    availability: str = "idle"
    source: str = "builtin"
    category: str = "core"


COMMANDS = [
    SlashCommand("/help", "show terminal commands", availability="always"),
    SlashCommand("/commands", "show or manage prompt-backed workspace commands", aliases=("/cmds",), argument_hint="[read|render|save|delete]"),
    SlashCommand("/status", "show protocol, workspace, permission, and token estimate"),
    SlashCommand("/model", "show or switch .env/config model profiles", aliases=("/models",), argument_hint="<profile>"),
    SlashCommand("/doctor", "check local model, workspace, and tool readiness"),
    SlashCommand("/workspace", "show workspace path and scope"),
    SlashCommand("/tools", "show enabled tools"),
    SlashCommand("/permissions", "show permission sources or switch permission mode", aliases=("/permission", "/perms"), argument_hint="[sources|audit|guarded|auto|ask|deny]"),
    SlashCommand("/diff", "show git workspace changes"),
    SlashCommand("/context", "show or edit context window messages", argument_hint="[messages|drop]"),
    SlashCommand("/trace", "show context assembly trace"),
    SlashCommand("/prompt", "show, override, render, or reuse prompt templates", argument_hint="[show|set|save|render|use]"),
    SlashCommand("/compact", "summarize older conversation messages and keep recent context", argument_hint="<target_tokens>"),
    SlashCommand("/sessions", "show or delete saved terminal sessions", argument_hint="[delete]"),
    SlashCommand("/session", "show current terminal session details"),
    SlashCommand("/resume", "resume a saved terminal session", argument_hint="<session>"),
    SlashCommand("/export", "export current session to workspace JSON or Markdown", argument_hint="[json|markdown] [path]"),
    SlashCommand("/fork", "fork current session into a new saved session", argument_hint="[non_system_message_count]"),
    SlashCommand("/rewind", "remove recent non-system messages from current session", argument_hint="[count]"),
    SlashCommand("/agents", "list, save, or switch agent profiles", argument_hint="[save|use]"),
    SlashCommand("/tasks", "list, create, run, start, queue, or cancel tasks for this agent", argument_hint="[create|run|start|enqueue|queue|drain|cancel]"),
    SlashCommand("/schedules", "list, create, run, or delete scheduled tasks", aliases=("/schedule",), argument_hint="[create|run|delete]"),
    SlashCommand("/hooks", "list, add, or delete session hooks", argument_hint="[add|delete]"),
    SlashCommand("/todo", "show or clear the session todo checklist", aliases=("/todos",), argument_hint="[clear]"),
    SlashCommand("/plan", "show or control session plan mode", argument_hint="[status|enter|exit|clear]"),
    SlashCommand("/workflows", "list, save, validate, run, or delete workspace workflows", aliases=("/workflow",), argument_hint="[read|save|validate|run|delete]"),
    SlashCommand("/capabilities", "show terminal capability surface overview", aliases=("/caps",)),
    SlashCommand("/plugins", "install, list, enable, or disable local plugins", argument_hint="[install|enable|disable]"),
    SlashCommand("/skills", "install, list, enable, or disable skills", argument_hint="[install|use|disable]"),
    SlashCommand("/mcp", "show, configure, or reload MCP tools", argument_hint="[set|reload|clear]"),
    SlashCommand("/memory", "list, add, edit, or forget memory records", argument_hint="[add|edit|forget]"),
    SlashCommand("/clear", "reset conversation messages"),
    SlashCommand("/exit", "leave the chat", aliases=("/quit",), availability="always"),
]


def command_names() -> list[str]:
    return [command.name for command in COMMANDS]


def command_lookup() -> dict[str, SlashCommand]:
    lookup: dict[str, SlashCommand] = {}
    for command in COMMANDS:
        lookup[command.name] = command
        for alias in command.aliases:
            lookup[alias] = command
    return lookup
