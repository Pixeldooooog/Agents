from __future__ import annotations

import json
from typing import Any

from agents.kernel.capabilities.tools.builtin.agents import AGENT_RUN_SCHEMA, agent_run
from agents.kernel.capabilities.tools.builtin.agent_profiles import (
    AGENT_PROFILES_SCHEMA,
    AGENT_SAVE_PROFILE_SCHEMA,
    agent_profiles,
    agent_save_profile,
)
from agents.kernel.capabilities.tools.builtin.browser import BROWSER_DOWNLOAD_SCHEMA, BROWSER_OPEN_SCHEMA, browser_download, browser_open
from agents.kernel.capabilities.tools.builtin.commands import (
    COMMAND_DELETE_SCHEMA,
    COMMAND_DISCOVER_SCHEMA,
    COMMAND_READ_SCHEMA,
    COMMAND_RENDER_SCHEMA,
    COMMAND_SAVE_SCHEMA,
    command_delete,
    command_discover,
    command_read,
    command_render,
    command_save,
)
from agents.kernel.capabilities.tools.builtin.config import (
    CONFIG_MANAGE_SCHEMA,
    CONFIG_VALUE_UNSET,
    config_manage,
    format_config_result,
)
from agents.kernel.capabilities.tools.builtin.filesystem import (
    DELETE_PATH_SCHEMA,
    LIST_DIR_SCHEMA,
    MOVE_PATH_SCHEMA,
    READ_FILE_SCHEMA,
    WRITE_FILE_SCHEMA,
    delete_path,
    format_read_file_result,
    list_dir,
    move_path,
    read_file,
    write_file,
)
from agents.kernel.capabilities.tools.builtin.extensions import (
    EXTENSION_NAME_SCHEMA,
    SKILL_INSTALL_SCHEMA,
    SKILL_UNINSTALL_SCHEMA,
    plugin_disable,
    plugin_enable,
    skill_install,
    skill_disable,
    skill_uninstall,
    skill_use,
)
from agents.kernel.capabilities.tools.builtin.git import (
    GIT_ADD_SCHEMA,
    GIT_COMMIT_SCHEMA,
    GIT_DIFF_SCHEMA,
    GIT_LOG_SCHEMA,
    GIT_SHOW_SCHEMA,
    GIT_STATUS_SCHEMA,
    git_add,
    git_commit,
    git_diff,
    git_log,
    git_show,
    git_status,
)
from agents.kernel.capabilities.tools.builtin.hooks import (
    HOOK_ADD_SCHEMA,
    HOOK_DELETE_SCHEMA,
    HOOK_EVENTS_SCHEMA,
    HOOK_LIST_SCHEMA,
    hook_add,
    hook_delete,
    hook_events,
    hook_list,
)
from agents.kernel.capabilities.tools.builtin.lsp import LSP_QUERY_SCHEMA, format_lsp_result, lsp_query
from agents.kernel.capabilities.tools.builtin.meta import SKILL_DISCOVER_SCHEMA, TOOL_SEARCH_SCHEMA, skill_discover, tool_search
from agents.kernel.capabilities.tools.builtin.memory import (
    MEMORY_ADD_SCHEMA,
    MEMORY_EDIT_SCHEMA,
    MEMORY_FORGET_SCHEMA,
    MEMORY_LIST_SCHEMA,
    memory_add,
    memory_edit,
    memory_forget,
    memory_list,
)
from agents.kernel.capabilities.tools.builtin.notebook import (
    NOTEBOOK_EDIT_SCHEMA,
    format_notebook_edit_result,
    notebook_edit,
)
from agents.kernel.capabilities.tools.builtin.mcp_resources import (
    MCP_READ_RESOURCE_SCHEMA,
    MCP_RESOURCES_SCHEMA,
    mcp_read_resource,
    mcp_resources,
)
from agents.kernel.capabilities.tools.builtin.mcp_prompts import (
    MCP_GET_PROMPT_SCHEMA,
    MCP_PROMPTS_SCHEMA,
    mcp_get_prompt,
    mcp_prompts,
)
from agents.kernel.capabilities.tools.builtin.mcp_management import (
    MCP_CLEAR_SCHEMA,
    MCP_CONFIGURE_SCHEMA,
    MCP_RELOAD_SCHEMA,
    MCP_SERVER_NAME_SCHEMA,
    MCP_SERVERS_SCHEMA,
    mcp_clear,
    mcp_configure,
    mcp_disable,
    mcp_enable,
    mcp_remove,
    mcp_reconnect,
    mcp_reload,
    mcp_servers,
)
from agents.kernel.capabilities.tools.builtin.mcp_ide import (
    IDE_DISCOVERY_SCHEMA,
    IDE_EXTENSION_SCHEMA,
    MCP_CONFIGURE_IDE_SCHEMA,
    mcp_configure_ide,
    mcp_detect_ide,
    mcp_ide_extension_status,
    mcp_install_ide_extension,
)
from agents.kernel.capabilities.tools.builtin.patch import (
    PATCH_APPLY_SCHEMA,
    apply_patch,
    apply_src_origin_edit,
    apply_src_origin_multi_edit,
    format_src_origin_edit_result,
    format_src_origin_multi_edit_result,
)
from agents.kernel.capabilities.tools.builtin.planning import (
    PLAN_ENTER_SCHEMA,
    PLAN_EXIT_SCHEMA,
    PLAN_STATUS_SCHEMA,
    TODO_READ_SCHEMA,
    TODO_WRITE_SCHEMA,
    format_todo_write_result,
    plan_enter,
    plan_exit,
    plan_status,
    todo_read,
    todo_write,
)
from agents.kernel.capabilities.tools.builtin.permissions import (
    PERMISSION_REMOVE_RULE_SCHEMA,
    PERMISSION_RULE_SCHEMA,
    PERMISSION_EXPLAIN_SCHEMA,
    PERMISSION_SOURCES_SCHEMA,
    PERMISSION_STATUS_SCHEMA,
    permission_add_rule,
    permission_explain,
    permission_remove_rule,
    permission_sources,
    permission_status,
)
from agents.kernel.capabilities.tools.builtin.plugins import (
    PLUGIN_DISCOVER_SCHEMA,
    PLUGIN_INSTALL_SCHEMA,
    PLUGIN_UNINSTALL_SCHEMA,
    plugin_discover,
    plugin_install,
    plugin_uninstall,
)
from agents.kernel.capabilities.tools.builtin.prompts import (
    PROMPT_DELETE_SCHEMA,
    PROMPT_READ_SCHEMA,
    PROMPT_RENDER_SCHEMA,
    PROMPT_SAVE_SCHEMA,
    PROMPT_TEMPLATES_SCHEMA,
    prompt_delete,
    prompt_read,
    prompt_render,
    prompt_save,
    prompt_templates,
)
from agents.kernel.capabilities.tools.builtin.search import GLOB_SCHEMA, GREP_SCHEMA, format_glob_result, format_grep_result, glob, grep
from agents.kernel.capabilities.tools.builtin.schedules import (
    SCHEDULE_CREATE_SCHEMA,
    SCHEDULE_DELETE_SCHEMA,
    SCHEDULE_LIST_SCHEMA,
    SCHEDULE_RUN_SCHEMA,
    schedule_create,
    schedule_delete,
    schedule_list,
    schedule_run,
)
from agents.kernel.capabilities.tools.builtin.session_context import (
    CONTEXT_COMPACT_SCHEMA,
    CONTEXT_MESSAGES_SCHEMA,
    CONTEXT_REWIND_SCHEMA,
    CONTEXT_TRACE_SCHEMA,
    SESSION_EXPORT_SCHEMA,
    SESSION_SUMMARY_SCHEMA,
    SESSION_STATUS_SCHEMA,
    context_compact,
    context_messages,
    context_rewind,
    context_trace,
    session_export,
    session_summary,
    session_status,
)
from agents.kernel.capabilities.tools.builtin.sleep import SLEEP_WAIT_SCHEMA, sleep_wait
from agents.kernel.capabilities.tools.builtin.shell import (
    RUN_COMMAND_SCHEMA,
    SHELL_BACKGROUNDS_SCHEMA,
    SHELL_KILL_SCHEMA,
    SHELL_OUTPUT_SCHEMA,
    run_command,
    shell_backgrounds,
    shell_kill,
    shell_output,
)
from agents.kernel.capabilities.tools.builtin.skill_invocation import (
    SKILL_INVOKE_SCHEMA,
    format_skill_invoke_result,
    skill_invoke,
)
from agents.kernel.capabilities.tools.builtin.structured import (
    format_structured_output_result,
    structured_output,
    structured_output_schema_from_metadata,
)
from agents.kernel.capabilities.tools.builtin.tasks import (
    TASK_CREATE_SCHEMA,
    TASK_BACKGROUND_SCHEMA,
    TASK_BACKGROUNDS_SCHEMA,
    TASK_GET_SCHEMA,
    TASK_LIST_SCHEMA,
    TASK_OUTPUT_SCHEMA,
    TASK_RUN_SCHEMA,
    TASK_STOP_SCHEMA,
    TASK_UPDATE_SCHEMA,
    task_create,
    task_background,
    task_backgrounds,
    task_get,
    task_list,
    task_output,
    task_run,
    task_stop,
    task_update,
)
from agents.kernel.capabilities.tools.builtin.teams import (
    TEAM_CREATE_SCHEMA,
    TEAM_DELETE_SCHEMA,
    TEAM_INBOX_SCHEMA,
    TEAM_MEMBERS_SCHEMA,
    TEAM_RUN_MEMBER_SCHEMA,
    TEAM_SEND_SCHEMA,
    team_create,
    team_delete,
    team_inbox,
    team_members,
    team_run_member,
    team_send,
)
from agents.kernel.capabilities.tools.builtin.tests import TEST_DISCOVER_SCHEMA, TEST_RUN_SCHEMA, discover_tests, run_tests
from agents.kernel.capabilities.tools.builtin.user_interaction import (
    ASK_USER_QUESTION_SCHEMA,
    USER_MESSAGE_SCHEMA,
    ask_user_question,
    format_ask_user_question_result,
    format_user_message_result,
    send_user_message,
)
from agents.kernel.capabilities.tools.builtin.web import (
    WEB_EXTRACT_SCHEMA,
    WEB_MAP_SCHEMA,
    WEB_SEARCH_SCHEMA,
    web_extract,
    web_map,
    web_search,
)
from agents.kernel.capabilities.tools.builtin.worktree import (
    WORKTREE_ENTER_SCHEMA,
    WORKTREE_EXIT_SCHEMA,
    enter_worktree,
    exit_worktree,
    format_worktree_result,
)
from agents.kernel.capabilities.tools.builtin.workflows import (
    WORKFLOW_DELETE_SCHEMA,
    WORKFLOW_READ_SCHEMA,
    WORKFLOW_RUN_SCHEMA,
    WORKFLOW_RUN_SAVED_SCHEMA,
    WORKFLOW_SAVE_SCHEMA,
    WORKFLOW_TEMPLATES_SCHEMA,
    WORKFLOW_VALIDATE_SCHEMA,
    workflow_delete,
    workflow_read,
    workflow_run,
    workflow_run_saved,
    workflow_save,
    workflow_templates,
    workflow_validate,
)
from agents.kernel.capabilities.sandbox.text import DEFAULT_TEXT_READ_MAX_BYTES
from agents.kernel.capabilities.tools.context import ToolRuntimeContext
from agents.kernel.capabilities.tools.registry import ToolActivity, ToolDefinition, ToolRegistry
from agents.kernel.capabilities.web import NullWebSearchProvider, WebSearchProvider


