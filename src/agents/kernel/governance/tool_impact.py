from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from agents.kernel.governance.sandbox import classify_tool_risk
from agents.kernel.schema import ToolCall


MAX_PREVIEW_CHARS = 4000


@dataclass(frozen=True)
class ToolImpact:
    tool_name: str
    risk: str
    operations: list[str] = field(default_factory=list)
    paths: list[str] = field(default_factory=list)
    commands: list[str] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)
    writes_files: bool = False
    requires_network: bool = False
    external_disclosure: bool = False
    query: str = ""
    cost_estimate: dict[str, Any] = field(default_factory=dict)
    diff_preview: str = ""
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "tool_name": self.tool_name,
            "risk": self.risk,
            "operations": list(self.operations),
            "paths": list(self.paths),
            "commands": list(self.commands),
            "domains": list(self.domains),
            "writes_files": self.writes_files,
            "requires_network": self.requires_network,
            "external_disclosure": self.external_disclosure,
            "query": self.query,
            "cost_estimate": dict(self.cost_estimate),
        }
        if self.diff_preview:
            payload["diff_preview"] = self.diff_preview
        if self.summary:
            payload["summary"] = self.summary
        return payload


def describe_tool_impact(call: ToolCall) -> ToolImpact:
    name = call.name
    arguments = dict(call.arguments or {})
    risk = classify_tool_risk(name).value
    if name == "filesystem.read":
        return _impact(name, risk, operations=["file_read"], paths=[_string(arguments.get("path"))])
    if name == "filesystem.list":
        return _impact(name, risk, operations=["file_read"], paths=[_string(arguments.get("path") or ".")])
    if name == "search.grep":
        return _impact(name, risk, operations=["file_read"], paths=[_string(arguments.get("path") or ".")])
    if name.startswith("command."):
        command_name = _string(arguments.get("name") or arguments.get("query"))
        if name in {"command.save", "command.delete"}:
            path = ".agents/commands/%s.md" % command_name.lstrip("/") if command_name else ""
            return _impact(
                name,
                risk,
                operations=["command_write"],
                paths=[path],
                writes_files=True,
                query=command_name,
                diff_preview=_truncate(_string(arguments.get("content"))),
                summary="save command" if name == "command.save" else "delete command",
            )
        return _impact(
            name,
            risk,
            operations=["command_read"],
            query=command_name,
            summary="render command" if name == "command.render" else "read command" if name == "command.read" else "discover commands",
        )
    if name == "filesystem.write":
        path = _string(arguments.get("path"))
        return _impact(
            name,
            risk,
            operations=["file_write"],
            paths=[path],
            writes_files=True,
            diff_preview=_truncate(_string(arguments.get("content"))),
            summary="write %s" % path if path else "write file",
        )
    if name == "filesystem.delete":
        path = _string(arguments.get("path"))
        return _impact(
            name,
            risk,
            operations=["file_delete"],
            paths=[path],
            writes_files=True,
            summary="delete %s" % path if path else "delete file",
        )
    if name == "filesystem.move":
        source = _string(arguments.get("source_path"))
        destination = _string(arguments.get("destination_path"))
        return _impact(
            name,
            risk,
            operations=["file_move"],
            paths=[source, destination],
            writes_files=True,
            summary="move %s to %s" % (source, destination) if source and destination else "move file",
        )
    if name == "patch.apply":
        return _patch_impact(name, risk, arguments)
    if name == "test.discover":
        return _impact(name, risk, operations=["file_read"], paths=[_string(arguments.get("path") or ".")])
    if name in {"shell.run", "test.run"}:
        command = _string(arguments.get("command") or ("pytest" if name == "test.run" else ""))
        return _impact(name, risk, operations=["process"], commands=[command], summary=_program_summary(command))
    if name == "git.status":
        return _impact(name, risk, operations=["process"], commands=["git status --short"])
    if name == "git.diff":
        command = "git diff"
        if arguments.get("staged"):
            command = "git diff --staged"
        path = _string(arguments.get("path"))
        if path:
            command = "%s -- %s" % (command, shlex.quote(path))
        return _impact(name, risk, operations=["process"], commands=[command], paths=[path])
    if name == "git.add":
        paths = [_string(item) for item in arguments.get("paths") or [] if _string(item)]
        command = "git add -A" if arguments.get("all") else "git add -- %s" % " ".join(shlex.quote(path) for path in paths)
        return _impact(name, risk, operations=["process", "git_index_write"], commands=[command], paths=paths, writes_files=True)
    if name == "git.commit":
        paths = [_string(item) for item in arguments.get("paths") or [] if _string(item)]
        command = "git commit"
        if arguments.get("all"):
            command += " -a"
        if arguments.get("allow_empty"):
            command += " --allow-empty"
        return _impact(name, risk, operations=["process", "git_commit"], commands=[command], paths=paths, writes_files=True)
    if name == "git.log":
        return _impact(name, risk, operations=["process"], commands=["git log"], paths=[_string(arguments.get("path"))])
    if name == "git.show":
        revision = _string(arguments.get("revision") or "HEAD")
        return _impact(name, risk, operations=["process"], commands=["git show %s" % revision], paths=[_string(arguments.get("path"))])
    if name.startswith("tool."):
        query = _string(arguments.get("query"))
        return _impact(name, risk, operations=["tool_catalog_read"], query=query, summary="search tools")
    if name.startswith("skill."):
        query = _string(arguments.get("query"))
        if name in {"skill.install", "skill.uninstall", "skill.use", "skill.disable"}:
            summary = {
                "skill.install": "install skill",
                "skill.uninstall": "uninstall skill",
                "skill.use": "enable skill",
                "skill.disable": "disable skill",
            }.get(name, "skill state change")
            return _impact(
                name,
                risk,
                operations=["extension_state_write"],
                paths=[_string(arguments.get("source"))],
                query=_string(arguments.get("name") or arguments.get("source")),
                writes_files=name in {"skill.install", "skill.uninstall"},
                summary=summary,
            )
        return _impact(name, risk, operations=["skill_catalog_read"], query=query, summary="discover skills")
    if name.startswith("plugin."):
        if name in {"plugin.install", "plugin.uninstall", "plugin.enable", "plugin.disable"}:
            summary = {
                "plugin.install": "install plugin",
                "plugin.uninstall": "uninstall plugin",
                "plugin.enable": "enable plugin",
                "plugin.disable": "disable plugin",
            }.get(name, "plugin state change")
            return _impact(
                name,
                risk,
                operations=["extension_state_write"],
                paths=[_string(arguments.get("source"))],
                query=_string(arguments.get("name") or arguments.get("source")),
                writes_files=name in {"plugin.install", "plugin.uninstall"},
                summary=summary,
            )
        return _impact(name, risk, operations=["plugin_catalog_read"], query=_string(arguments.get("query")), summary="discover plugins")
    if name.startswith("mcp."):
        query = _string(arguments.get("uri") or arguments.get("uri_prefix") or arguments.get("name") or arguments.get("query") or arguments.get("command"))
        operation = {
            "mcp.servers": "mcp_server_read",
            "mcp.configure": "mcp_server_write",
            "mcp.enable": "mcp_server_write",
            "mcp.disable": "mcp_server_write",
            "mcp.remove": "mcp_server_write",
            "mcp.clear": "mcp_server_write",
            "mcp.read_resource": "mcp_resource_read",
            "mcp.resources": "mcp_resource_list",
            "mcp.get_prompt": "mcp_prompt_render",
            "mcp.prompts": "mcp_prompt_list",
        }.get(name, "mcp_operation")
        summary = {
            "mcp.servers": "list MCP servers",
            "mcp.configure": "configure MCP server",
            "mcp.enable": "enable MCP server",
            "mcp.disable": "disable MCP server",
            "mcp.remove": "remove MCP server",
            "mcp.clear": "clear MCP server configuration",
            "mcp.read_resource": "read MCP resource",
            "mcp.resources": "list MCP resources",
            "mcp.get_prompt": "render MCP prompt",
            "mcp.prompts": "list MCP prompts",
        }.get(name, "MCP operation")
        return _impact(name, risk, operations=[operation], query=query, summary=summary)
    if name.startswith("memory."):
        return _memory_impact(name, risk, arguments)
    if name.startswith("todo."):
        return _todo_impact(name, risk, arguments)
    if name.startswith("plan."):
        return _plan_impact(name, risk, arguments)
    if name.startswith("prompt."):
        return _prompt_impact(name, risk, arguments)
    if name.startswith("context.") or name.startswith("session."):
        return _session_context_impact(name, risk, arguments)
    if name.startswith("permission."):
        writes_permission = name in {"permission.add_rule", "permission.remove_rule"}
        return _impact(
            name,
            risk,
            operations=["permission_write"] if writes_permission else ["permission_read"],
            query=_string(arguments.get("tool")),
            summary=_permission_summary(name, arguments),
        )
    if name.startswith("hook."):
        return _hook_impact(name, risk, arguments)
    if name.startswith("team."):
        return _team_impact(name, risk, arguments)
    if name.startswith("workflow."):
        return _workflow_impact(name, risk, arguments)
    if name.startswith("task."):
        return _task_impact(name, risk, arguments)
    if name.startswith("schedule."):
        return _schedule_impact(name, risk, arguments)
    if name.startswith("agent."):
        return _agent_impact(name, risk, arguments)
    if name.startswith("browser.") or name.startswith("web."):
        if name.startswith("web."):
            return _web_impact(name, risk, arguments)
        url = _string(arguments.get("url"))
        domain = _domain(url)
        return _impact(
            name,
            risk,
            operations=["network"],
            domains=[domain],
            requires_network=True,
            paths=_browser_paths(name, arguments),
            writes_files=name in {"browser.open", "browser.download"},
            summary="open %s" % domain if domain else "browser network access",
        )
    if name.startswith("mcp_"):
        return _impact(name, risk, operations=["mcp_call"], summary="external MCP tool call")
    return _impact(name, risk, operations=["tool_call"])


