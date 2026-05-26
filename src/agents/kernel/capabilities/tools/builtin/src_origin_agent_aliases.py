from __future__ import annotations

import json
from typing import Any

from agents.kernel.capabilities.sandbox.text import DEFAULT_TEXT_READ_MAX_BYTES
from agents.kernel.capabilities.tools.builtin.agents import agent_run
from agents.kernel.capabilities.tools.builtin.config import (
    CONFIG_MANAGE_SCHEMA,
    CONFIG_VALUE_UNSET,
    config_manage,
    format_config_result,
)
from agents.kernel.capabilities.tools.builtin.filesystem import format_read_file_result, read_file, write_file
from agents.kernel.capabilities.tools.builtin.lsp import (
    LSP_QUERY_SCHEMA,
    format_lsp_result,
    lsp_query,
)
from agents.kernel.capabilities.tools.builtin.notebook import (
    NOTEBOOK_EDIT_SCHEMA,
    format_notebook_edit_result,
    notebook_edit,
)
from agents.kernel.capabilities.tools.builtin.patch import (
    apply_src_origin_edit,
    apply_src_origin_multi_edit,
    format_src_origin_edit_result,
    format_src_origin_multi_edit_result,
)
from agents.kernel.capabilities.tools.builtin.planning import (
    TODO_WRITE_SCHEMA,
    format_todo_write_result,
    todo_write,
)
from agents.kernel.capabilities.tools.builtin.registration_helpers import register_builtin_tool as _register_builtin_tool
from agents.kernel.capabilities.tools.builtin.search import (
    GLOB_SCHEMA,
    GREP_SCHEMA,
    format_glob_result,
    format_grep_result,
    glob,
    grep,
)
from agents.kernel.capabilities.tools.builtin.shell import RUN_COMMAND_SCHEMA, run_command
from agents.kernel.capabilities.tools.builtin.skill_invocation import (
    SKILL_INVOKE_SCHEMA,
    format_skill_invoke_result,
    skill_invoke,
)
from agents.kernel.capabilities.tools.builtin.sleep import SLEEP_WAIT_SCHEMA, sleep_wait
from agents.kernel.capabilities.tools.builtin.src_origin_discovery_aliases import register_src_origin_discovery_aliases
from agents.kernel.capabilities.tools.builtin.src_origin_plan_aliases import register_src_origin_plan_aliases
from agents.kernel.capabilities.tools.builtin.src_origin_schedule_aliases import register_src_origin_schedule_aliases
from agents.kernel.capabilities.tools.builtin.src_origin_task_aliases import register_src_origin_task_aliases
from agents.kernel.capabilities.tools.builtin.structured import (
    format_structured_output_result,
    structured_output,
    structured_output_schema_from_metadata,
)
from agents.kernel.capabilities.tools.builtin.tasks import task_background
from agents.kernel.capabilities.tools.builtin.teams import team_create, team_delete, team_send
from agents.kernel.capabilities.tools.builtin.user_interaction import (
    ASK_USER_QUESTION_SCHEMA,
    USER_MESSAGE_SCHEMA,
    ask_user_question,
    format_ask_user_question_result,
    format_user_message_result,
    send_user_message,
)
from agents.kernel.capabilities.tools.builtin.worktree import (
    WORKTREE_ENTER_SCHEMA,
    WORKTREE_EXIT_SCHEMA,
    enter_worktree,
    exit_worktree,
    format_worktree_result,
)
from agents.kernel.capabilities.tools.context import ToolRuntimeContext
from agents.kernel.capabilities.tools.registry import ToolRegistry
from agents.kernel.capabilities.web import WebSearchProvider


def _agent_spec_metadata(context: ToolRuntimeContext) -> dict:
    metadata = getattr(getattr(context, "agent_spec", None), "metadata", None)
    return dict(metadata) if isinstance(metadata, dict) else {}


SRC_ORIGIN_READ_SCHEMA = {
    "type": "object",
    "properties": {
        "file_path": {"type": "string", "description": "Path to the file to read."},
        "offset": {"type": "integer", "minimum": 0},
        "limit": {"type": "integer", "minimum": 1},
        "pages": {"type": "string", "description": "Page range for PDF files."},
        "max_bytes": {"type": "integer", "minimum": 1, "maximum": DEFAULT_TEXT_READ_MAX_BYTES},
    },
    "required": ["file_path"],
}

