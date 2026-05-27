from __future__ import annotations

from typing import Any

from agents.kernel.governance.tool_impact_common import _list_of_dicts, _string


def _canonical_arguments(original_name: str, canonical_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if original_name == "Read" and canonical_name == "filesystem.read":
        payload = dict(arguments)
        if "path" not in payload and "file_path" in payload:
            payload["path"] = payload.get("file_path")
        return payload
    if original_name == "Write" and canonical_name == "filesystem.write":
        payload = dict(arguments)
        if "path" not in payload and "file_path" in payload:
            payload["path"] = payload.get("file_path")
        return payload
    if original_name == "Edit" and canonical_name == "patch.apply":
        return {
            "edits": [
                {
                    "path": _string(arguments.get("file_path")),
                    "old_text": _string(arguments.get("old_string")),
                    "new_text": _string(arguments.get("new_string")),
                    "replace_all": bool(arguments.get("replace_all")),
                }
            ]
        }
    if original_name == "MultiEdit" and canonical_name == "patch.apply":
        file_path = _string(arguments.get("file_path"))
        return {
            "edits": [
                {
                    "path": file_path,
                    "old_text": _string(edit.get("old_string")),
                    "new_text": _string(edit.get("new_string")),
                    "replace_all": bool(edit.get("replace_all")),
                }
                for edit in _list_of_dicts(arguments.get("edits"))
            ]
        }
    if original_name == "WebSearch" and canonical_name == "web.search":
        payload = dict(arguments)
        if "include_domains" not in payload and "allowed_domains" in payload:
            payload["include_domains"] = payload.get("allowed_domains")
        if "exclude_domains" not in payload and "blocked_domains" in payload:
            payload["exclude_domains"] = payload.get("blocked_domains")
        return payload
    if original_name == "WebFetch" and canonical_name == "web.extract":
        payload = dict(arguments)
        if "urls" not in payload and "url" in payload:
            payload["urls"] = [payload.get("url")]
        if "query" not in payload and "prompt" in payload:
            payload["query"] = payload.get("prompt")
        return payload
    if original_name == "TaskCreate" and canonical_name == "task.create":
        payload = dict(arguments)
        if "title" not in payload and "subject" in payload:
            payload["title"] = payload.get("subject")
        if "input" not in payload and "description" in payload:
            payload["input"] = payload.get("description")
        return payload
    if original_name == "TaskGet" and canonical_name == "task.get":
        return {"task_id": arguments.get("taskId", arguments.get("task_id", ""))}
    if original_name == "TaskUpdate" and canonical_name == "task.update":
        payload = dict(arguments)
        if "task_id" not in payload and "taskId" in payload:
            payload["task_id"] = payload.get("taskId")
        if "title" not in payload and "subject" in payload:
            payload["title"] = payload.get("subject")
        if "input" not in payload and "description" in payload:
            payload["input"] = payload.get("description")
        return payload
    if original_name in {"TaskOutput", "AgentOutputTool"} and canonical_name == "task.output":
        return {"task_id": arguments.get("task_id", "")}
    if original_name == "TaskStop" and canonical_name == "task.stop":
        return {"task_id": arguments.get("task_id", arguments.get("shell_id", ""))}
    if original_name == "KillShell" and canonical_name == "shell.kill":
        return {"task_id": arguments.get("task_id", arguments.get("shell_id", ""))}
    if original_name == "CronCreate" and canonical_name == "schedule.create":
        return {"title": arguments.get("prompt", ""), "schedule": arguments.get("cron", ""), "input": arguments.get("prompt", "")}
    if original_name == "CronDelete" and canonical_name == "schedule.delete":
        return {"schedule_id": arguments.get("id", "")}
    if original_name in {"Agent", "Task"} and canonical_name == "agent.run":
        payload = dict(arguments)
        if "agent_id" not in payload and "name" in payload:
            payload["agent_id"] = payload.get("name")
        return payload
    if original_name == "SendMessage" and canonical_name == "team.send":
        payload = dict(arguments)
        if "team_id" not in payload and "team_name" in payload:
            payload["team_id"] = payload.get("team_name")
        return payload
    if original_name == "TeamCreate" and canonical_name == "team.create":
        return {
            "team_id": arguments.get("team_name", ""),
            "name": arguments.get("team_name", ""),
            "description": arguments.get("description", ""),
        }
    if original_name == "Skill" and canonical_name == "skill.invoke":
        payload = dict(arguments)
        if "skill" not in payload and "name" in payload:
            payload["skill"] = payload.get("name")
        return payload
    if original_name == "Config" and canonical_name == "config.manage":
        return dict(arguments)
    if original_name == "AskUserQuestion" and canonical_name == "user.ask":
        return dict(arguments)
    if original_name in {"SendUserMessage", "Brief"} and canonical_name == "user.message":
        return dict(arguments)
    if original_name == "EnterWorktree" and canonical_name == "worktree.enter":
        return dict(arguments)
    if original_name == "ExitWorktree" and canonical_name == "worktree.exit":
        return dict(arguments)
    return arguments