def _hook_impact(name: str, risk: str, arguments: dict[str, Any]) -> ToolImpact:
    hook_id = _string(arguments.get("hook_id"))
    event = _string(arguments.get("event"))
    action = _string(arguments.get("action"))
    operations = ["hook_state_write"] if name in {"hook.add", "hook.delete"} else ["hook_read"]
    summary = {
        "hook.events": "list hook events",
        "hook.list": "list hooks",
        "hook.add": "add hook",
        "hook.delete": "delete hook %s" % hook_id if hook_id else "delete hook",
    }.get(name, "hook operation")
    return _impact(name, risk, operations=operations, query=hook_id or event, diff_preview=_truncate("%s %s" % (event, action)), summary=summary)


def _task_impact(name: str, risk: str, arguments: dict[str, Any]) -> ToolImpact:
    task_id = _string(arguments.get("task_id"))
    title = _string(arguments.get("title"))
    status = _string(arguments.get("status"))
    operations = ["task_state_write"] if name in {"task.create", "task.update", "task.stop", "task.run", "task.background"} else ["task_read"]
    if name in {"task.run", "task.background"}:
        operations = ["task_state_write", "subagent"]
    summary = {
        "task.create": "create task %s" % title if title else "create task",
        "task.list": "list tasks",
        "task.get": "read task %s" % task_id if task_id else "read task",
        "task.update": "set task %s to %s" % (task_id, status) if task_id and status else "update task",
        "task.stop": "cancel task %s" % task_id if task_id else "cancel task",
        "task.output": "read task output %s" % task_id if task_id else "read task output",
        "task.run": "run task %s" % task_id if task_id else "create and run task %s" % title if title else "run task",
        "task.background": "background task %s" % task_id if task_id else "create and background task %s" % title if title else "background task",
        "task.backgrounds": "list background tasks",
    }.get(name, "task operation")
    return _impact(name, risk, operations=operations, diff_preview=_truncate(_string(arguments.get("input"))), summary=summary)