SRC_ORIGIN_WRITE_SCHEMA = {
    "type": "object",
    "properties": {
        "file_path": {"type": "string", "description": "Path to the file to write."},
        "content": {"type": "string", "description": "The content to write to the file."},
    },
    "required": ["file_path", "content"],
}

SRC_ORIGIN_EDIT_SCHEMA = {
    "type": "object",
    "properties": {
        "file_path": {"type": "string", "description": "Path to the file to edit."},
        "old_string": {"type": "string", "description": "Text to replace."},
        "new_string": {"type": "string", "description": "Replacement text."},
        "replace_all": {"type": "boolean", "description": "Replace all occurrences."},
    },
    "required": ["file_path", "old_string", "new_string"],
}

SRC_ORIGIN_MULTI_EDIT_SCHEMA = {
    "type": "object",
    "properties": {
        "file_path": {"type": "string", "description": "Path to the file to edit."},
        "edits": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "old_string": {"type": "string", "description": "Text to replace."},
                    "new_string": {"type": "string", "description": "Replacement text."},
                    "replace_all": {"type": "boolean", "description": "Replace all occurrences."},
                },
                "required": ["old_string", "new_string"],
            },
        },
    },
    "required": ["file_path", "edits"],
}

SRC_ORIGIN_EMPTY_SCHEMA = {"type": "object", "properties": {}}

SRC_ORIGIN_AGENT_SCHEMA = {
    "type": "object",
    "properties": {
        "description": {"type": "string", "description": "A short description of the task."},
        "prompt": {"type": "string", "description": "The task for the agent to perform."},
        "subagent_type": {"type": "string"},
        "model": {"type": "string", "enum": ["sonnet", "opus", "haiku"]},
        "run_in_background": {"type": "boolean"},
        "name": {"type": "string"},
        "team_name": {"type": "string"},
        "mode": {"type": "string"},
        "isolation": {"type": "string", "enum": ["worktree", "remote"]},
        "cwd": {"type": "string"},
    },
    "required": ["description", "prompt"],
}

SRC_ORIGIN_SEND_MESSAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "to": {"type": "string", "description": "Recipient teammate name or *."},
        "summary": {"type": "string", "description": "Short message summary."},
        "message": {
            "description": "Plain text or structured message content.",
            "anyOf": [{"type": "string"}, {"type": "object"}],
        },
        "team_name": {"type": "string", "description": "Optional team id/name override."},
    },
    "required": ["to", "message"],
}

SRC_ORIGIN_TEAM_CREATE_SCHEMA = {
    "type": "object",
    "properties": {
        "team_name": {"type": "string", "description": "Name for the new team to create."},
        "description": {"type": "string", "description": "Team description or purpose."},
        "agent_type": {"type": "string", "description": "Role of the team lead."},
    },
    "required": ["team_name"],
}


def _src_origin_metadata(metadata: dict[str, Any] | None, **extra: Any) -> dict[str, Any]:
    payload = dict(metadata or {})
    for key, value in extra.items():
        if value not in (None, ""):
            payload[key] = value
    return payload


async def _src_origin_agent(
    context: ToolRuntimeContext,
    *,
    description: str,
    prompt: str,
    subagent_type: str = "",
    model: str = "",
    run_in_background: bool = False,
    name: str = "",
    team_name: str = "",
    mode: str = "",
    isolation: str = "",
    cwd: str = "",
) -> dict:
    if run_in_background:
        payload = await task_background(
            context,
            title=description,
            input=prompt,
            metadata=_src_origin_metadata(
                {"source": "Agent"},
                subagent_type=subagent_type,
                model=model,
                name=name,
                team_name=team_name,
                mode=mode,
                isolation=isolation,
                cwd=cwd,
            ),
            step_name="agent",
        )
        payload["status"] = "async_launched"
        payload["agentId"] = payload["task"]["task_id"]
        payload["description"] = description
        payload["prompt"] = prompt
        return payload
    return await agent_run(
        context,
        prompt=prompt,
        description=description,
        agent_id=name,
    )


