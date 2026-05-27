from __future__ import annotations

from typing import Any

from agents.kernel.governance.tool_impact_common import (
    ToolImpact,
    _domain,
    _impact,
    _list_of_dicts,
    _string,
    _truncate,
    _web_cost_estimate,
    _web_summary,
)


def _worktree_impact(name: str, arguments: dict[str, Any]) -> ToolImpact:
    if name == "worktree.enter":
        worktree_name = _string(arguments.get("name"))
        return _impact(
            name,
            "medium",
            operations=["worktree_create", "workspace_switch"],
            query=worktree_name,
            writes_files=True,
            summary="enter worktree %s" % worktree_name if worktree_name else "enter worktree",
        )
    action = _string(arguments.get("action"))
    remove = action == "remove"
    return _impact(
        name,
        "high" if remove else "medium",
        operations=["worktree_remove", "workspace_switch"] if remove else ["workspace_switch"],
        query=action,
        writes_files=remove,
        summary="remove worktree" if remove else "exit worktree",
    )


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
    operations = ["team_state_write", "subagent"] if name == "team.run_member" else ["team_state_write"] if name in {"team.create", "team.delete", "team.send", "team.inbox"} else ["team_read"]
    summary = {
        "team.create": "create team",
        "team.delete": "delete team",
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
        summary = {
            "workflow.save": "save workflow %s" % workflow_name if workflow_name else "save workflow",
            "workflow.delete": "delete workflow %s" % workflow_name if workflow_name else "delete workflow",
        }[name]
        return _impact(
            name,
            risk,
            operations=["workflow_write"],
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
