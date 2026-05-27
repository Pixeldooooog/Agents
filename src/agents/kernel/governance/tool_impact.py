from __future__ import annotations

import shlex

from agents.kernel.governance.sandbox import classify_tool_risk
from agents.kernel.governance.tool_impact_arguments import _canonical_arguments
from agents.kernel.governance.tool_impact_common import (
    ToolImpact,
    _browser_paths,
    _domain,
    _impact,
    _json_preview,
    _program_summary,
    _string,
    _truncate,
)
from agents.kernel.governance.tool_impact_domains import (
    _agent_impact,
    _hook_impact,
    _memory_impact,
    _patch_impact,
    _permission_summary,
    _plan_impact,
    _prompt_impact,
    _schedule_impact,
    _session_context_impact,
    _task_impact,
    _team_impact,
    _todo_impact,
    _web_impact,
    _workflow_impact,
    _worktree_impact,
)
from agents.kernel.governance.tool_rules import normalize_tool_name
from agents.kernel.schema import ToolCall


def describe_tool_impact(call: ToolCall) -> ToolImpact:
    name = normalize_tool_name(call.name)
    arguments = _canonical_arguments(call.name, name, dict(call.arguments or {}))
    risk = classify_tool_risk(name).value
    if name == "filesystem.read":
        return _impact(name, risk, operations=["file_read"], paths=[_string(arguments.get("path"))])
    if name == "filesystem.list":
        return _impact(name, risk, operations=["file_read"], paths=[_string(arguments.get("path") or ".")])
    if name == "search.grep":
        return _impact(name, risk, operations=["file_read"], paths=[_string(arguments.get("path") or ".")])
    if name == "search.glob":
        return _impact(name, risk, operations=["file_read"], paths=[_string(arguments.get("path") or ".")], query=_string(arguments.get("pattern")))
    if name == "lsp.query":
        path = _string(arguments.get("filePath") or arguments.get("file_path") or arguments.get("path"))
        operation = _string(arguments.get("operation"))
        return _impact(
            name,
            risk,
            operations=["file_read", "lsp_query"],
            paths=[path],
            query=operation,
            summary="LSP %s %s" % (operation, path) if operation and path else "LSP query",
        )
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
    if name == "notebook.edit":
        path = _string(arguments.get("notebook_path") or arguments.get("path"))
        mode = _string(arguments.get("edit_mode") or "replace")
        cell_id = _string(arguments.get("cell_id"))
        return _impact(
            name,
            risk,
            operations=["file_write", "notebook_edit"],
            paths=[path],
            writes_files=True,
            diff_preview=_truncate(_string(arguments.get("new_source"))),
            summary="%s notebook cell %s" % (mode, cell_id) if cell_id else "%s notebook cell" % mode,
        )
    if name == "patch.apply":
        return _patch_impact(name, risk, arguments)
    if name == "test.discover":
        return _impact(name, risk, operations=["file_read"], paths=[_string(arguments.get("path") or ".")])
    if name == "sleep.wait":
        duration = _string(arguments.get("duration_seconds"))
        return _impact(name, risk, operations=["wait"], query=duration, summary="wait %ss" % duration if duration else "wait")
    if name in {"shell.run", "test.run"}:
        command = _string(arguments.get("command") or ("pytest" if name == "test.run" else ""))
        return _impact(name, risk, operations=["process"], commands=[command], summary=_program_summary(command))
    if name == "shell.output":
        task_id = _string(arguments.get("task_id"))
        return _impact(name, risk, operations=["process_output_read"], query=task_id, summary="read shell output")
    if name == "shell.backgrounds":
        return _impact(name, risk, operations=["process_output_read"], summary="list background shell commands")
    if name == "shell.kill":
        task_id = _string(arguments.get("task_id"))
        return _impact(name, risk, operations=["process_control"], query=task_id, summary="stop shell command")
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
        if name == "skill.invoke":
            skill = _string(arguments.get("skill") or arguments.get("name"))
            operations = ["skill_invoke"]
            if _string(arguments.get("mode")).lower() == "fork":
                operations.append("subagent")
            return _impact(
                name,
                risk,
                operations=operations,
                query=skill,
                diff_preview=_truncate(_string(arguments.get("args"))),
                summary="invoke skill %s" % skill if skill else "invoke skill",
            )
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
            "mcp.detect_ide": "mcp_server_read",
            "mcp.configure_ide": "mcp_server_write",
            "mcp.ide_extension_status": "mcp_server_read",
            "mcp.install_ide_extension": "mcp_server_write",
            "mcp.enable": "mcp_server_write",
            "mcp.disable": "mcp_server_write",
            "mcp.remove": "mcp_server_write",
            "mcp.clear": "mcp_server_write",
            "mcp.reload": "mcp_server_reconnect",
            "mcp.reconnect": "mcp_server_reconnect",
            "mcp.read_resource": "mcp_resource_read",
            "mcp.resources": "mcp_resource_list",
            "mcp.get_prompt": "mcp_prompt_render",
            "mcp.prompts": "mcp_prompt_list",
        }.get(name, "mcp_operation")
        summary = {
            "mcp.servers": "list MCP servers",
            "mcp.configure": "configure MCP server",
            "mcp.detect_ide": "detect IDE MCP server",
            "mcp.configure_ide": "configure IDE MCP server",
            "mcp.ide_extension_status": "check IDE extension status",
            "mcp.install_ide_extension": "install IDE extension",
            "mcp.enable": "enable MCP server",
            "mcp.disable": "disable MCP server",
            "mcp.remove": "remove MCP server",
            "mcp.clear": "clear MCP server configuration",
            "mcp.reload": "reload MCP servers",
            "mcp.reconnect": "reconnect MCP server",
            "mcp.read_resource": "read MCP resource",
            "mcp.resources": "list MCP resources",
            "mcp.get_prompt": "render MCP prompt",
            "mcp.prompts": "list MCP prompts",
        }.get(name, "MCP operation")
        return _impact(name, risk, operations=[operation], query=query, summary=summary)
    if name.startswith("structured."):
        return _impact(
            name,
            risk,
            operations=["structured_output"],
            diff_preview=_truncate(_json_preview(arguments)),
            summary="return structured output",
        )
    if name.startswith("config."):
        setting = _string(arguments.get("setting"))
        writes = "value" in arguments
        return _impact(
            name,
            "medium" if writes else "low",
            operations=["config_write"] if writes else ["config_read"],
            query=setting,
            diff_preview=_truncate(_json_preview({"setting": setting, "value": arguments.get("value")})) if writes else "",
            summary="set config %s" % setting if writes and setting else "read config %s" % setting if setting else "manage config",
        )
    if name.startswith("user."):
        if name == "user.message":
            attachments = arguments.get("attachments") if isinstance(arguments.get("attachments"), list) else []
            return _impact(
                name,
                risk,
                operations=["user_message"],
                paths=[_string(item) for item in attachments if _string(item)],
                query=_truncate(_string(arguments.get("message")), 500),
                summary="message user",
            )
        questions = arguments.get("questions") if isinstance(arguments.get("questions"), list) else []
        text = " | ".join(_string(item.get("question")) for item in questions if isinstance(item, dict))
        return _impact(
            name,
            risk,
            operations=["user_interaction"],
            query=_truncate(text, 500),
            summary="ask user question",
        )
    if name.startswith("worktree."):
        return _worktree_impact(name, arguments)
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