def _schedule_impact(name: str, risk: str, arguments: dict[str, Any]) -> ToolImpact:
    schedule_id = _string(arguments.get("schedule_id"))
    title = _string(arguments.get("title"))
    schedule = _string(arguments.get("schedule"))
    if name == "schedule.run":
        return _impact(
            name,
            risk,
            operations=["schedule_run", "task_state_write", "subagent"],
            query=schedule_id,
            summary="run scheduled task %s" % schedule_id if schedule_id else "run scheduled task",
        )
    operations = ["schedule_state_write"] if name in {"schedule.create", "schedule.delete"} else ["schedule_read"]
    summary = {
        "schedule.create": "create schedule",
        "schedule.list": "list schedules",
        "schedule.delete": "delete schedule %s" % schedule_id if schedule_id else "delete schedule",
    }.get(name, "schedule operation")
    return _impact(name, risk, operations=operations, query=schedule_id, diff_preview=_truncate("%s %s" % (title, schedule)), summary=summary)


def _todo_impact(name: str, risk: str, arguments: dict[str, Any]) -> ToolImpact:
    todos = arguments.get("todos") or []
    count = len(todos) if isinstance(todos, list) else 0
    summary = "update %d todo(s)" % count if name == "todo.write" else "read todos"
    operation = "todo_state_write" if name == "todo.write" else "todo_read"
    return _impact(name, risk, operations=[operation], summary=summary)