BUILTIN_TOOL_NAMES = [
    "filesystem.read",
    "filesystem.list",
    "filesystem.write",
    "filesystem.delete",
    "filesystem.move",
    "notebook.edit",
    "lsp.query",
    "patch.apply",
    "search.grep",
    "search.glob",
    "structured.output",
    "config.manage",
    "user.ask",
    "user.message",
    "worktree.enter",
    "worktree.exit",
    "Read",
    "Write",
    "Edit",
    "MultiEdit",
    "Bash",
    "Glob",
    "Grep",
    "TodoWrite",
    "NotebookEdit",
    "LSP",
    "Sleep",
    "WebSearch",
    "WebFetch",
    "ListMcpResourcesTool",
    "ReadMcpResourceTool",
    "TaskOutput",
    "AgentOutputTool",
    "BashOutputTool",
    "TaskStop",
    "KillShell",
    "TaskCreate",
    "TaskList",
    "TaskGet",
    "TaskUpdate",
    "CronCreate",
    "CronList",
    "CronDelete",
    "ToolSearch",
    "EnterPlanMode",
    "ExitPlanMode",
    "Agent",
    "Task",
    "SendMessage",
    "TeamCreate",
    "TeamDelete",
    "StructuredOutput",
    "Skill",
    "Config",
    "AskUserQuestion",
    "SendUserMessage",
    "Brief",
    "EnterWorktree",
    "ExitWorktree",
    "command.discover",
    "command.render",
    "command.read",
    "command.save",
    "command.delete",
    "tool.search",
    "skill.discover",
    "skill.invoke",
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
    "web.search",
    "web.extract",
    "web.map",
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
    "shell.run",
    "shell.output",
    "shell.backgrounds",
    "shell.kill",
    "sleep.wait",
    "browser.open",
    "browser.download",
    "agent.profiles",
    "agent.save_profile",
    "team.create",
    "team.delete",
    "team.members",
    "team.send",
    "team.inbox",
    "team.run_member",
    "agent.run",
]


def register_builtin_tools(
    registry: ToolRegistry,
    context: ToolRuntimeContext,
    web_provider: WebSearchProvider | None = None,
) -> list[str]:
    context.runtime_event_sink = registry.emit_runtime_event
    context.runtime_event_active = registry.has_runtime_event_sink
    active_web_provider = web_provider or NullWebSearchProvider()
    _register_filesystem(registry, context)
    _register_notebooks(registry, context)
    _register_lsp(registry, context)
    _register_patch_and_search(registry, context)
    _register_structured_output(registry, context)
    _register_skill_invocation(registry, context)
    _register_config(registry, context)
    _register_user_interaction(registry, context)
    _register_worktrees(registry, context)
    _register_src_origin_aliases(registry, context, active_web_provider)
    _register_commands(registry, context)
    _register_meta(registry, context)
    _register_plugins(registry, context)
    _register_extension_management(registry, context)
    _register_mcp_management(registry, context)
    _register_mcp_prompts(registry, context)
    _register_mcp_resources(registry, context)
    _register_prompt_templates(registry, context)
    _register_session_context(registry, context)
    _register_permissions(registry, context)
    _register_hooks(registry, context)
    _register_memory(registry, context)
    _register_web(registry, context, active_web_provider)
    _register_git(registry, context)
    _register_tests(registry, context)
    _register_planning(registry, context)
    _register_workflows(registry, context)
    _register_tasks(registry, context)
    _register_schedules(registry, context)
    _register_shell(registry, context)
    _register_sleep(registry, context)
    _register_browser(registry, context)
    _register_agent_profiles(registry, context)
    _register_teams(registry, context)
    _register_agents(registry, context)
    return list(BUILTIN_TOOL_NAMES)


def _register_builtin_tool(
    registry: ToolRegistry,
    *,
    name: str,
    description: str,
    parameters: dict,
    handler,
    metadata: dict | None = None,
    read_only: bool = False,
    destructive: bool = False,
    writes_state: bool = False,
    concurrency_safe: bool = True,
    interrupt_behavior: str = "block",
    cancels_siblings_on_error: bool = False,
    max_result_size_chars: int | None = None,
    path_parameters: tuple[str, ...] = (),
    activity_kind: str = "generic",
    activity_title: str = "",
    activity_target_argument: str = "",
    activity_summary: str = "",
    result_formatter=None,
) -> None:
    registry.register_definition(
        ToolDefinition(
            name=name,
            description=description,
            parameters=parameters,
            handler=handler,
            metadata=dict(metadata or {}),
            read_only=read_only,
            destructive=destructive,
            writes_state=writes_state,
            concurrency_safe=concurrency_safe,
            interrupt_behavior=interrupt_behavior,
            cancels_siblings_on_error=cancels_siblings_on_error,
            max_result_size_chars=max_result_size_chars,
            path_parameters=path_parameters,
            activity=ToolActivity(
                kind=activity_kind,
                title=activity_title,
                target_argument=activity_target_argument,
                summary=activity_summary,
            ),
            result_formatter=result_formatter,
        )
    )


