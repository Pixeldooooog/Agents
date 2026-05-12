from __future__ import annotations

import getpass
import os
from copy import copy
from pathlib import Path
from typing import Optional

import typer

from agents.kernel.config import runtime_settings as settings

CODING_TOOLS = [
    "filesystem.read",
    "filesystem.list",
    "filesystem.write",
    "filesystem.delete",
    "filesystem.move",
    "patch.apply",
    "search.grep",
    "command.discover",
    "command.render",
    "command.read",
    "command.save",
    "command.delete",
    "tool.search",
    "skill.discover",
    "skill.install",
    "skill.uninstall",
    "skill.use",
    "skill.disable",
    "plugin.discover",
    "plugin.install",
    "plugin.uninstall",
    "plugin.enable",
    "plugin.disable",
    "mcp.servers",
    "mcp.configure",
    "mcp.enable",
    "mcp.disable",
    "mcp.remove",
    "mcp.clear",
    "mcp.prompts",
    "mcp.get_prompt",
    "mcp.resources",
    "mcp.read_resource",
    "prompt.templates",
    "prompt.read",
    "prompt.render",
    "prompt.save",
    "prompt.delete",
    "session.status",
    "session.summary",
    "session.export",
    "context.trace",
    "context.messages",
    "context.compact",
    "context.rewind",
    "permission.status",
    "permission.sources",
    "permission.explain",
    "permission.add_rule",
    "permission.remove_rule",
    "hook.events",
    "hook.list",
    "hook.add",
    "hook.delete",
    "memory.list",
    "memory.add",
    "memory.edit",
    "memory.forget",
    "git.status",
    "git.diff",
    "git.add",
    "git.commit",
    "git.log",
    "git.show",
    "test.discover",
    "test.run",
    "todo.write",
    "todo.read",
    "plan.enter",
    "plan.status",
    "plan.exit",
    "workflow.templates",
    "workflow.read",
    "workflow.save",
    "workflow.delete",
    "workflow.validate",
    "workflow.run",
    "workflow.run_saved",
    "task.create",
    "task.list",
    "task.get",
    "task.update",
    "task.stop",
    "task.output",
    "task.run",
    "task.background",
    "task.backgrounds",
    "schedule.create",
    "schedule.list",
    "schedule.delete",
    "schedule.run",
    "agent.profiles",
    "agent.save_profile",
    "team.create",
    "team.members",
    "team.send",
    "team.inbox",
    "team.run_member",
    "agent.run",
    "shell.run",
]
CHAT_TOOLS = ["filesystem.read", "filesystem.list", "search.grep"]
BROWSER_TOOLS = [*CODING_TOOLS, "web.search", "web.extract", "browser.open", "browser.download"]
RISKY_TOOLS = [
    "filesystem.write",
    "filesystem.delete",
    "filesystem.move",
    "patch.apply",
    "git.add",
    "git.commit",
    "test.run",
    "shell.run",
    "browser.open",
    "browser.download",
    "command.save",
    "command.delete",
    "plan.exit",
    "prompt.save",
    "prompt.delete",
    "permission.add_rule",
    "permission.remove_rule",
    "context.compact",
    "context.rewind",
    "session.export",
    "skill.install",
    "skill.uninstall",
    "skill.use",
    "skill.disable",
    "plugin.install",
    "plugin.uninstall",
    "plugin.enable",
    "plugin.disable",
    "mcp.configure",
    "mcp.enable",
    "mcp.disable",
    "mcp.remove",
    "mcp.clear",
    "memory.add",
    "memory.edit",
    "memory.forget",
    "hook.add",
    "hook.delete",
    "task.run",
    "schedule.create",
    "schedule.delete",
    "schedule.run",
    "workflow.save",
    "workflow.delete",
    "workflow.run",
    "workflow.run_saved",
    "task.background",
    "agent.save_profile",
    "team.run_member",
    "agent.run",
]
CODING_COMMANDS = "git,python,python3,pytest,make,node,npm,npx,bun"


def normalize_profile(profile: str) -> str:
    value = str(profile or "coding").strip().lower()
    if value not in {"coding", "chat", "browser"}:
        raise typer.BadParameter("profile must be coding, chat, or browser")
    return value


def workspace_path(profile: str, explicit: Optional[Path]) -> Optional[Path]:
    if explicit is not None:
        return explicit.expanduser().resolve()
    if profile in {"coding", "chat", "browser"}:
        return Path.cwd().resolve()
    return None


def enabled_tools(profile: str, tools: Optional[str]) -> list[str]:
    if tools:
        return [item.strip() for item in tools.split(",") if item.strip()]
    if profile == "browser":
        return list(BROWSER_TOOLS)
    if profile == "chat":
        return list(CHAT_TOOLS)
    return list(CODING_TOOLS)