async def _src_origin_send_message(
    context: ToolRuntimeContext,
    *,
    to: str,
    message: Any,
    summary: str = "",
    team_name: str = "",
) -> dict:
    content = message if isinstance(message, str) else json.dumps(message, ensure_ascii=False, sort_keys=True)
    team_id = str(team_name or (next(iter(context.teams)) if len(context.teams) == 1 else ""))
    return await team_send(
        context,
        to=to,
        message=content,
        team_id=team_id,
        from_agent="team-lead",
        message_type="message",
    )


async def _src_origin_team_create(
    context: ToolRuntimeContext,
    *,
    team_name: str,
    description: str = "",
    agent_type: str = "",
) -> dict:
    lead_agent_id = "team-lead"
    payload = await team_create(
        context,
        team_id=team_name,
        name=team_name,
        description=description,
        members=[
            {
                "agent_id": lead_agent_id,
                "name": "team-lead",
                "role": agent_type or "team-lead",
            }
        ],
    )
    payload.update(
        {
            "team_name": payload["team"]["name"],
            "team_file_path": ".agents/teams/%s.json" % payload["team"]["team_id"],
            "lead_agent_id": lead_agent_id,
        }
    )
    return payload


def register_src_origin_aliases(
    registry: ToolRegistry,
    context: ToolRuntimeContext,
    active_web_provider: WebSearchProvider,
) -> None:
    structured_schema = structured_output_schema_from_metadata(_agent_spec_metadata(context))
    _register_builtin_tool(
        registry,
        name="Read",
        description="Read a file from the current workspace. src-origin alias for filesystem.read.",
        parameters=SRC_ORIGIN_READ_SCHEMA,
        handler=lambda file_path, offset=1, limit=None, pages=None, max_bytes=None: read_file(
            context,
            file_path,
            max_bytes=max_bytes,
            offset=offset,
            limit=limit,
            pages=pages,
        ),
        metadata={"alias_of": "filesystem.read", "src_origin_tool": "Read"},
        read_only=True,
        path_parameters=("file_path",),
        activity_kind="workspace",
        activity_title="Read file",
        activity_target_argument="file_path",
        result_formatter=format_read_file_result,
    )
    _register_builtin_tool(
        registry,
        name="Write",
        description="Create or overwrite a file in the current workspace. src-origin alias for filesystem.write.",
        parameters=SRC_ORIGIN_WRITE_SCHEMA,
        handler=lambda file_path, content: write_file(context, file_path, content),
        metadata={"risk": "medium", "writes_files": True, "alias_of": "filesystem.write", "src_origin_tool": "Write"},
        writes_state=True,
        concurrency_safe=False,
        max_result_size_chars=100000,
        path_parameters=("file_path",),
        activity_kind="edit",
        activity_title="Write file",
        activity_target_argument="file_path",
    )
    _register_builtin_tool(
        registry,
        name="Edit",
        description="Replace text in a file. src-origin alias for patch.apply single-file edit.",
        parameters=SRC_ORIGIN_EDIT_SCHEMA,
        handler=lambda file_path, old_string, new_string, replace_all=False: apply_src_origin_edit(
            context,
            file_path=file_path,
            old_string=old_string,
            new_string=new_string,
            replace_all=replace_all,
        ),
        metadata={
            "risk": "medium",
            "writes_files": True,
            "alias_of": "patch.apply",
            "src_origin_tool": "Edit",
        },
        writes_state=True,
        concurrency_safe=False,
        max_result_size_chars=100000,
        path_parameters=("file_path",),
        activity_kind="edit",
        activity_title="Edit file",
        activity_target_argument="file_path",
        result_formatter=format_src_origin_edit_result,
    )
    _register_builtin_tool(
        registry,
        name="MultiEdit",
        description="Apply multiple text replacements to one file. src-origin alias for patch.apply.",
        parameters=SRC_ORIGIN_MULTI_EDIT_SCHEMA,
        handler=lambda file_path, edits: apply_src_origin_multi_edit(
            context,
            file_path=file_path,
            edits=edits,
        ),
        metadata={
            "risk": "medium",
            "writes_files": True,
            "alias_of": "patch.apply",
            "src_origin_tool": "MultiEdit",
        },
        writes_state=True,
        concurrency_safe=False,
        max_result_size_chars=100000,
        path_parameters=("file_path",),
        activity_kind="edit",
        activity_title="Edit file",
        activity_target_argument="file_path",
        result_formatter=format_src_origin_multi_edit_result,
    )
    _register_builtin_tool(
        registry,
        name="LSP",
        description="Run a src-origin style language-server query for a workspace source file.",
        parameters=LSP_QUERY_SCHEMA,
        handler=lambda operation, filePath, line, character: lsp_query(
            context,
            operation=operation,
            filePath=filePath,
            line=line,
            character=character,
        ),
        metadata={"alias_of": "lsp.query", "src_origin_tool": "LSP"},
        read_only=True,
        path_parameters=("filePath",),
        activity_kind="workspace",
        activity_title="Query language server",
        activity_target_argument="filePath",
        result_formatter=format_lsp_result,
    )
    _register_builtin_tool(
        registry,
        name="Bash",
        description="Run a shell command. src-origin alias for shell.run.",
        parameters=RUN_COMMAND_SCHEMA,
        handler=lambda command,
        timeout_seconds=20.0,
        timeout=None,
        description="",
        run_in_background=False,
        dangerouslyDisableSandbox=False: run_command(
            context,
            command=command,
            timeout_seconds=timeout_seconds,
            timeout=timeout,
            description=description,
            run_in_background=run_in_background,
            dangerouslyDisableSandbox=dangerouslyDisableSandbox,
        ),
        metadata={"risk": "high", "requires_process": True, "alias_of": "shell.run", "src_origin_tool": "Bash"},
        concurrency_safe=False,
        interrupt_behavior="cancel",
        cancels_siblings_on_error=True,
        activity_kind="terminal",
        activity_title="Run shell command",
        activity_target_argument="command",
    )
    _register_builtin_tool(
        registry,
        name="Glob",
        description="Find workspace files by glob pattern. src-origin alias for search.glob.",
        parameters=GLOB_SCHEMA,
        handler=lambda pattern, path=".", max_results=100: glob(context, pattern, path=path, max_results=max_results),
        metadata={"alias_of": "search.glob", "src_origin_tool": "Glob"},
        read_only=True,
        path_parameters=("path",),
        activity_kind="workspace",
        activity_title="Find files",
        activity_target_argument="pattern",
        result_formatter=format_glob_result,
    )
    _register_builtin_tool(
        registry,
        name="Grep",
        description="Search workspace files by regex. src-origin alias for search.grep.",
        parameters=GREP_SCHEMA,
        handler=lambda pattern, path=".", glob="", max_results=1000, case_sensitive=True, output_mode="files_with_matches", head_limit=None, offset=0, **options: grep(
            context,
            pattern,
            path=path,
            glob=glob,
            max_results=max_results,
            case_sensitive=case_sensitive,
            output_mode=output_mode,
            head_limit=head_limit,
            offset=offset,
            **options,
        ),
        metadata={"alias_of": "search.grep", "src_origin_tool": "Grep"},
        read_only=True,
        path_parameters=("path",),
        activity_kind="workspace",
        activity_title="Search files",
        activity_target_argument="path",
        result_formatter=format_grep_result,
    )
    _register_builtin_tool(
        registry,
        name="TodoWrite",
        description="Update the structured todo list for the current session. src-origin alias for todo.write.",
        parameters=TODO_WRITE_SCHEMA,
        handler=lambda todos: todo_write(context, todos=todos),
        metadata={
            "risk": "low",
            "writes_state": True,
            "defer": True,
            "alias_of": "todo.write",
            "src_origin_tool": "TodoWrite",
        },
        writes_state=True,
        concurrency_safe=False,
        max_result_size_chars=100000,
        activity_kind="state",
        activity_title="Update todos",
        result_formatter=format_todo_write_result,
    )
    _register_builtin_tool(
        registry,
        name="NotebookEdit",
        description="Edit a specific Jupyter notebook cell. src-origin alias for notebook.edit.",
        parameters=NOTEBOOK_EDIT_SCHEMA,
        handler=lambda notebook_path,
        new_source,
        cell_id=None,
        cell_type=None,
        edit_mode="replace": notebook_edit(
            context,
            notebook_path=notebook_path,
            new_source=new_source,
            cell_id=cell_id,
            cell_type=cell_type,
            edit_mode=edit_mode,
        ),
        metadata={"risk": "medium", "writes_files": True, "alias_of": "notebook.edit", "src_origin_tool": "NotebookEdit"},
        writes_state=True,
        concurrency_safe=False,
        max_result_size_chars=100000,
        path_parameters=("notebook_path",),
        activity_kind="edit",
        activity_title="Edit notebook",
        activity_target_argument="notebook_path",
        result_formatter=format_notebook_edit_result,
    )
    _register_builtin_tool(
        registry,
        name="Sleep",
        description="Wait for a specified duration. src-origin alias for sleep.wait.",
        parameters=SLEEP_WAIT_SCHEMA,
        handler=lambda duration_seconds, reason="": sleep_wait(context, duration_seconds=duration_seconds, reason=reason),
        metadata={"risk": "low", "alias_of": "sleep.wait", "src_origin_tool": "Sleep"},
        read_only=True,
        interrupt_behavior="cancel",
        activity_kind="wait",
        activity_title="Wait",
        activity_target_argument="duration_seconds",
    )
    register_src_origin_discovery_aliases(registry, context, active_web_provider)
    register_src_origin_task_aliases(registry, context)
    register_src_origin_schedule_aliases(registry, context)
    register_src_origin_plan_aliases(registry, context)
    for alias_name, src_origin_tool in (("Agent", "Agent"), ("Task", "Task")):
        _register_builtin_tool(
            registry,
            name=alias_name,
            description="Delegate work to a child agent. src-origin alias for agent.run.",
            parameters=SRC_ORIGIN_AGENT_SCHEMA,
            handler=lambda description,
            prompt,
            subagent_type="",
            model="",
            run_in_background=False,
            name="",
            team_name="",
            mode="",
            isolation="",
            cwd="": _src_origin_agent(
                context,
                description=description,
                prompt=prompt,
                subagent_type=subagent_type,
                model=model,
                run_in_background=run_in_background,
                name=name,
                team_name=team_name,
                mode=mode,
                isolation=isolation,
                cwd=cwd,
            ),
            metadata={"risk": "high", "spawns_agent": True, "model_call": True, "alias_of": "agent.run", "src_origin_tool": src_origin_tool},
            writes_state=True,
            concurrency_safe=False,
            activity_kind="agent",
            activity_title="Run agent",
            activity_target_argument="description",
        )
    _register_builtin_tool(
        registry,
        name="SendMessage",
        description="Send a message to a teammate. src-origin alias for team.send.",
        parameters=SRC_ORIGIN_SEND_MESSAGE_SCHEMA,
        handler=lambda to, message, summary="", team_name="": _src_origin_send_message(
            context,
            to=to,
            message=message,
            summary=summary,
            team_name=team_name,
        ),
        metadata={"risk": "low", "writes_state": True, "alias_of": "team.send", "src_origin_tool": "SendMessage"},
        writes_state=True,
        activity_kind="state",
        activity_title="Send message",
        activity_target_argument="to",
    )
    _register_builtin_tool(
        registry,
        name="TeamCreate",
        description="Create a multi-agent team. src-origin alias for team.create.",
        parameters=SRC_ORIGIN_TEAM_CREATE_SCHEMA,
        handler=lambda team_name, description="", agent_type="": _src_origin_team_create(
            context,
            team_name=team_name,
            description=description,
            agent_type=agent_type,
        ),
        metadata={"risk": "low", "writes_state": True, "alias_of": "team.create", "src_origin_tool": "TeamCreate"},
        writes_state=True,
        activity_kind="state",
        activity_title="Create team",
        activity_target_argument="team_name",
    )
    _register_builtin_tool(
        registry,
        name="TeamDelete",
        description="Delete the active team. src-origin alias for team.delete.",
        parameters=SRC_ORIGIN_EMPTY_SCHEMA,
        handler=lambda: team_delete(context),
        metadata={"risk": "medium", "writes_state": True, "alias_of": "team.delete", "src_origin_tool": "TeamDelete"},
        writes_state=True,
        concurrency_safe=False,
        activity_kind="state",
        activity_title="Delete team",
    )
    _register_builtin_tool(
        registry,
        name="StructuredOutput",
        description="Return structured output in the requested format. src-origin alias for structured.output.",
        parameters=structured_schema,
        handler=structured_output,
        metadata={
            "risk": "low",
            "structured_output": True,
            "alias_of": "structured.output",
            "src_origin_tool": "StructuredOutput",
        },
        read_only=True,
        max_result_size_chars=100000,
        activity_kind="structured",
        activity_title="Structured output",
        result_formatter=format_structured_output_result,
    )
    _register_builtin_tool(
        registry,
        name="Skill",
        description="Invoke a slash-command skill. src-origin alias for skill.invoke.",
        parameters=SKILL_INVOKE_SCHEMA,
        handler=lambda skill, args="", mode="auto": skill_invoke(context, skill=skill, args=args, mode=mode),
        metadata={"risk": "high", "model_call": True, "alias_of": "skill.invoke", "src_origin_tool": "Skill"},
        concurrency_safe=False,
        max_result_size_chars=100000,
        activity_kind="skill",
        activity_title="Invoke skill",
        activity_target_argument="skill",
        result_formatter=format_skill_invoke_result,
    )
    _register_builtin_tool(
        registry,
        name="Config",
        description="Get or set configuration settings. src-origin alias for config.manage.",
        parameters=CONFIG_MANAGE_SCHEMA,
        handler=lambda setting, value=CONFIG_VALUE_UNSET: config_manage(context, setting=setting, value=value),
        metadata={"risk": "medium", "writes_state": True, "defer": True, "alias_of": "config.manage", "src_origin_tool": "Config"},
        writes_state=True,
        max_result_size_chars=100000,
        activity_kind="state",
        activity_title="Manage config",
        activity_target_argument="setting",
        result_formatter=format_config_result,
    )
    _register_builtin_tool(
        registry,
        name="AskUserQuestion",
        description="Ask the user multiple-choice questions. src-origin alias for user.ask.",
        parameters=ASK_USER_QUESTION_SCHEMA,
        handler=lambda questions, answers=None, annotations=None, metadata=None: ask_user_question(
            questions=questions,
            answers=answers,
            annotations=annotations,
            metadata=metadata,
        ),
        metadata={
            "risk": "low",
            "requires_user_interaction": True,
            "defer": True,
            "alias_of": "user.ask",
            "src_origin_tool": "AskUserQuestion",
        },
        read_only=True,
        max_result_size_chars=100000,
        activity_kind="state",
        activity_title="Ask user",
        activity_target_argument="questions",
        result_formatter=format_ask_user_question_result,
    )
    for alias_name in ("SendUserMessage", "Brief"):
        _register_builtin_tool(
            registry,
            name=alias_name,
            description="Send a message to the user. src-origin alias for user.message.",
            parameters=USER_MESSAGE_SCHEMA,
            handler=lambda message, attachments=None, status="normal": send_user_message(
                context,
                message=message,
                attachments=attachments,
                status=status,
            ),
            metadata={"risk": "low", "user_visible": True, "alias_of": "user.message", "src_origin_tool": alias_name},
            read_only=True,
            max_result_size_chars=100000,
            activity_kind="state",
            activity_title="Message user",
            activity_target_argument="message",
            result_formatter=format_user_message_result,
        )
    _register_builtin_tool(
        registry,
        name="EnterWorktree",
        description="Create or resume an isolated git worktree. src-origin alias for worktree.enter.",
        parameters=WORKTREE_ENTER_SCHEMA,
        handler=lambda name="", pr_number=None, prNumber=None: enter_worktree(context, name=name, pr_number=pr_number, pr_number_alias=prNumber),
        metadata={"risk": "medium", "writes_state": True, "alias_of": "worktree.enter", "src_origin_tool": "EnterWorktree"},
        writes_state=True,
        concurrency_safe=False,
        activity_kind="state",
        activity_title="Enter worktree",
        activity_target_argument="name",
        result_formatter=format_worktree_result,
    )
    _register_builtin_tool(
        registry,
        name="ExitWorktree",
        description="Exit the active git worktree. src-origin alias for worktree.exit.",
        parameters=WORKTREE_EXIT_SCHEMA,
        handler=lambda action, discard_changes=False: exit_worktree(
            context,
            action=action,
            discard_changes=discard_changes,
        ),
        metadata={"risk": "medium", "writes_state": True, "alias_of": "worktree.exit", "src_origin_tool": "ExitWorktree"},
        destructive=True,
        writes_state=True,
        concurrency_safe=False,
        activity_kind="state",
        activity_title="Exit worktree",
        activity_target_argument="action",
        result_formatter=format_worktree_result,
    )