def _register_filesystem(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    _register_builtin_tool(
        registry,
        name="filesystem.read",
        description="Read a text file from the current workspace, optionally by line offset and limit.",
        parameters=READ_FILE_SCHEMA,
        handler=lambda path, max_bytes=None, offset=1, limit=None, pages=None: read_file(
            context,
            path,
            max_bytes=max_bytes,
            offset=offset,
            limit=limit,
            pages=pages,
        ),
        read_only=True,
        path_parameters=("path",),
        activity_kind="workspace",
        activity_title="Read file",
        activity_target_argument="path",
        result_formatter=format_read_file_result,
    )
    _register_builtin_tool(
        registry,
        name="filesystem.list",
        description="List files and directories inside the current workspace.",
        parameters=LIST_DIR_SCHEMA,
        handler=lambda path=".": list_dir(context, path=path),
        read_only=True,
        path_parameters=("path",),
        activity_kind="workspace",
        activity_title="List directory",
        activity_target_argument="path",
    )
    _register_builtin_tool(
        registry,
        name="filesystem.write",
        description="Write a UTF-8 text file inside the current workspace when the sandbox allows writes.",
        parameters=WRITE_FILE_SCHEMA,
        handler=lambda path, content: write_file(context, path, content),
        metadata={"risk": "medium", "writes_files": True},
        writes_state=True,
        concurrency_safe=False,
        path_parameters=("path",),
        activity_kind="edit",
        activity_title="Write file",
        activity_target_argument="path",
    )
    _register_builtin_tool(
        registry,
        name="filesystem.delete",
        description="Delete a file or directory inside the current workspace.",
        parameters=DELETE_PATH_SCHEMA,
        handler=lambda path, recursive=False: delete_path(context, path, recursive=recursive),
        metadata={"risk": "medium", "writes_files": True},
        destructive=True,
        writes_state=True,
        concurrency_safe=False,
        path_parameters=("path",),
        activity_kind="edit",
        activity_title="Delete path",
        activity_target_argument="path",
    )
    _register_builtin_tool(
        registry,
        name="filesystem.move",
        description="Move or rename a file or directory inside the current workspace.",
        parameters=MOVE_PATH_SCHEMA,
        handler=lambda source_path, destination_path, overwrite=False: move_path(
            context,
            source_path=source_path,
            destination_path=destination_path,
            overwrite=overwrite,
        ),
        metadata={"risk": "medium", "writes_files": True},
        writes_state=True,
        concurrency_safe=False,
        path_parameters=("source_path", "destination_path"),
        activity_kind="edit",
        activity_title="Move path",
        activity_target_argument="source_path",
    )


def _register_notebooks(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    _register_builtin_tool(
        registry,
        name="notebook.edit",
        description="Edit a specific cell in a Jupyter notebook with read-before-write stale-file safety.",
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
        metadata={"risk": "medium", "writes_files": True, "src_origin_tool": "NotebookEdit"},
        writes_state=True,
        concurrency_safe=False,
        max_result_size_chars=100000,
        path_parameters=("notebook_path",),
        activity_kind="edit",
        activity_title="Edit notebook",
        activity_target_argument="notebook_path",
        result_formatter=format_notebook_edit_result,
    )


def _register_lsp(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    _register_builtin_tool(
        registry,
        name="lsp.query",
        description="Run a read-only language-server query for a source file in the current workspace.",
        parameters=LSP_QUERY_SCHEMA,
        handler=lambda operation, filePath, line, character: lsp_query(
            context,
            operation=operation,
            filePath=filePath,
            line=line,
            character=character,
        ),
        read_only=True,
        path_parameters=("filePath",),
        activity_kind="workspace",
        activity_title="Query language server",
        activity_target_argument="filePath",
        result_formatter=format_lsp_result,
    )


def _register_patch_and_search(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    _register_builtin_tool(
        registry,
        name="patch.apply",
        description="Apply exact text edits or create text files inside the current workspace.",
        parameters=PATCH_APPLY_SCHEMA,
        handler=lambda edits=None, creates=None, dry_run=False: apply_patch(
            context,
            edits=edits,
            creates=creates,
            dry_run=dry_run,
        ),
        metadata={"risk": "medium", "writes_files": True},
        writes_state=True,
        concurrency_safe=False,
        activity_kind="edit",
        activity_title="Apply patch",
    )
    _register_builtin_tool(
        registry,
        name="search.grep",
        description="Search text files inside the current workspace with a regular expression.",
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
        read_only=True,
        path_parameters=("path",),
        activity_kind="workspace",
        activity_title="Search files",
        activity_target_argument="path",
        result_formatter=format_grep_result,
    )
    _register_builtin_tool(
        registry,
        name="search.glob",
        description="Find workspace files by glob pattern.",
        parameters=GLOB_SCHEMA,
        handler=lambda pattern, path=".", max_results=100: glob(
            context,
            pattern,
            path=path,
            max_results=max_results,
        ),
        read_only=True,
        path_parameters=("path",),
        activity_kind="workspace",
        activity_title="Find files",
        activity_target_argument="pattern",
        result_formatter=format_glob_result,
    )


def _register_structured_output(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    schema = structured_output_schema_from_metadata(_agent_spec_metadata(context))
    _register_builtin_tool(
        registry,
        name="structured.output",
        description="Return the final answer as structured data for SDK and non-interactive callers.",
        parameters=schema,
        handler=structured_output,
        metadata={"risk": "low", "structured_output": True},
        read_only=True,
        max_result_size_chars=100000,
        activity_kind="structured",
        activity_title="Structured output",
        result_formatter=format_structured_output_result,
    )


def _register_skill_invocation(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    _register_builtin_tool(
        registry,
        name="skill.invoke",
        description="Invoke a local skill by expanding its prompt or executing it in a forked child agent.",
        parameters=SKILL_INVOKE_SCHEMA,
        handler=lambda skill, args="", mode="auto": skill_invoke(context, skill=skill, args=args, mode=mode),
        metadata={"risk": "high", "model_call": True},
        writes_state=False,
        concurrency_safe=False,
        max_result_size_chars=100000,
        activity_kind="skill",
        activity_title="Invoke skill",
        activity_target_argument="skill",
        result_formatter=format_skill_invoke_result,
    )


def _register_config(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    _register_builtin_tool(
        registry,
        name="config.manage",
        description="Get or set session configuration settings such as theme, model, and permissions.defaultMode.",
        parameters=CONFIG_MANAGE_SCHEMA,
        handler=lambda setting, value=CONFIG_VALUE_UNSET: config_manage(context, setting=setting, value=value),
        metadata={"risk": "medium", "writes_state": True, "defer": True},
        writes_state=True,
        max_result_size_chars=100000,
        activity_kind="state",
        activity_title="Manage config",
        activity_target_argument="setting",
        result_formatter=format_config_result,
    )


def _register_user_interaction(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    _register_builtin_tool(
        registry,
        name="user.message",
        description="Send a message to the user with optional workspace file attachments.",
        parameters=USER_MESSAGE_SCHEMA,
        handler=lambda message, attachments=None, status="normal": send_user_message(
            context,
            message=message,
            attachments=attachments,
            status=status,
        ),
        metadata={"risk": "low", "user_visible": True},
        read_only=True,
        max_result_size_chars=100000,
        activity_kind="state",
        activity_title="Message user",
        activity_target_argument="message",
        result_formatter=format_user_message_result,
    )
    _register_builtin_tool(
        registry,
        name="user.ask",
        description="Ask the user one or more multiple-choice questions and return their answers.",
        parameters=ASK_USER_QUESTION_SCHEMA,
        handler=lambda questions, answers=None, annotations=None, metadata=None: ask_user_question(
            questions=questions,
            answers=answers,
            annotations=annotations,
            metadata=metadata,
        ),
        metadata={"risk": "low", "requires_user_interaction": True, "defer": True},
        read_only=True,
        max_result_size_chars=100000,
        activity_kind="state",
        activity_title="Ask user",
        activity_target_argument="questions",
        result_formatter=format_ask_user_question_result,
    )


def _register_worktrees(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    _register_builtin_tool(
        registry,
        name="worktree.enter",
        description="Create or resume an isolated git worktree and switch the session workspace to it.",
        parameters=WORKTREE_ENTER_SCHEMA,
        handler=lambda name="", pr_number=None, prNumber=None: enter_worktree(context, name=name, pr_number=pr_number, pr_number_alias=prNumber),
        metadata={"risk": "medium", "writes_state": True},
        writes_state=True,
        concurrency_safe=False,
        activity_kind="state",
        activity_title="Enter worktree",
        activity_target_argument="name",
        result_formatter=format_worktree_result,
    )
    _register_builtin_tool(
        registry,
        name="worktree.exit",
        description="Exit the active git worktree, either preserving it or removing it after safety checks.",
        parameters=WORKTREE_EXIT_SCHEMA,
        handler=lambda action, discard_changes=False: exit_worktree(
            context,
            action=action,
            discard_changes=discard_changes,
        ),
        metadata={"risk": "medium", "writes_state": True},
        destructive=True,
        writes_state=True,
        concurrency_safe=False,
        activity_kind="state",
        activity_title="Exit worktree",
        activity_target_argument="action",
        result_formatter=format_worktree_result,
    )


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

SRC_ORIGIN_WEB_SEARCH_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "The search query to use."},
        "allowed_domains": {"type": "array", "items": {"type": "string"}},
        "blocked_domains": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["query"],
}

SRC_ORIGIN_WEB_FETCH_SCHEMA = {
    "type": "object",
    "properties": {
        "url": {"type": "string", "description": "The URL to fetch content from."},
        "prompt": {"type": "string", "description": "The prompt to run on the fetched content."},
    },
    "required": ["url", "prompt"],
}

SRC_ORIGIN_TASK_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "task_id": {"type": "string", "description": "Background task id."},
        "block": {"type": "boolean", "description": "Whether to wait for completion."},
        "timeout": {"type": "number", "minimum": 0, "maximum": 600000, "description": "Max wait time in milliseconds."},
        "max_bytes": {"type": "integer", "minimum": 1, "maximum": 200000},
    },
    "required": ["task_id"],
}

SRC_ORIGIN_TASK_STOP_SCHEMA = {
    "type": "object",
    "properties": {
        "task_id": {"type": "string", "description": "The ID of the background task to stop."},
        "shell_id": {"type": "string", "description": "Deprecated shell task id alias."},
    },
}

SRC_ORIGIN_TASK_CREATE_SCHEMA = {
    "type": "object",
    "properties": {
        "subject": {"type": "string", "description": "A brief title for the task."},
        "description": {"type": "string", "description": "What needs to be done."},
        "activeForm": {"type": "string", "description": "Present-continuous status label."},
        "metadata": {"type": "object", "additionalProperties": True},
    },
    "required": ["subject", "description"],
}

SRC_ORIGIN_TASK_GET_SCHEMA = {
    "type": "object",
    "properties": {
        "taskId": {"type": "string", "description": "The task ID to get."},
    },
    "required": ["taskId"],
}

SRC_ORIGIN_TASK_UPDATE_SCHEMA = {
    "type": "object",
    "properties": {
        "taskId": {"type": "string", "description": "The ID of the task to update."},
        "subject": {"type": "string", "description": "New subject for the task."},
        "description": {"type": "string", "description": "New description for the task."},
        "activeForm": {"type": "string", "description": "Present-continuous status label."},
        "status": {
            "type": "string",
            "enum": ["pending", "running", "completed", "failed", "killed", "deleted"],
            "description": "New src-origin task status.",
        },
        "owner": {"type": "string"},
        "addBlocks": {"type": "array", "items": {"type": "string"}},
        "addBlockedBy": {"type": "array", "items": {"type": "string"}},
        "metadata": {"type": "object", "additionalProperties": True},
    },
    "required": ["taskId"],
}

SRC_ORIGIN_CRON_CREATE_SCHEMA = {
    "type": "object",
    "properties": {
        "cron": {"type": "string", "description": "Standard 5-field cron expression."},
        "prompt": {"type": "string", "description": "The prompt to enqueue at each fire time."},
        "recurring": {"type": "boolean"},
        "durable": {"type": "boolean"},
    },
    "required": ["cron", "prompt"],
}

SRC_ORIGIN_CRON_DELETE_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "string", "description": "Job ID returned by CronCreate."},
    },
    "required": ["id"],
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


def _src_origin_task_status(status: str) -> str:
    mapping = {
        "pending": "created",
        "running": "running",
        "completed": "finished",
        "failed": "error",
        "killed": "canceled",
        "deleted": "canceled",
    }
    value = str(status or "").strip()
    return mapping.get(value, value)


def _src_origin_prompt_title(prompt: str) -> str:
    text = str(prompt or "").strip()
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    return first_line[:80] or "Scheduled prompt"


async def _src_origin_task_create(
    context: ToolRuntimeContext,
    *,
    subject: str,
    description: str,
    activeForm: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict:
    return await task_create(
        context,
        title=subject,
        input=description,
        metadata=_src_origin_metadata(metadata, activeForm=activeForm),
    )


async def _src_origin_task_update(
    context: ToolRuntimeContext,
    *,
    taskId: str,
    subject: str = "",
    description: str = "",
    activeForm: str = "",
    status: str = "",
    owner: str = "",
    addBlocks: list[str] | None = None,
    addBlockedBy: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict:
    return await task_update(
        context,
        task_id=taskId,
        title=subject,
        input=description,
        status=_src_origin_task_status(status),
        metadata=_src_origin_metadata(
            metadata,
            activeForm=activeForm,
            owner=owner,
            blocks=",".join(addBlocks or []),
            blockedBy=",".join(addBlockedBy or []),
        ),
    )


async def _src_origin_cron_create(
    context: ToolRuntimeContext,
    *,
    cron: str,
    prompt: str,
    recurring: bool = True,
    durable: bool = False,
) -> dict:
    return await schedule_create(
        context,
        title=_src_origin_prompt_title(prompt),
        input=prompt,
        schedule=cron,
        enabled=True,
        metadata={"recurring": str(bool(recurring)).lower(), "durable": str(bool(durable)).lower()},
    )


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


async def _src_origin_web_search(
    context: ToolRuntimeContext,
    provider: WebSearchProvider,
    *,
    query: str,
    allowed_domains: list[str] | None = None,
    blocked_domains: list[str] | None = None,
) -> dict:
    if allowed_domains and blocked_domains:
        raise ValueError("Cannot specify both allowed_domains and blocked_domains")
    return await web_search(
        context,
        provider,
        query=query,
        include_domains=allowed_domains,
        exclude_domains=blocked_domains,
    )


async def _src_origin_web_fetch(
    context: ToolRuntimeContext,
    provider: WebSearchProvider,
    *,
    url: str,
    prompt: str,
) -> dict:
    return await web_extract(
        context,
        provider,
        urls=[url],
        query=prompt,
        extract_depth="basic",
        format="markdown",
    )


async def _src_origin_task_output(
    context: ToolRuntimeContext,
    *,
    task_id: str,
    block: bool = True,
    timeout: float = 30000,
    max_bytes: int = 20000,
) -> dict:
    task_id = str(task_id or "")
    if task_id.startswith("shell_"):
        result = await shell_output(
            context,
            task_id=task_id,
            block=block,
            timeout_seconds=float(timeout or 0) / 1000.0,
            max_bytes=max_bytes,
        )
        return _src_origin_shell_output_payload(result)
    result = await task_output(context, task_id=task_id, max_bytes=max_bytes)
    return _src_origin_tracked_task_output_payload(result)


async def _src_origin_task_stop(
    context: ToolRuntimeContext,
    *,
    task_id: str = "",
    shell_id: str = "",
) -> dict:
    resolved_task_id = str(task_id or shell_id or "")
    if not resolved_task_id:
        raise ValueError("Missing required parameter: task_id")
    if resolved_task_id.startswith("shell_"):
        result = await shell_kill(context, task_id=resolved_task_id)
        task = result.get("task") if isinstance(result.get("task"), dict) else {}
        if not result.get("killed"):
            raise ValueError("Task %s is not running (status: %s)" % (resolved_task_id, task.get("status") or "unknown"))
        return _src_origin_task_stop_payload(task, task_type="local_bash")
    result = await task_stop(context, task_id=resolved_task_id)
    task = result.get("task") if isinstance(result.get("task"), dict) else {}
    return _src_origin_task_stop_payload(task, task_type=_src_origin_tracked_task_type(task))


def _src_origin_shell_output_payload(result: dict) -> dict:
    task = result.get("task") if isinstance(result.get("task"), dict) else {}
    output = str(result.get("output") or "")
    payload = {
        "task_id": str(task.get("task_id") or ""),
        "task_type": "local_bash",
        "status": str(task.get("status") or ""),
        "description": str(task.get("command") or ""),
        "output": output,
    }
    if task.get("exit_code") is not None:
        payload["exitCode"] = task.get("exit_code")
    return {"retrieval_status": str(result.get("retrieval_status") or "success"), "task": payload}


def _src_origin_tracked_task_output_payload(result: dict) -> dict:
    task = result.get("task") if isinstance(result.get("task"), dict) else {}
    output = str(result.get("output") or "")
    return {
        "retrieval_status": "success",
        "task": {
            "task_id": str(task.get("task_id") or ""),
            "task_type": _src_origin_tracked_task_type(task),
            "status": str(task.get("status") or ""),
            "description": str(task.get("title") or task.get("input") or ""),
            "prompt": str(task.get("input") or ""),
            "output": output,
        },
    }


def _src_origin_task_stop_payload(task: dict, *, task_type: str) -> dict:
    task_id = str(task.get("task_id") or "")
    command = str(task.get("command") or task.get("title") or task.get("input") or "")
    return {
        "message": "Successfully stopped task: %s (%s)" % (task_id, command),
        "task_id": task_id,
        "task_type": task_type,
        "command": command,
    }


def _src_origin_tracked_task_type(task: dict) -> str:
    metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
    return str(metadata.get("task_type") or metadata.get("type") or metadata.get("source") or "task")


def _register_src_origin_aliases(
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
    _register_builtin_tool(
        registry,
        name="WebSearch",
        description="Search the web for current information. src-origin alias for web.search.",
        parameters=SRC_ORIGIN_WEB_SEARCH_SCHEMA,
        handler=lambda query, allowed_domains=None, blocked_domains=None: _src_origin_web_search(
            context,
            active_web_provider,
            query=query,
            allowed_domains=allowed_domains,
            blocked_domains=blocked_domains,
        ),
        metadata={
            "risk": "medium",
            "requires_network": True,
            "external_disclosure": True,
            "provider": getattr(active_web_provider, "name", "none"),
            "alias_of": "web.search",
            "src_origin_tool": "WebSearch",
        },
        read_only=True,
        activity_kind="web",
        activity_title="Search web",
        activity_target_argument="query",
    )
    _register_builtin_tool(
        registry,
        name="WebFetch",
        description="Fetch and extract content from a URL. src-origin alias for web.extract.",
        parameters=SRC_ORIGIN_WEB_FETCH_SCHEMA,
        handler=lambda url, prompt: _src_origin_web_fetch(
            context,
            active_web_provider,
            url=url,
            prompt=prompt,
        ),
        metadata={
            "risk": "medium",
            "requires_network": True,
            "external_disclosure": True,
            "provider": getattr(active_web_provider, "name", "none"),
            "alias_of": "web.extract",
            "src_origin_tool": "WebFetch",
        },
        read_only=True,
        activity_kind="web",
        activity_title="Extract web content",
        activity_target_argument="url",
    )
    _register_builtin_tool(
        registry,
        name="ListMcpResourcesTool",
        description="List resources from configured MCP servers. src-origin alias for mcp.resources.",
        parameters=MCP_RESOURCES_SCHEMA,
        handler=lambda server="", uri_prefix="", max_results=50: mcp_resources(
            context,
            server=server,
            uri_prefix=uri_prefix,
            max_results=max_results,
        ),
        metadata={"risk": "low", "alias_of": "mcp.resources", "src_origin_tool": "ListMcpResourcesTool"},
        read_only=True,
        activity_kind="mcp",
        activity_title="List MCP resources",
        activity_target_argument="server",
    )
    _register_builtin_tool(
        registry,
        name="ReadMcpResourceTool",
        description="Read a resource from a configured MCP server. src-origin alias for mcp.read_resource.",
        parameters=MCP_READ_RESOURCE_SCHEMA,
        handler=lambda uri, server="": mcp_read_resource(context, uri=uri, server=server),
        metadata={"risk": "medium", "alias_of": "mcp.read_resource", "src_origin_tool": "ReadMcpResourceTool"},
        read_only=True,
        activity_kind="mcp",
        activity_title="Read MCP resource",
        activity_target_argument="uri",
    )
    for alias_name, src_origin_tool, alias_of in (
        ("TaskOutput", "TaskOutput", "task.output"),
        ("AgentOutputTool", "AgentOutputTool", "task.output"),
        ("BashOutputTool", "BashOutputTool", "shell.output"),
    ):
        _register_builtin_tool(
            registry,
            name=alias_name,
            description="Read output from a tracked or background task. src-origin alias for task.output/shell.output.",
            parameters=SRC_ORIGIN_TASK_OUTPUT_SCHEMA,
            handler=lambda task_id, block=True, timeout=30000, max_bytes=20000: _src_origin_task_output(
                context,
                task_id=task_id,
                block=block,
                timeout=timeout,
                max_bytes=max_bytes,
            ),
            metadata={"risk": "low", "alias_of": alias_of, "src_origin_tool": src_origin_tool},
            read_only=True,
            activity_kind="state",
            activity_title="Read task output",
            activity_target_argument="task_id",
        )
    for alias_name, src_origin_tool in (("TaskStop", "TaskStop"), ("KillShell", "KillShell")):
        _register_builtin_tool(
            registry,
            name=alias_name,
            description="Stop a tracked or background task. src-origin alias for task.stop/shell.kill.",
            parameters=SRC_ORIGIN_TASK_STOP_SCHEMA,
            handler=lambda task_id="", shell_id="": _src_origin_task_stop(context, task_id=task_id, shell_id=shell_id),
            metadata={"risk": "medium", "writes_state": True, "alias_of": "task.stop", "src_origin_tool": src_origin_tool},
            writes_state=True,
            concurrency_safe=False,
            activity_kind="state",
            activity_title="Stop task",
            activity_target_argument="task_id",
        )
    _register_builtin_tool(
        registry,
        name="TaskCreate",
        description="Create a tracked task. src-origin alias for task.create.",
        parameters=SRC_ORIGIN_TASK_CREATE_SCHEMA,
        handler=lambda subject, description, activeForm="", metadata=None: _src_origin_task_create(
            context,
            subject=subject,
            description=description,
            activeForm=activeForm,
            metadata=metadata,
        ),
        metadata={"risk": "medium", "writes_state": True, "alias_of": "task.create", "src_origin_tool": "TaskCreate"},
        writes_state=True,
        activity_kind="state",
        activity_title="Create task",
        activity_target_argument="subject",
    )
    _register_builtin_tool(
        registry,
        name="TaskList",
        description="List tracked tasks. src-origin alias for task.list.",
        parameters=SRC_ORIGIN_EMPTY_SCHEMA,
        handler=lambda: task_list(context),
        metadata={"risk": "low", "alias_of": "task.list", "src_origin_tool": "TaskList"},
        read_only=True,
        activity_kind="state",
        activity_title="List tasks",
    )
    _register_builtin_tool(
        registry,
        name="TaskGet",
        description="Load a tracked task by id. src-origin alias for task.get.",
        parameters=SRC_ORIGIN_TASK_GET_SCHEMA,
        handler=lambda taskId: task_get(context, task_id=taskId),
        metadata={"risk": "low", "alias_of": "task.get", "src_origin_tool": "TaskGet"},
        read_only=True,
        activity_kind="state",
        activity_title="Read task",
        activity_target_argument="taskId",
    )
    _register_builtin_tool(
        registry,
        name="TaskUpdate",
        description="Update a tracked task. src-origin alias for task.update.",
        parameters=SRC_ORIGIN_TASK_UPDATE_SCHEMA,
        handler=lambda taskId,
        subject="",
        description="",
        activeForm="",
        status="",
        owner="",
        addBlocks=None,
        addBlockedBy=None,
        metadata=None: _src_origin_task_update(
            context,
            taskId=taskId,
            subject=subject,
            description=description,
            activeForm=activeForm,
            status=status,
            owner=owner,
            addBlocks=addBlocks,
            addBlockedBy=addBlockedBy,
            metadata=metadata,
        ),
        metadata={"risk": "medium", "writes_state": True, "alias_of": "task.update", "src_origin_tool": "TaskUpdate"},
        writes_state=True,
        concurrency_safe=False,
        activity_kind="state",
        activity_title="Update task",
        activity_target_argument="taskId",
    )
    _register_builtin_tool(
        registry,
        name="CronCreate",
        description="Schedule a recurring or one-shot prompt. src-origin alias for schedule.create.",
        parameters=SRC_ORIGIN_CRON_CREATE_SCHEMA,
        handler=lambda cron, prompt, recurring=True, durable=False: _src_origin_cron_create(
            context,
            cron=cron,
            prompt=prompt,
            recurring=recurring,
            durable=durable,
        ),
        metadata={"risk": "medium", "writes_state": True, "alias_of": "schedule.create", "src_origin_tool": "CronCreate"},
        writes_state=True,
        activity_kind="state",
        activity_title="Create schedule",
        activity_target_argument="cron",
    )
    _register_builtin_tool(
        registry,
        name="CronList",
        description="List scheduled prompts. src-origin alias for schedule.list.",
        parameters=SRC_ORIGIN_EMPTY_SCHEMA,
        handler=lambda: schedule_list(context),
        metadata={"risk": "low", "alias_of": "schedule.list", "src_origin_tool": "CronList"},
        read_only=True,
        activity_kind="state",
        activity_title="List schedules",
    )
    _register_builtin_tool(
        registry,
        name="CronDelete",
        description="Delete a scheduled prompt. src-origin alias for schedule.delete.",
        parameters=SRC_ORIGIN_CRON_DELETE_SCHEMA,
        handler=lambda id: schedule_delete(context, schedule_id=id),
        metadata={"risk": "medium", "writes_state": True, "alias_of": "schedule.delete", "src_origin_tool": "CronDelete"},
        writes_state=True,
        activity_kind="state",
        activity_title="Delete schedule",
        activity_target_argument="id",
    )
    _register_builtin_tool(
        registry,
        name="ToolSearch",
        description="Search registered tools. src-origin alias for tool.search.",
        parameters=TOOL_SEARCH_SCHEMA,
        handler=lambda query="", max_results=5, include_all=False: tool_search(
            context,
            registry,
            query=query,
            max_results=max_results,
            include_all=include_all,
        ),
        metadata={"risk": "low", "alias_of": "tool.search", "src_origin_tool": "ToolSearch"},
        read_only=True,
        activity_kind="state",
        activity_title="Search tools",
        activity_target_argument="query",
    )
    _register_builtin_tool(
        registry,
        name="EnterPlanMode",
        description="Enter plan mode. src-origin alias for plan.enter.",
        parameters=PLAN_ENTER_SCHEMA,
        handler=lambda: plan_enter(context),
        metadata={"risk": "low", "writes_state": True, "alias_of": "plan.enter", "src_origin_tool": "EnterPlanMode"},
        writes_state=True,
        activity_kind="state",
        activity_title="Enter plan mode",
    )
    _register_builtin_tool(
        registry,
        name="ExitPlanMode",
        description="Exit plan mode with a concrete plan. src-origin alias for plan.exit.",
        parameters=PLAN_EXIT_SCHEMA,
        handler=lambda plan, allowedPrompts=None, allowed_prompts=None: plan_exit(
            context,
            plan=plan,
            allowedPrompts=allowedPrompts,
            allowed_prompts=allowed_prompts,
        ),
        metadata={
            "risk": "medium",
            "writes_state": True,
            "requires_approval": True,
            "alias_of": "plan.exit",
            "src_origin_tool": "ExitPlanMode",
        },
        writes_state=True,
        activity_kind="state",
        activity_title="Exit plan mode",
        activity_target_argument="plan",
    )
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


def _register_commands(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    registry.register(
        "command.discover",
        "Discover prompt-backed workspace commands in .agents/commands or commands.",
        COMMAND_DISCOVER_SCHEMA,
        lambda query="", max_results=50: command_discover(context, query=query, max_results=max_results),
        metadata={"risk": "low", "model_call": True},
    )
    registry.register(
        "command.render",
        "Render a prompt-backed workspace command with argument text.",
        COMMAND_RENDER_SCHEMA,
        lambda name, arguments="": command_render(context, name=name, arguments=arguments),
        metadata={"risk": "low", "model_call": True},
    )
    registry.register(
        "command.read",
        "Read a prompt-backed workspace command file.",
        COMMAND_READ_SCHEMA,
        lambda name, max_bytes=20000: command_read(context, name=name, max_bytes=max_bytes),
        metadata={"risk": "low", "model_call": True},
    )
    registry.register(
        "command.save",
        "Save a prompt-backed workspace command under .agents/commands.",
        COMMAND_SAVE_SCHEMA,
        lambda name,
        content,
        description="",
        argument_hint="",
        aliases=None,
        category="custom",
        overwrite=False: command_save(
            context,
            name=name,
            content=content,
            description=description,
            argument_hint=argument_hint,
            aliases=aliases,
            category=category,
            overwrite=overwrite,
        ),
        metadata={"risk": "medium", "writes_files": True, "model_call": True},
    )
    registry.register(
        "command.delete",
        "Delete a prompt-backed workspace command.",
        COMMAND_DELETE_SCHEMA,
        lambda name: command_delete(context, name=name),
        metadata={"risk": "medium", "writes_files": True, "model_call": True},
    )


def _register_meta(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    registry.register(
        "tool.search",
        "Search the current tool catalog by name, description, or metadata.",
        TOOL_SEARCH_SCHEMA,
        lambda query="", max_results=20, include_all=False: tool_search(
            context,
            registry,
            query=query,
            max_results=max_results,
            include_all=include_all,
        ),
        metadata={"risk": "low", "model_call": True},
    )
    registry.register(
        "skill.discover",
        "Discover available local skills and their tool/prompt contributions.",
        SKILL_DISCOVER_SCHEMA,
        lambda query="", max_results=20, include_prompt=False: skill_discover(
            context,
            query=query,
            max_results=max_results,
            include_prompt=include_prompt,
        ),
        metadata={"risk": "low", "model_call": True},
    )


def _register_plugins(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    registry.register(
        "plugin.discover",
        "Discover local plugins and their tool/prompt contributions in the current workspace.",
        PLUGIN_DISCOVER_SCHEMA,
        lambda query="", max_results=20, include_prompt=False: plugin_discover(
            context,
            query=query,
            max_results=max_results,
            include_prompt=include_prompt,
        ),
        metadata={"risk": "low", "model_call": True},
    )
    registry.register(
        "plugin.install",
        "Install a local plugin directory into .agents/plugins.",
        PLUGIN_INSTALL_SCHEMA,
        lambda source: plugin_install(context, source=source),
        metadata={"risk": "medium", "writes_files": True, "writes_state": True, "model_call": True},
    )
    registry.register(
        "plugin.uninstall",
        "Uninstall an installed plugin from .agents/plugins by name.",
        PLUGIN_UNINSTALL_SCHEMA,
        lambda name: plugin_uninstall(context, name=name),
        metadata={"risk": "medium", "writes_files": True, "writes_state": True, "model_call": True},
    )


def _register_extension_management(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    registry.register(
        "skill.install",
        "Install a local skill JSON file or skill package directory into skills.",
        SKILL_INSTALL_SCHEMA,
        lambda source: skill_install(context, source=source),
        metadata={"risk": "medium", "writes_files": True, "writes_state": True, "model_call": True},
    )
    registry.register(
        "skill.uninstall",
        "Uninstall a local skill from skills by name.",
        SKILL_UNINSTALL_SCHEMA,
        lambda name: skill_uninstall(context, name=name),
        metadata={"risk": "medium", "writes_files": True, "writes_state": True, "model_call": True},
    )
    registry.register(
        "skill.use",
        "Enable a local skill for the current session, including prompt fragments and tool contributions.",
        EXTENSION_NAME_SCHEMA,
        lambda name: skill_use(context, registry, name=name),
        metadata={"risk": "medium", "writes_state": True, "model_call": True},
    )
    registry.register(
        "skill.disable",
        "Disable a previously enabled local skill's tool contributions for the current session.",
        EXTENSION_NAME_SCHEMA,
        lambda name: skill_disable(context, name=name),
        metadata={"risk": "medium", "writes_state": True, "model_call": True},
    )
    registry.register(
        "plugin.enable",
        "Enable a local plugin for the current session, including prompt fragments and tool contributions.",
        EXTENSION_NAME_SCHEMA,
        lambda name: plugin_enable(context, registry, name=name),
        metadata={"risk": "medium", "writes_state": True, "model_call": True},
    )
    registry.register(
        "plugin.disable",
        "Disable a previously enabled local plugin's tool contributions for the current session.",
        EXTENSION_NAME_SCHEMA,
        lambda name: plugin_disable(context, name=name),
        metadata={"risk": "medium", "writes_state": True, "model_call": True},
    )


def _register_mcp_management(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    registry.register(
        "mcp.servers",
        "Read configured and loaded MCP server status.",
        MCP_SERVERS_SCHEMA,
        lambda: mcp_servers(context),
        metadata={"risk": "low", "source": "mcp", "model_call": True},
    )
    registry.register(
        "mcp.configure",
        "Configure the local MCP server command for this session.",
        MCP_CONFIGURE_SCHEMA,
        lambda command="", name="default", transport="", url="", headers=None, auth_token="", authToken="", execution_mode="", sandbox_profile="", auth_required=False, auth_url="", auth_status="", auth_message="": mcp_configure(
            context,
            command=command,
            name=name,
            transport=transport,
            url=url,
            headers=headers,
            auth_token=auth_token or authToken,
            execution_mode=execution_mode,
            sandbox_profile=sandbox_profile,
            auth_required=auth_required,
            auth_url=auth_url,
            auth_status=auth_status,
            auth_message=auth_message,
        ),
        metadata={"risk": "medium", "writes_state": True, "source": "mcp", "model_call": True},
    )
    registry.register(
        "mcp.detect_ide",
        "Detect Claude IDE extension MCP lockfiles for the current workspace.",
        IDE_DISCOVERY_SCHEMA,
        lambda cwd="", lockfile_dirs=None, lockfiles=None, include_invalid=False, port=0, skip_valid_check=False, host="": mcp_detect_ide(
            context,
            cwd=cwd,
            lockfile_dirs=lockfile_dirs,
            lockfiles=lockfiles,
            include_invalid=include_invalid,
            port=port,
            skip_valid_check=skip_valid_check,
            host=host,
        ),
        metadata={"risk": "low", "source": "mcp", "model_call": True},
    )
    registry.register(
        "mcp.configure_ide",
        "Detect and save a Claude IDE extension MCP server for this workspace.",
        MCP_CONFIGURE_IDE_SCHEMA,
        lambda name="ide", cwd="", lockfile_dirs=None, lockfiles=None, include_invalid=False, port=0, skip_valid_check=False, host="", index=-1: mcp_configure_ide(
            context,
            name=name,
            cwd=cwd,
            lockfile_dirs=lockfile_dirs,
            lockfiles=lockfiles,
            include_invalid=include_invalid,
            port=port,
            skip_valid_check=skip_valid_check,
            host=host,
            index=index,
        ),
        metadata={"risk": "medium", "writes_state": True, "source": "mcp", "model_call": True},
    )
    registry.register(
        "mcp.ide_extension_status",
        "Check whether the Claude IDE extension is installed for an IDE.",
        IDE_EXTENSION_SCHEMA,
        lambda ide_type="", ideType="", target_version="", targetVersion="": mcp_ide_extension_status(
            context,
            ide_type=ide_type or ideType,
        ),
        metadata={"risk": "low", "requires_process": True, "source": "mcp", "model_call": True},
    )
    registry.register(
        "mcp.install_ide_extension",
        "Install or update the Claude IDE extension for supported VS Code-family IDEs.",
        IDE_EXTENSION_SCHEMA,
        lambda ide_type="", ideType="", target_version="", targetVersion="": mcp_install_ide_extension(
            context,
            ide_type=ide_type or ideType,
            target_version=target_version or targetVersion,
        ),
        metadata={
            "risk": "medium",
            "writes_state": True,
            "requires_process": True,
            "source": "mcp",
            "model_call": True,
        },
    )
    registry.register(
        "mcp.clear",
        "Clear local MCP server configuration and loaded providers for this session.",
        MCP_CLEAR_SCHEMA,
        lambda: mcp_clear(context),
        metadata={"risk": "medium", "writes_state": True, "source": "mcp", "model_call": True},
    )
    registry.register(
        "mcp.reload",
        "Reconnect configured MCP servers and swap loaded MCP tool handlers.",
        MCP_RELOAD_SCHEMA,
        lambda: mcp_reload(context, registry),
        metadata={"risk": "medium", "writes_state": True, "source": "mcp", "model_call": True},
    )
    registry.register(
        "mcp.reconnect",
        "Reconnect one configured MCP server and swap only that server's tool handlers.",
        MCP_SERVER_NAME_SCHEMA,
        lambda name="": mcp_reconnect(context, registry, name=name),
        metadata={"risk": "medium", "writes_state": True, "source": "mcp", "model_call": True},
    )
    registry.register(
        "mcp.enable",
        "Enable a previously configured MCP server for this session scope.",
        MCP_SERVER_NAME_SCHEMA,
        lambda name="": mcp_enable(context, name=name),
        metadata={"risk": "medium", "writes_state": True, "source": "mcp", "model_call": True},
    )
    registry.register(
        "mcp.disable",
        "Disable a configured MCP server without deleting its saved command.",
        MCP_SERVER_NAME_SCHEMA,
        lambda name="": mcp_disable(context, name=name),
        metadata={"risk": "medium", "writes_state": True, "source": "mcp", "model_call": True},
    )
    registry.register(
        "mcp.remove",
        "Remove a saved MCP server configuration.",
        MCP_SERVER_NAME_SCHEMA,
        lambda name="": mcp_remove(context, name=name),
        metadata={"risk": "medium", "writes_state": True, "source": "mcp", "model_call": True},
    )


def _register_mcp_prompts(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    registry.register(
        "mcp.prompts",
        "List prompt templates exposed by configured MCP servers.",
        MCP_PROMPTS_SCHEMA,
        lambda server="", query="", max_results=50: mcp_prompts(
            context,
            server=server,
            query=query,
            max_results=max_results,
        ),
        metadata={"risk": "low", "source": "mcp", "model_call": True},
    )
    registry.register(
        "mcp.get_prompt",
        "Render a prompt template exposed by a configured MCP server.",
        MCP_GET_PROMPT_SCHEMA,
        lambda name, server="", arguments=None: mcp_get_prompt(
            context,
            name=name,
            server=server,
            arguments=arguments,
        ),
        metadata={"risk": "medium", "source": "mcp", "model_call": True},
    )


def _register_mcp_resources(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    registry.register(
        "mcp.resources",
        "List resources exposed by configured MCP servers.",
        MCP_RESOURCES_SCHEMA,
        lambda server="", uri_prefix="", max_results=50: mcp_resources(
            context,
            server=server,
            uri_prefix=uri_prefix,
            max_results=max_results,
        ),
        metadata={"risk": "low", "source": "mcp", "model_call": True},
    )
    registry.register(
        "mcp.read_resource",
        "Read a resource exposed by a configured MCP server.",
        MCP_READ_RESOURCE_SCHEMA,
        lambda uri, server="": mcp_read_resource(context, uri=uri, server=server),
        metadata={"risk": "medium", "source": "mcp", "model_call": True},
    )


def _register_prompt_templates(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    registry.register(
        "prompt.templates",
        "List local prompt templates in .agents/prompts.",
        PROMPT_TEMPLATES_SCHEMA,
        lambda query="", max_results=50: prompt_templates(context, query=query, max_results=max_results),
        metadata={"risk": "low", "model_call": True},
    )
    registry.register(
        "prompt.read",
        "Read a local prompt template from .agents/prompts.",
        PROMPT_READ_SCHEMA,
        lambda name, max_bytes=20000: prompt_read(context, name=name, max_bytes=max_bytes),
        metadata={"risk": "low", "model_call": True},
    )
    registry.register(
        "prompt.render",
        "Render a local prompt template with named or raw arguments.",
        PROMPT_RENDER_SCHEMA,
        lambda name, arguments=None, raw_arguments="": prompt_render(
            context,
            name=name,
            arguments=arguments,
            raw_arguments=raw_arguments,
        ),
        metadata={"risk": "low", "model_call": True},
    )
    registry.register(
        "prompt.save",
        "Save a local prompt template under .agents/prompts.",
        PROMPT_SAVE_SCHEMA,
        lambda name, content, overwrite=False: prompt_save(
            context,
            name=name,
            content=content,
            overwrite=overwrite,
        ),
        metadata={"risk": "medium", "writes_files": True, "model_call": True},
    )
    registry.register(
        "prompt.delete",
        "Delete a local prompt template under .agents/prompts.",
        PROMPT_DELETE_SCHEMA,
        lambda name: prompt_delete(context, name=name),
        metadata={"risk": "medium", "writes_files": True, "model_call": True},
    )


def _register_session_context(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    registry.register(
        "session.status",
        "Read current session, workspace, model, enabled tool, and context-window status.",
        SESSION_STATUS_SCHEMA,
        lambda: session_status(context),
        metadata={"risk": "low", "model_call": True},
    )
    registry.register(
        "session.export",
        "Export current session messages to a workspace JSON or Markdown file.",
        SESSION_EXPORT_SCHEMA,
        lambda path="", format="json", include_system=False: session_export(
            context,
            path=path,
            format=format,
            include_system=include_system,
        ),
        metadata={"risk": "medium", "writes_files": True, "model_call": True},
    )
    registry.register(
        "session.summary",
        "Summarize recent current-session messages for handoff or status review.",
        SESSION_SUMMARY_SCHEMA,
        lambda include_system=False, max_messages=50, max_chars=2000: session_summary(
            context,
            include_system=include_system,
            max_messages=max_messages,
            max_chars=max_chars,
        ),
        metadata={"risk": "low", "model_call": True},
    )
    registry.register(
        "context.trace",
        "Read compiled context trace items and their sources.",
        CONTEXT_TRACE_SCHEMA,
        lambda include_text=False, max_chars=240: context_trace(
            context,
            include_text=include_text,
            max_chars=max_chars,
        ),
        metadata={"risk": "low", "model_call": True},
    )
    registry.register(
        "context.messages",
        "Read recent session message summaries.",
        CONTEXT_MESSAGES_SCHEMA,
        lambda include_system=False, max_messages=50, max_chars=240: context_messages(
            context,
            include_system=include_system,
            max_messages=max_messages,
            max_chars=max_chars,
        ),
        metadata={"risk": "low", "model_call": True},
    )
    registry.register(
        "context.compact",
        "Compact older session messages using the configured context compaction strategy.",
        CONTEXT_COMPACT_SCHEMA,
        lambda target_tokens=None: context_compact(context, target_tokens=target_tokens),
        metadata={"risk": "medium", "writes_state": True, "model_call": True},
    )
    registry.register(
        "context.rewind",
        "Remove recent non-system messages from the current session context.",
        CONTEXT_REWIND_SCHEMA,
        lambda drop_last=1: context_rewind(context, drop_last=drop_last),
        metadata={"risk": "medium", "writes_state": True, "model_call": True},
    )


def _register_permissions(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    registry.register(
        "permission.status",
        "Read current tool permission profile and configured approval/deny lists.",
        PERMISSION_STATUS_SCHEMA,
        lambda: permission_status(context),
        metadata={"risk": "low", "model_call": True},
    )
    registry.register(
        "permission.sources",
        "Read tool permission rules grouped by source and behavior.",
        PERMISSION_SOURCES_SCHEMA,
        lambda: permission_sources(context),
        metadata={"risk": "low", "model_call": True},
    )
    registry.register(
        "permission.explain",
        "Explain the permission decision and impact for a hypothetical tool call.",
        PERMISSION_EXPLAIN_SCHEMA,
        lambda tool, arguments=None: permission_explain(context, tool=tool, arguments=arguments),
        metadata={"risk": "low", "model_call": True},
    )
    registry.register(
        "permission.add_rule",
        "Add a session-scoped allow, deny, or ask rule for a tool.",
        PERMISSION_RULE_SCHEMA,
        lambda behavior, tool: permission_add_rule(context, behavior=behavior, tool=tool),
        metadata={"risk": "medium", "writes_state": True, "model_call": True},
    )
    registry.register(
        "permission.remove_rule",
        "Remove session-scoped permission rules for a tool.",
        PERMISSION_REMOVE_RULE_SCHEMA,
        lambda tool, behavior="": permission_remove_rule(context, tool=tool, behavior=behavior),
        metadata={"risk": "medium", "writes_state": True, "model_call": True},
    )


def _register_hooks(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    registry.register(
        "hook.events",
        "List supported session hook events and actions.",
        HOOK_EVENTS_SCHEMA,
        lambda: hook_events(context),
        metadata={"risk": "low", "model_call": True},
    )
    registry.register(
        "hook.list",
        "List session hooks configured for the current agent session.",
        HOOK_LIST_SCHEMA,
        lambda event="", enabled=None, limit=50: hook_list(context, event=event, enabled=enabled, limit=limit),
        metadata={"risk": "low", "model_call": True},
    )
    registry.register(
        "hook.add",
        "Add a session hook that can append request guidance, record events, or gate tool use.",
        HOOK_ADD_SCHEMA,
        lambda event, name, action, content="", enabled=True, tool="", metadata=None: hook_add(
            context,
            event=event,
            name=name,
            action=action,
            content=content,
            enabled=enabled,
            tool=tool,
            metadata=metadata,
        ),
        metadata={"risk": "medium", "writes_state": True, "model_call": True},
    )
    registry.register(
        "hook.delete",
        "Delete a session hook by id or short id.",
        HOOK_DELETE_SCHEMA,
        lambda hook_id: hook_delete(context, hook_id=hook_id),
        metadata={"risk": "medium", "writes_state": True, "model_call": True},
    )


def _register_memory(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    registry.register(
        "memory.list",
        "List memories visible to the current user, agent, and workspace scope.",
        MEMORY_LIST_SCHEMA,
        lambda scope="", query="", limit=50: memory_list(context, scope=scope, query=query, limit=limit),
        metadata={"risk": "low"},
    )
    registry.register(
        "memory.add",
        "Save a memory for future context retrieval.",
        MEMORY_ADD_SCHEMA,
        lambda content, scope="workspace", metadata=None: memory_add(
            context,
            content=content,
            scope=scope,
            metadata=metadata,
        ),
        metadata={"risk": "medium", "writes_state": True, "model_call": True},
    )
    registry.register(
        "memory.edit",
        "Update a visible memory by id or short id.",
        MEMORY_EDIT_SCHEMA,
        lambda memory_id, content: memory_edit(context, memory_id=memory_id, content=content),
        metadata={"risk": "medium", "writes_state": True, "model_call": True},
    )
    registry.register(
        "memory.forget",
        "Delete a visible memory by id or short id.",
        MEMORY_FORGET_SCHEMA,
        lambda memory_id: memory_forget(context, memory_id=memory_id),
        metadata={"risk": "medium", "writes_state": True, "model_call": True},
    )


def _register_web(registry: ToolRegistry, context: ToolRuntimeContext, active_web_provider: WebSearchProvider) -> None:
    _register_builtin_tool(
        registry,
        name="web.search",
        description="Search the web through the configured control-plane search provider and return cited sources.",
        parameters=WEB_SEARCH_SCHEMA,
        handler=lambda query,
        topic="general",
        search_depth="basic",
        max_results=5,
        time_range="",
        include_domains=None,
        exclude_domains=None,
        country="",
        include_answer=False,
        include_raw_content=False,
        chunks_per_source=3: web_search(
            context,
            active_web_provider,
            query=query,
            topic=topic,
            search_depth=search_depth,
            max_results=max_results,
            time_range=time_range,
            include_domains=include_domains,
            exclude_domains=exclude_domains,
            country=country,
            include_answer=include_answer,
            include_raw_content=include_raw_content,
            chunks_per_source=chunks_per_source,
        ),
        metadata={
            "risk": "medium",
            "requires_network": True,
            "external_disclosure": True,
            "provider": getattr(active_web_provider, "name", "none"),
        },
        read_only=True,
        activity_kind="web",
        activity_title="Search web",
        activity_target_argument="query",
    )
    _register_builtin_tool(
        registry,
        name="web.extract",
        description="Extract clean content from specific URLs through the configured control-plane search provider.",
        parameters=WEB_EXTRACT_SCHEMA,
        handler=lambda urls, query="", extract_depth="basic", format="markdown", chunks_per_source=3: web_extract(
            context,
            active_web_provider,
            urls=urls,
            query=query,
            extract_depth=extract_depth,
            format=format,
            chunks_per_source=chunks_per_source,
        ),
        metadata={
            "risk": "medium",
            "requires_network": True,
            "external_disclosure": True,
            "provider": getattr(active_web_provider, "name", "none"),
        },
        read_only=True,
        activity_kind="web",
        activity_title="Extract web content",
        activity_target_argument="urls",
    )
    _register_builtin_tool(
        registry,
        name="web.map",
        description="Discover URLs under a site through the configured control-plane search provider.",
        parameters=WEB_MAP_SCHEMA,
        handler=lambda url, instructions="", max_depth=1, limit=50, include_domains=None, exclude_domains=None: web_map(
            context,
            active_web_provider,
            url=url,
            instructions=instructions,
            max_depth=max_depth,
            limit=limit,
            include_domains=include_domains,
            exclude_domains=exclude_domains,
        ),
        metadata={
            "risk": "high",
            "requires_network": True,
            "external_disclosure": True,
            "provider": getattr(active_web_provider, "name", "none"),
        },
        read_only=True,
        activity_kind="web",
        activity_title="Map site",
        activity_target_argument="url",
    )


def _register_git(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    _register_builtin_tool(
        registry,
        name="git.status",
        description="Return git workspace status from inside the sandbox.",
        parameters=GIT_STATUS_SCHEMA,
        handler=lambda short=True: git_status(context, short=short),
        read_only=True,
        activity_kind="git",
        activity_title="Inspect git status",
    )
    _register_builtin_tool(
        registry,
        name="git.diff",
        description="Return git diff output from inside the sandbox.",
        parameters=GIT_DIFF_SCHEMA,
        handler=lambda path="", staged=False, max_bytes=20000: git_diff(
            context,
            path=path,
            staged=staged,
            max_bytes=max_bytes,
        ),
        read_only=True,
        path_parameters=("path",),
        activity_kind="git",
        activity_title="Inspect git diff",
        activity_target_argument="path",
    )
    _register_builtin_tool(
        registry,
        name="git.add",
        description="Stage git workspace changes inside the sandbox.",
        parameters=GIT_ADD_SCHEMA,
        handler=lambda paths=None, all=False: git_add(context, paths=paths, all=all),
        metadata={"risk": "high", "requires_process": True, "writes_files": True},
        writes_state=True,
        concurrency_safe=False,
        path_parameters=("paths",),
        activity_kind="git",
        activity_title="Stage git changes",
        activity_target_argument="paths",
    )
    _register_builtin_tool(
        registry,
        name="git.commit",
        description="Create a git commit inside the sandbox.",
        parameters=GIT_COMMIT_SCHEMA,
        handler=lambda message, all=False, paths=None, allow_empty=False: git_commit(
            context,
            message=message,
            all=all,
            paths=paths,
            allow_empty=allow_empty,
        ),
        metadata={"risk": "high", "requires_process": True, "writes_files": True},
        writes_state=True,
        concurrency_safe=False,
        path_parameters=("paths",),
        activity_kind="git",
        activity_title="Create git commit",
        activity_target_argument="message",
    )
    _register_builtin_tool(
        registry,
        name="git.log",
        description="Return recent git history from inside the sandbox.",
        parameters=GIT_LOG_SCHEMA,
        handler=lambda max_count=10, path="", oneline=True, max_bytes=20000: git_log(
            context,
            max_count=max_count,
            path=path,
            oneline=oneline,
            max_bytes=max_bytes,
        ),
        metadata={"risk": "low", "requires_process": True},
        read_only=True,
        path_parameters=("path",),
        activity_kind="git",
        activity_title="Inspect git history",
        activity_target_argument="path",
    )
    _register_builtin_tool(
        registry,
        name="git.show",
        description="Return a git object or commit diff from inside the sandbox.",
        parameters=GIT_SHOW_SCHEMA,
        handler=lambda revision="HEAD", path="", stat=True, patch=True, max_bytes=20000: git_show(
            context,
            revision=revision,
            path=path,
            stat=stat,
            patch=patch,
            max_bytes=max_bytes,
        ),
        metadata={"risk": "low", "requires_process": True},
        read_only=True,
        path_parameters=("path",),
        activity_kind="git",
        activity_title="Inspect git object",
        activity_target_argument="revision",
    )


def _register_tests(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    _register_builtin_tool(
        registry,
        name="test.discover",
        description="Inspect workspace files and suggest likely test commands without running them.",
        parameters=TEST_DISCOVER_SCHEMA,
        handler=lambda path=".": discover_tests(context, path=path),
        read_only=True,
        path_parameters=("path",),
        activity_kind="terminal",
        activity_title="Discover tests",
        activity_target_argument="path",
    )
    _register_builtin_tool(
        registry,
        name="test.run",
        description="Run a test command inside the sandbox.",
        parameters=TEST_RUN_SCHEMA,
        handler=lambda command="pytest", timeout_seconds=120.0: run_tests(
            context,
            command=command,
            timeout_seconds=timeout_seconds,
        ),
        metadata={"risk": "high", "requires_process": True},
        concurrency_safe=False,
        activity_kind="terminal",
        activity_title="Run tests",
        activity_target_argument="command",
    )


def _register_planning(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    _register_builtin_tool(
        registry,
        name="todo.write",
        description="Update the structured todo list for the current session.",
        parameters=TODO_WRITE_SCHEMA,
        handler=lambda todos: todo_write(context, todos=todos),
        metadata={"risk": "low", "writes_state": True, "defer": True},
        writes_state=True,
        concurrency_safe=False,
        max_result_size_chars=100000,
        activity_kind="state",
        activity_title="Update todos",
        result_formatter=format_todo_write_result,
    )
    _register_builtin_tool(
        registry,
        name="todo.read",
        description="Read the structured todo list for the current session.",
        parameters=TODO_READ_SCHEMA,
        handler=lambda: todo_read(context),
        metadata={"risk": "low"},
        read_only=True,
        activity_kind="state",
        activity_title="Read todos",
    )
    registry.register(
        "plan.enter",
        "Enter read-only plan mode for exploration and implementation design.",
        PLAN_ENTER_SCHEMA,
        lambda: plan_enter(context),
        metadata={"risk": "low", "writes_state": True},
    )
    registry.register(
        "plan.status",
        "Read current plan-mode status, last plan, requested semantic permissions, and todos.",
        PLAN_STATUS_SCHEMA,
        lambda: plan_status(context),
        metadata={"risk": "low"},
    )
    registry.register(
        "plan.exit",
        "Exit plan mode by presenting a concrete implementation plan.",
        PLAN_EXIT_SCHEMA,
        lambda plan, allowedPrompts=None, allowed_prompts=None: plan_exit(
            context,
            plan=plan,
            allowedPrompts=allowedPrompts,
            allowed_prompts=allowed_prompts,
        ),
        metadata={"risk": "medium", "writes_state": True, "requires_approval": True},
    )


def _register_tasks(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    registry.register(
        "task.create",
        "Create a tracked task for the current agent and workspace.",
        TASK_CREATE_SCHEMA,
        lambda title, input="", metadata=None: task_create(
            context,
            title=title,
            input=input,
            metadata=metadata,
        ),
        metadata={"risk": "low", "writes_state": True},
    )
    registry.register(
        "task.list",
        "List tracked tasks for the current agent and workspace.",
        TASK_LIST_SCHEMA,
        lambda status="", agent_id="", limit=50: task_list(
            context,
            status=status,
            agent_id=agent_id,
            limit=limit,
        ),
        metadata={"risk": "low"},
    )
    registry.register(
        "task.get",
        "Load a tracked task and its steps by id or short id.",
        TASK_GET_SCHEMA,
        lambda task_id: task_get(context, task_id=task_id),
        metadata={"risk": "low"},
    )
    registry.register(
        "task.update",
        "Update a tracked task title, input, status, or metadata.",
        TASK_UPDATE_SCHEMA,
        lambda task_id, status="", title="", input="", metadata=None: task_update(
            context,
            task_id=task_id,
            status=status,
            title=title,
            input=input,
            metadata=metadata,
        ),
        metadata={"risk": "medium", "writes_state": True},
    )
    registry.register(
        "task.stop",
        "Cancel a tracked task and any pending or running task steps.",
        TASK_STOP_SCHEMA,
        lambda task_id: task_stop(context, task_id=task_id),
        metadata={"risk": "medium", "writes_state": True},
    )
    registry.register(
        "task.output",
        "Return task step output and errors by id or short id.",
        TASK_OUTPUT_SCHEMA,
        lambda task_id, max_bytes=20000: task_output(context, task_id=task_id, max_bytes=max_bytes),
        metadata={"risk": "low"},
    )
    registry.register(
        "task.run",
        "Run a tracked task through a child agent session and record run, step, output, and events.",
        TASK_RUN_SCHEMA,
        lambda task_id="", title="", input="", metadata=None, step_name="execute": task_run(
            context,
            task_id=task_id,
            title=title,
            input=input,
            metadata=metadata,
            step_name=step_name,
        ),
        metadata={"risk": "high", "writes_state": True, "spawns_agent": True, "model_call": True},
    )
    registry.register(
        "task.background",
        "Start a tracked task in the background and return immediately.",
        TASK_BACKGROUND_SCHEMA,
        lambda task_id="", title="", input="", metadata=None, step_name="execute": task_background(
            context,
            task_id=task_id,
            title=title,
            input=input,
            metadata=metadata,
            step_name=step_name,
        ),
        metadata={"risk": "high", "writes_state": True, "spawns_agent": True, "model_call": True},
    )
    registry.register(
        "task.backgrounds",
        "List background tasks launched by the current session.",
        TASK_BACKGROUNDS_SCHEMA,
        lambda: task_backgrounds(context),
        metadata={"risk": "low", "model_call": True},
    )


def _register_schedules(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    registry.register(
        "schedule.create",
        "Create a scheduled task definition for the current agent scope.",
        SCHEDULE_CREATE_SCHEMA,
        lambda title, schedule, input="", enabled=True, metadata=None: schedule_create(
            context,
            title=title,
            schedule=schedule,
            input=input,
            enabled=enabled,
            metadata=metadata,
        ),
        metadata={"risk": "medium", "writes_state": True, "model_call": True},
    )
    registry.register(
        "schedule.list",
        "List scheduled task definitions for the current agent scope.",
        SCHEDULE_LIST_SCHEMA,
        lambda enabled=None, limit=50: schedule_list(context, enabled=enabled, limit=limit),
        metadata={"risk": "low", "model_call": True},
    )
    registry.register(
        "schedule.delete",
        "Delete a scheduled task definition by id or short id.",
        SCHEDULE_DELETE_SCHEMA,
        lambda schedule_id: schedule_delete(context, schedule_id=schedule_id),
        metadata={"risk": "medium", "writes_state": True, "model_call": True},
    )
    registry.register(
        "schedule.run",
        "Run a scheduled task definition now, optionally in the background.",
        SCHEDULE_RUN_SCHEMA,
        lambda schedule_id, background=True: schedule_run(context, schedule_id=schedule_id, background=background),
        metadata={"risk": "high", "writes_state": True, "spawns_agent": True, "model_call": True},
    )


def _register_workflows(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    registry.register(
        "workflow.templates",
        "List saved workspace workflows from .agents/workflows.",
        WORKFLOW_TEMPLATES_SCHEMA,
        lambda query="", max_results=50: workflow_templates(context, query=query, max_results=max_results),
        metadata={"risk": "low", "model_call": True},
    )
    registry.register(
        "workflow.read",
        "Read and validate a saved workspace workflow by name.",
        WORKFLOW_READ_SCHEMA,
        lambda name: workflow_read(context, name=name),
        metadata={"risk": "low", "model_call": True},
    )
    registry.register(
        "workflow.save",
        "Save a validated workflow DAG to .agents/workflows for reuse.",
        WORKFLOW_SAVE_SCHEMA,
        lambda name, nodes, workflow_id="", edges=None, metadata=None, overwrite=False: workflow_save(
            context,
            name=name,
            nodes=nodes,
            workflow_id=workflow_id,
            edges=edges,
            metadata=metadata,
            overwrite=overwrite,
        ),
        metadata={"risk": "medium", "writes_files": True, "model_call": True},
    )
    registry.register(
        "workflow.delete",
        "Delete a saved workspace workflow by name.",
        WORKFLOW_DELETE_SCHEMA,
        lambda name: workflow_delete(context, name=name),
        metadata={"risk": "medium", "writes_files": True, "model_call": True},
    )
    registry.register(
        "workflow.validate",
        "Validate a local workflow DAG and return deterministic execution order.",
        WORKFLOW_VALIDATE_SCHEMA,
        lambda nodes, workflow_id="", edges=None, metadata=None: workflow_validate(
            context,
            nodes=nodes,
            workflow_id=workflow_id,
            edges=edges,
            metadata=metadata,
        ),
        metadata={"risk": "low", "model_call": True},
    )
    registry.register(
        "workflow.run",
        "Run a simple task/agent workflow DAG, stopping on approval gates or errors.",
        WORKFLOW_RUN_SCHEMA,
        lambda nodes, workflow_id="", edges=None, metadata=None, stop_on_error=True: workflow_run(
            context,
            nodes=nodes,
            workflow_id=workflow_id,
            edges=edges,
            metadata=metadata,
            stop_on_error=stop_on_error,
        ),
        metadata={"risk": "high", "writes_state": True, "spawns_agent": True, "model_call": True},
    )
    registry.register(
        "workflow.run_saved",
        "Run a saved workspace workflow by name, stopping on approval gates or errors.",
        WORKFLOW_RUN_SAVED_SCHEMA,
        lambda name, stop_on_error=True: workflow_run_saved(
            context,
            name=name,
            stop_on_error=stop_on_error,
        ),
        metadata={"risk": "high", "writes_state": True, "spawns_agent": True, "model_call": True},
    )


def _register_shell(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    _register_builtin_tool(
        registry,
        name="shell.run",
        description="Run a shell command in the current workspace when the sandbox allows process execution.",
        parameters=RUN_COMMAND_SCHEMA,
        handler=lambda command, timeout_seconds=20.0, timeout=None, description="", run_in_background=False, dangerouslyDisableSandbox=False: run_command(
            context,
            command,
            timeout_seconds=timeout_seconds,
            timeout=timeout,
            description=description,
            run_in_background=run_in_background,
            dangerouslyDisableSandbox=dangerouslyDisableSandbox,
        ),
        metadata={"risk": "high", "requires_process": True},
        concurrency_safe=False,
        interrupt_behavior="cancel",
        cancels_siblings_on_error=True,
        activity_kind="terminal",
        activity_title="Run shell command",
        activity_target_argument="command",
    )
    _register_builtin_tool(
        registry,
        name="shell.output",
        description="Read output and status for a background shell command.",
        parameters=SHELL_OUTPUT_SCHEMA,
        handler=lambda task_id, block=True, timeout_seconds=30.0, max_bytes=20000: shell_output(
            context,
            task_id=task_id,
            block=block,
            timeout_seconds=timeout_seconds,
            max_bytes=max_bytes,
        ),
        read_only=True,
        activity_kind="terminal",
        activity_title="Read background shell output",
        activity_target_argument="task_id",
    )
    _register_builtin_tool(
        registry,
        name="shell.backgrounds",
        description="List background shell commands launched by the current session.",
        parameters=SHELL_BACKGROUNDS_SCHEMA,
        handler=lambda: shell_backgrounds(context),
        read_only=True,
        activity_kind="terminal",
        activity_title="List background shell commands",
    )
    _register_builtin_tool(
        registry,
        name="shell.kill",
        description="Stop a background shell command.",
        parameters=SHELL_KILL_SCHEMA,
        handler=lambda task_id: shell_kill(context, task_id=task_id),
        metadata={"risk": "medium", "requires_process": True},
        writes_state=True,
        concurrency_safe=False,
        activity_kind="terminal",
        activity_title="Stop background shell command",
        activity_target_argument="task_id",
    )


def _register_sleep(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    _register_builtin_tool(
        registry,
        name="sleep.wait",
        description="Wait for a specified duration without holding a shell process.",
        parameters=SLEEP_WAIT_SCHEMA,
        handler=lambda duration_seconds, reason="": sleep_wait(
            context,
            duration_seconds=duration_seconds,
            reason=reason,
        ),
        read_only=True,
        concurrency_safe=True,
        interrupt_behavior="cancel",
        activity_kind="wait",
        activity_title="Wait",
        activity_target_argument="duration_seconds",
    )


def _register_browser(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    _register_builtin_tool(
        registry,
        name="browser.open",
        description="Fetch an HTTP(S) page inside the sandbox and store it in the run artifact store unless output_path is set.",
        parameters=BROWSER_OPEN_SCHEMA,
        handler=lambda url, output_path="", max_bytes=200000: browser_open(
            context,
            url=url,
            output_path=output_path,
            max_bytes=max_bytes,
        ),
        metadata={"risk": "high", "requires_process": True, "requires_network": True, "writes_files": True},
        writes_state=True,
        concurrency_safe=False,
        path_parameters=("output_path",),
        activity_kind="browser",
        activity_title="Open browser page",
        activity_target_argument="url",
    )
    _register_builtin_tool(
        registry,
        name="browser.download",
        description="Download an HTTP(S) URL inside the sandbox to the artifact store or an explicit workspace path.",
        parameters=BROWSER_DOWNLOAD_SCHEMA,
        handler=lambda url, path="", max_bytes=20000000: browser_download(
            context,
            url=url,
            path=path,
            max_bytes=max_bytes,
        ),
        metadata={"risk": "high", "requires_process": True, "requires_network": True, "writes_files": True},
        writes_state=True,
        concurrency_safe=False,
        path_parameters=("path",),
        activity_kind="browser",
        activity_title="Download URL",
        activity_target_argument="url",
    )


def _register_agent_profiles(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    registry.register(
        "agent.profiles",
        "List saved agent profiles for the current user.",
        AGENT_PROFILES_SCHEMA,
        lambda query="", limit=50: agent_profiles(context, query=query, limit=limit),
        metadata={"risk": "low", "model_call": True},
    )
    registry.register(
        "agent.save_profile",
        "Save the current session as an agent profile with optional overrides.",
        AGENT_SAVE_PROFILE_SCHEMA,
        lambda agent_id="", name="", system_prompt="", enabled_tools=None, skills=None, permission_profile="": agent_save_profile(
            context,
            agent_id=agent_id,
            name=name,
            system_prompt=system_prompt,
            enabled_tools=enabled_tools,
            skills=skills,
            permission_profile=permission_profile,
        ),
        metadata={"risk": "medium", "writes_state": True, "model_call": True},
    )


def _register_teams(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    registry.register(
        "team.create",
        "Create or update an agent team with named members.",
        TEAM_CREATE_SCHEMA,
        lambda team_id="", name="", description="", members=None: team_create(
            context,
            team_id=team_id,
            name=name,
            description=description,
            members=members,
        ),
        metadata={"risk": "low", "writes_state": True, "model_call": True},
    )
    registry.register(
        "team.delete",
        "Delete an agent team and its queued messages.",
        TEAM_DELETE_SCHEMA,
        lambda team_id="": team_delete(context, team_id=team_id),
        metadata={"risk": "medium", "writes_state": True, "model_call": True},
    )
    registry.register(
        "team.members",
        "List members for an agent team.",
        TEAM_MEMBERS_SCHEMA,
        lambda team_id="": team_members(context, team_id=team_id),
        metadata={"risk": "low", "model_call": True},
    )
    registry.register(
        "team.send",
        "Send a message to a team member or broadcast to the team.",
        TEAM_SEND_SCHEMA,
        lambda to, message, team_id="", from_agent="", message_type="message": team_send(
            context,
            to=to,
            message=message,
            team_id=team_id,
            from_agent=from_agent,
            message_type=message_type,
        ),
        metadata={"risk": "low", "writes_state": True, "model_call": True},
    )
    registry.register(
        "team.inbox",
        "Read queued team messages for an agent.",
        TEAM_INBOX_SCHEMA,
        lambda agent_id="", team_id="", unread_only=True, mark_read=False, limit=50: team_inbox(
            context,
            agent_id=agent_id,
            team_id=team_id,
            unread_only=unread_only,
            mark_read=mark_read,
            limit=limit,
        ),
        metadata={"risk": "low", "writes_state": True, "model_call": True},
    )
    registry.register(
        "team.run_member",
        "Run a bounded prompt with a configured team member and deliver the result to an inbox.",
        TEAM_RUN_MEMBER_SCHEMA,
        lambda agent_id, prompt, team_id="", reply_to="": team_run_member(
            context,
            agent_id=agent_id,
            prompt=prompt,
            team_id=team_id,
            reply_to=reply_to,
        ),
        metadata={"risk": "high", "writes_state": True, "spawns_agent": True, "model_call": True},
    )


def _register_agents(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    registry.register(
        "agent.run",
        "Run a bounded prompt in an in-process child agent and return the child agent result.",
        AGENT_RUN_SCHEMA,
        lambda prompt, description="", agent_id="", system_prompt="", enabled_tools=None: agent_run(
            context,
            prompt=prompt,
            description=description,
            agent_id=agent_id,
            system_prompt=system_prompt,
            enabled_tools=enabled_tools,
        ),
        metadata={"risk": "high", "spawns_agent": True, "model_call": True},
    )
