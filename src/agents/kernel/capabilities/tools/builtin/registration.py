from __future__ import annotations

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
from agents.kernel.capabilities.tools.builtin.meta import (
    SKILL_DISCOVER_SCHEMA,
    TOOL_SEARCH_SCHEMA,
    skill_discover,
    tool_search,
)
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
from agents.kernel.capabilities.tools.builtin.execution_registration import register_execution_tools
from agents.kernel.capabilities.tools.builtin.mcp.registration import register_mcp_builtin_tools
from agents.kernel.capabilities.tools.builtin.patch import (
    PATCH_APPLY_SCHEMA,
    apply_patch,
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
from agents.kernel.capabilities.tools.builtin.registration_helpers import register_builtin_tool as _register_builtin_tool
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
from agents.kernel.capabilities.tools.builtin.src_origin_agent_aliases import register_src_origin_aliases
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
from agents.kernel.capabilities.tools.context import ToolRuntimeContext
from agents.kernel.capabilities.tools.registry import ToolRegistry
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
    register_src_origin_aliases(registry, context, active_web_provider)
    _register_commands(registry, context)
    _register_meta(registry, context)
    _register_plugins(registry, context)
    _register_extension_management(registry, context)
    register_mcp_builtin_tools(registry, context)
    _register_prompt_templates(registry, context)
    _register_session_context(registry, context)
    _register_permissions(registry, context)
    _register_hooks(registry, context)
    _register_memory(registry, context)
    _register_web(registry, context, active_web_provider)
    register_execution_tools(registry, context)
    return list(BUILTIN_TOOL_NAMES)


def _agent_spec_metadata(context: ToolRuntimeContext) -> dict:
    metadata = getattr(getattr(context, "agent_spec", None), "metadata", None)
    return dict(metadata) if isinstance(metadata, dict) else {}


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