def permission_settings(permission: str, profile: str) -> tuple[str, list[str]]:
    value = str(permission or "guarded").strip().lower()
    if value == "guarded":
        return "auto", list(RISKY_TOOLS if profile != "chat" else [])
    if value in {"auto", "ask", "deny"}:
        return value, []
    raise typer.BadParameter("permission must be guarded, auto, ask, or deny")


def settings_for_terminal(profile: str, sandbox_provider: Optional[str], workspace_root: Optional[Path] = None):
    runtime_settings = copy(settings)
    updates = {
        "SANDBOX_PROFILE": "browser" if profile == "browser" else ("coding" if profile == "coding" else "restricted"),
        "SANDBOX_ALLOWED_COMMANDS": _merge_csv(settings.agent.SANDBOX_ALLOWED_COMMANDS, CODING_COMMANDS),
    }
    if sandbox_provider:
        updates["SANDBOX_PROVIDER"] = sandbox_provider
    if os.getenv("AGENTS_TERMINAL_DB_PATH"):
        updates["DB_PATH"] = os.environ["AGENTS_TERMINAL_DB_PATH"]
    runtime_settings.agent = settings.agent.model_copy(update=updates)
    if workspace_root is not None:
        runtime_settings.server = copy(settings.server)
        runtime_settings.server.ROOT_PATH = str(Path(workspace_root).expanduser().resolve())
    return runtime_settings


def system_prompt(base_prompt: Optional[str], profile: str, active_workspace: Optional[Path]) -> Optional[str]:
    if profile not in {"coding", "browser"}:
        return base_prompt
    guidance = (
        "You are running inside a local coding terminal. Treat the bound workspace as the project root. "
        "Before answering project-structure questions, inspect the workspace using a short reconnaissance pass: "
        "list the root, read project marker files such as README.md, pyproject.toml, package.json, makefile, and scan key directories with search.grep when useful. "
        "Do not infer architecture from a directory listing alone when readable project files are available. "
        "When asked to implement code, use patch.apply or filesystem.write/delete/move for edits, git.* tools for repository operations, and test.discover/test.run for checks. "
        "Use command.discover/command.render/command.read/command.save/command.delete for prompt-backed workspace commands. "
        "Use tool.search when you need to inspect the current tool catalog; use skill.discover/skill.install/skill.uninstall/skill.use/skill.disable and plugin.discover/plugin.install/plugin.uninstall/plugin.enable/plugin.disable to manage local skill or plugin contributions. "
        "Use mcp.servers/mcp.configure/mcp.enable/mcp.disable/mcp.remove/mcp.clear to inspect or manage MCP server configuration, mcp.prompts/mcp.get_prompt for MCP prompt templates, and mcp.resources/mcp.read_resource for non-tool MCP context exposed by configured servers. "
        "Use prompt.templates/prompt.read/prompt.save/prompt.delete to manage reusable local prompt templates. "
        "Use session.status/session.summary/session.export, context.trace/context.messages, and context.compact/context.rewind to inspect, summarize, export, or trim current session context. "
        "Use permission.status, permission.sources, and permission.explain to inspect current tool permission rules and decisions before risky calls. "
        "Use hook.events/hook.list/hook.add/hook.delete for session-local request/response hook management. "
        "Use memory.* only for durable user, agent, or workspace facts that should affect future sessions. "
        "Use todo.write to maintain a structured task checklist for non-trivial multi-step work, and plan.enter/plan.exit when read-only design should precede editing. "
        "Use workflow.templates/workflow.read/workflow.save/workflow.delete to manage reusable workflow files, and workflow.validate/workflow.run/workflow.run_saved for explicit multi-node task or agent workflows. "
        "Use task.* tools to create, inspect, update, stop, run, or background tracked work items when a request should be managed as a task; use schedule.* to define and run reusable scheduled task definitions. "
        "Use agent.profiles/agent.save_profile for reusable agent roles; use team.create/team.members/team.send/team.inbox/team.run_member for scoped teammate coordination; use agent.run only for bounded side work that benefits from an isolated child agent result. "
        "Keep all file paths inside the current workspace. "
        "Answer concisely with concrete file-backed observations and avoid offering unrelated follow-up menus."
    )
    if active_workspace is not None:
        guidance += " Current workspace: %s." % active_workspace
    return "%s\n\n%s" % (base_prompt, guidance) if base_prompt else guidance


def local_user_id() -> str:
    return getpass.getuser() or "local"


def _merge_csv(*values: str) -> str:
    result: list[str] = []
    seen = set()
    for value in values:
        for item in str(value or "").split(","):
            item = item.strip()
            if item and item not in seen:
                seen.add(item)
                result.append(item)
    return ",".join(result)