def _memory_impact(name: str, risk: str, arguments: dict[str, Any]) -> ToolImpact:
    memory_id = _string(arguments.get("memory_id"))
    scope = _string(arguments.get("scope"))
    content = _string(arguments.get("content"))
    operations = ["memory_write"] if name in {"memory.add", "memory.edit", "memory.forget"} else ["memory_read"]
    summary = {
        "memory.list": "list memories",
        "memory.add": "save %s memory" % (scope or "workspace"),
        "memory.edit": "edit memory %s" % memory_id if memory_id else "edit memory",
        "memory.forget": "forget memory %s" % memory_id if memory_id else "forget memory",
    }.get(name, "memory operation")
    return _impact(name, risk, operations=operations, diff_preview=_truncate(content), summary=summary)


def _prompt_impact(name: str, risk: str, arguments: dict[str, Any]) -> ToolImpact:
    prompt_name = _string(arguments.get("name"))
    content = _string(arguments.get("content"))
    operations = ["prompt_write"] if name in {"prompt.save", "prompt.delete"} else ["prompt_read"]
    summary = {
        "prompt.templates": "list prompt templates",
        "prompt.read": "read prompt template %s" % prompt_name if prompt_name else "read prompt template",
        "prompt.render": "render prompt template %s" % prompt_name if prompt_name else "render prompt template",
        "prompt.save": "save prompt template %s" % prompt_name if prompt_name else "save prompt template",
        "prompt.delete": "delete prompt template %s" % prompt_name if prompt_name else "delete prompt template",
    }.get(name, "prompt template operation")
    path = ".agents/prompts/%s.md" % prompt_name if prompt_name else ""
    return _impact(name, risk, operations=operations, paths=[path], writes_files=name in {"prompt.save", "prompt.delete"}, diff_preview=_truncate(content), summary=summary)


def _permission_summary(name: str, arguments: dict[str, Any]) -> str:
    tool = _string(arguments.get("tool"))
    behavior = _string(arguments.get("behavior"))
    return {
        "permission.status": "read permission status",
        "permission.sources": "read permission sources",
        "permission.explain": "explain permission",
        "permission.add_rule": "add %s permission rule for %s" % (behavior or "tool", tool) if tool else "add permission rule",
        "permission.remove_rule": "remove permission rule for %s" % tool if tool else "remove permission rule",
    }.get(name, "permission operation")


def _plan_impact(name: str, risk: str, arguments: dict[str, Any]) -> ToolImpact:
    plan = _string(arguments.get("plan"))
    summary = {
        "plan.enter": "enter plan mode",
        "plan.status": "read plan status",
        "plan.exit": "present plan and exit plan mode",
    }.get(name, "plan operation")
    operations = ["plan_state_write"] if name in {"plan.enter", "plan.exit"} else ["plan_read"]
    return _impact(name, risk, operations=operations, diff_preview=_truncate(plan), summary=summary)


def _session_context_impact(name: str, risk: str, arguments: dict[str, Any]) -> ToolImpact:
    if name == "session.export":
        path = _string(arguments.get("path"))
        return _impact(
            name,
            risk,
            operations=["session_export"],
            paths=[path],
            writes_files=True,
            summary="export current session",
        )
    operations = ["context_write"] if name in {"context.compact", "context.rewind"} else ["context_read"]
    summary = {
        "session.status": "read session status",
        "session.summary": "summarize current session",
        "context.trace": "read context trace",
        "context.messages": "read context messages",
        "context.compact": "compact session context",
        "context.rewind": "rewind session context",
    }.get(name, "session context operation")
    return _impact(name, risk, operations=operations, summary=summary)


def _team_impact(name: str, risk: str, arguments: dict[str, Any]) -> ToolImpact:
    operations = ["team_state_write", "subagent"] if name == "team.run_member" else ["team_state_write"] if name in {"team.create", "team.send", "team.inbox"} else ["team_read"]
    summary = {
        "team.create": "create team",
        "team.members": "list team members",
        "team.send": "send team message",
        "team.inbox": "read team inbox",
        "team.run_member": "run team member",
    }.get(name, "team operation")
    preview = _string(arguments.get("message") or arguments.get("prompt"))
    return _impact(name, risk, operations=operations, query=_string(arguments.get("team_id") or arguments.get("to") or arguments.get("agent_id")), diff_preview=_truncate(preview), summary=summary)


def _agent_impact(name: str, risk: str, arguments: dict[str, Any]) -> ToolImpact:
    if name in {"agent.profiles", "agent.save_profile"}:
        return _impact(
            name,
            risk,
            operations=["agent_profile_write"] if name == "agent.save_profile" else ["agent_profile_read"],
            query=_string(arguments.get("agent_id") or arguments.get("query")),
            summary="save agent profile" if name == "agent.save_profile" else "list agent profiles",
        )
    description = _string(arguments.get("description"))
    prompt = _string(arguments.get("prompt"))
    return _impact(
        name,
        risk,
        operations=["subagent"],
        summary="run child agent: %s" % description if description else "run child agent",
        diff_preview=_truncate(prompt),
    )


def _workflow_impact(name: str, risk: str, arguments: dict[str, Any]) -> ToolImpact:
    nodes = arguments.get("nodes") or []
    count = len(nodes) if isinstance(nodes, list) else 0
    workflow_name = _string(arguments.get("name"))
    path = ".agents/workflows/%s.json" % workflow_name if workflow_name else ""
    if name in {"workflow.run", "workflow.run_saved"}:
        operations = ["workflow_run", "subagent"]
        summary = (
            "run saved workflow %s" % workflow_name
            if name == "workflow.run_saved" and workflow_name
            else "run %d workflow node(s)" % count
        )
        return _impact(name, risk, operations=operations, paths=[path], diff_preview=_truncate(str(nodes)), summary=summary)
    if name in {"workflow.save", "workflow.delete"}:
        operation = "workflow_write"
        summary = {
            "workflow.save": "save workflow %s" % workflow_name if workflow_name else "save workflow",
            "workflow.delete": "delete workflow %s" % workflow_name if workflow_name else "delete workflow",
        }[name]
        return _impact(
            name,
            risk,
            operations=[operation],
            paths=[path],
            writes_files=True,
            diff_preview=_truncate(str(nodes)),
            summary=summary,
        )
    summary = {
        "workflow.templates": "list saved workflows",
        "workflow.read": "read workflow %s" % workflow_name if workflow_name else "read workflow",
        "workflow.validate": "validate %d workflow node(s)" % count,
    }.get(name, "workflow operation")
    operation = "workflow_validate" if name == "workflow.validate" else "workflow_read"
    return _impact(name, risk, operations=[operation], paths=[path], diff_preview=_truncate(str(nodes)), summary=summary)


def _web_impact(name: str, risk: str, arguments: dict[str, Any]) -> ToolImpact:
    query = _string(arguments.get("query"))
    urls = [_string(url) for url in arguments.get("urls") or [] if _string(url)]
    url = _string(arguments.get("url"))
    if url:
        urls.append(url)
    domains = [_domain(item) for item in urls]
    domains.extend(_string(item) for item in arguments.get("include_domains") or [] if _string(item))
    domains.extend(_string(item) for item in arguments.get("exclude_domains") or [] if _string(item))
    return _impact(
        name,
        risk,
        operations=["network", "external_search"] if name == "web.search" else ["network", "external_fetch"],
        domains=domains,
        requires_network=True,
        external_disclosure=True,
        query=query,
        cost_estimate=_web_cost_estimate(name, arguments),
        summary=_web_summary(name, query, domains),
    )


def _patch_impact(name: str, risk: str, arguments: dict[str, Any]) -> ToolImpact:
    paths: list[str] = []
    preview_parts: list[str] = []
    operations: list[str] = []
    for edit in _list_of_dicts(arguments.get("edits")):
        path = _string(edit.get("path"))
        if not path:
            continue
        paths.append(path)
        operations.append("file_patch")
        preview_parts.append(
            "%s\n--- old\n%s\n+++ new\n%s"
            % (path, _truncate(_string(edit.get("old_text")), 800), _truncate(_string(edit.get("new_text")), 800))
        )
    for create in _list_of_dicts(arguments.get("creates")):
        path = _string(create.get("path"))
        if not path:
            continue
        paths.append(path)
        operations.append("file_create")
        preview_parts.append("%s\n+++ content\n%s" % (path, _truncate(_string(create.get("content")), 800)))
    return _impact(
        name,
        risk,
        operations=operations or ["file_patch"],
        paths=paths,
        writes_files=not bool(arguments.get("dry_run")),
        diff_preview=_truncate("\n\n".join(preview_parts)),
        summary="patch %d file(s)" % len(set(paths)) if paths else "patch files",
    )


def _impact(
    tool_name: str,
    risk: str,
    *,
    operations: list[str] | None = None,
    paths: list[str] | None = None,
    commands: list[str] | None = None,
    domains: list[str] | None = None,
    writes_files: bool = False,
    requires_network: bool = False,
    external_disclosure: bool = False,
    query: str = "",
    cost_estimate: dict[str, Any] | None = None,
    diff_preview: str = "",
    summary: str = "",
) -> ToolImpact:
    return ToolImpact(
        tool_name=tool_name,
        risk=risk,
        operations=_unique(operations or []),
        paths=_unique(item for item in (paths or []) if item),
        commands=_unique(item for item in (commands or []) if item),
        domains=_unique(item for item in (domains or []) if item),
        writes_files=writes_files,
        requires_network=requires_network,
        external_disclosure=external_disclosure,
        query=query,
        cost_estimate=dict(cost_estimate or {}),
        diff_preview=diff_preview,
        summary=summary,
    )


def _web_cost_estimate(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name == "web.search":
        depth = _string(arguments.get("search_depth") or "basic")
        raw_cost = 1 if arguments.get("include_raw_content") else 0
        return {
            "provider": "tavily",
            "estimated_credits": (2 if depth == "advanced" else 1) + raw_cost,
            "basis": depth,
        }
    if name == "web.extract":
        urls = arguments.get("urls") or []
        depth = _string(arguments.get("extract_depth") or "basic")
        per_url = 2 if depth == "advanced" else 1
        return {"provider": "tavily", "estimated_credits": per_url * max(1, len(urls)), "basis": depth}
    if name == "web.map":
        return {"provider": "tavily", "estimated_credits": 1, "basis": "map"}
    return {}


def _web_summary(name: str, query: str, domains: list[str]) -> str:
    if name == "web.search":
        return "search web for %s" % query if query else "search web"
    if domains:
        return "%s %s" % (name, ", ".join(_unique(domains)[:3]))
    return name


def _browser_paths(name: str, arguments: dict[str, Any]) -> list[str]:
    if name == "browser.open":
        return [_string(arguments.get("output_path") or "artifact://run/{run_id}/downloads/browser-open.html")]
    if name == "browser.download":
        return [_string(arguments.get("path") or "artifact://run/{run_id}/downloads/download.bin")]
    return []


def _domain(url: str) -> str:
    parsed = urlparse(url)
    return parsed.netloc.lower()


def _program_summary(command: str) -> str:
    try:
        parts = shlex.split(command)
    except ValueError:
        return command
    return "run %s" % parts[0] if parts else command


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _truncate(value: str, limit: int = MAX_PREVIEW_CHARS) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return text[:limit] + "\n[truncated]"


def _string(value: Any) -> str:
    return str(value or "")


def _unique(values) -> list[str]:
    result: list[str] = []
    seen = set()
    for value in values:
        text = str(value or "")
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result
