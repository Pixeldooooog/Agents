from __future__ import annotations

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
from agents.kernel.capabilities.tools.builtin.filesystem import (
    DELETE_PATH_SCHEMA,
    LIST_DIR_SCHEMA,
    MOVE_PATH_SCHEMA,
    READ_FILE_SCHEMA,
    WRITE_FILE_SCHEMA,
    delete_path,
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
    MCP_SERVER_NAME_SCHEMA,
    MCP_SERVERS_SCHEMA,
    mcp_clear,
    mcp_configure,
    mcp_disable,
    mcp_enable,
    mcp_remove,
    mcp_servers,
)
from agents.kernel.capabilities.tools.builtin.patch import PATCH_APPLY_SCHEMA, apply_patch
from agents.kernel.capabilities.tools.builtin.planning import (
    PLAN_ENTER_SCHEMA,
    PLAN_EXIT_SCHEMA,
    PLAN_STATUS_SCHEMA,
    TODO_READ_SCHEMA,
    TODO_WRITE_SCHEMA,
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
from agents.kernel.capabilities.tools.builtin.search import GREP_SCHEMA, grep
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
from agents.kernel.capabilities.tools.builtin.shell import RUN_COMMAND_SCHEMA, run_command
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
    TEAM_INBOX_SCHEMA,
    TEAM_MEMBERS_SCHEMA,
    TEAM_RUN_MEMBER_SCHEMA,
    TEAM_SEND_SCHEMA,
    team_create,
    team_inbox,
    team_members,
    team_run_member,
    team_send,
)
from agents.kernel.capabilities.tools.builtin.tests import TEST_DISCOVER_SCHEMA, TEST_RUN_SCHEMA, discover_tests, run_tests
from agents.kernel.capabilities.tools.builtin.web import (
    WEB_EXTRACT_SCHEMA,
    WEB_MAP_SCHEMA,
    WEB_SEARCH_SCHEMA,
    web_extract,
    web_map,
    web_search,
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
from agents.kernel.capabilities.tools.context import ToolRuntimeContext
from agents.kernel.capabilities.tools.registry import ToolRegistry
from agents.kernel.capabilities.web import NullWebSearchProvider, WebSearchProvider


BUILTIN_TOOL_NAMES = [
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
    "browser.open",
    "browser.download",
    "agent.profiles",
    "agent.save_profile",
    "team.create",
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
    active_web_provider = web_provider or NullWebSearchProvider()
    _register_filesystem(registry, context)
    _register_patch_and_search(registry, context)
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
    _register_browser(registry, context)
    _register_agent_profiles(registry, context)
    _register_teams(registry, context)
    _register_agents(registry, context)
    return list(BUILTIN_TOOL_NAMES)


def _register_filesystem(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    registry.register(
        "filesystem.read",
        "Read a UTF-8 text file from the current workspace.",
        READ_FILE_SCHEMA,
        lambda path, max_bytes=20000: read_file(context, path, max_bytes=max_bytes),
    )
    registry.register(
        "filesystem.list",
        "List files and directories inside the current workspace.",
        LIST_DIR_SCHEMA,
        lambda path=".": list_dir(context, path=path),
    )
    registry.register(
        "filesystem.write",
        "Write a UTF-8 text file inside the current workspace when the sandbox allows writes.",
        WRITE_FILE_SCHEMA,
        lambda path, content: write_file(context, path, content),
        metadata={"risk": "medium", "writes_files": True},
    )
    registry.register(
        "filesystem.delete",
        "Delete a file or directory inside the current workspace.",
        DELETE_PATH_SCHEMA,
        lambda path, recursive=False: delete_path(context, path, recursive=recursive),
        metadata={"risk": "medium", "writes_files": True},
    )
    registry.register(
        "filesystem.move",
        "Move or rename a file or directory inside the current workspace.",
        MOVE_PATH_SCHEMA,
        lambda source_path, destination_path, overwrite=False: move_path(
            context,
            source_path=source_path,
            destination_path=destination_path,
            overwrite=overwrite,
        ),
        metadata={"risk": "medium", "writes_files": True},
    )


def _register_patch_and_search(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    registry.register(
        "patch.apply",
        "Apply exact text edits or create text files inside the current workspace.",
        PATCH_APPLY_SCHEMA,
        lambda edits=None, creates=None, dry_run=False: apply_patch(
            context,
            edits=edits,
            creates=creates,
            dry_run=dry_run,
        ),
        metadata={"risk": "medium", "writes_files": True},
    )
    registry.register(
        "search.grep",
        "Search text files inside the current workspace with a regular expression.",
        GREP_SCHEMA,
        lambda pattern, path=".", max_results=100, case_sensitive=True: grep(
            context,
            pattern,
            path=path,
            max_results=max_results,
            case_sensitive=case_sensitive,
        ),
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
        lambda command, name="default", execution_mode="", sandbox_profile="": mcp_configure(
            context,
            command=command,
            name=name,
            execution_mode=execution_mode,
            sandbox_profile=sandbox_profile,
        ),
        metadata={"risk": "medium", "writes_state": True, "source": "mcp", "model_call": True},
    )
    registry.register(
        "mcp.clear",
        "Clear local MCP server configuration and loaded providers for this session.",
        MCP_CLEAR_SCHEMA,
        lambda: mcp_clear(context),
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
    registry.register(
        "web.search",
        "Search the web through the configured control-plane search provider and return cited sources.",
        WEB_SEARCH_SCHEMA,
        lambda query,
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
    )
    registry.register(
        "web.extract",
        "Extract clean content from specific URLs through the configured control-plane search provider.",
        WEB_EXTRACT_SCHEMA,
        lambda urls, query="", extract_depth="basic", format="markdown", chunks_per_source=3: web_extract(
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
    )
    registry.register(
        "web.map",
        "Discover URLs under a site through the configured control-plane search provider.",
        WEB_MAP_SCHEMA,
        lambda url, instructions="", max_depth=1, limit=50, include_domains=None, exclude_domains=None: web_map(
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
    )


def _register_git(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    registry.register(
        "git.status",
        "Return git workspace status from inside the sandbox.",
        GIT_STATUS_SCHEMA,
        lambda short=True: git_status(context, short=short),
    )
    registry.register(
        "git.diff",
        "Return git diff output from inside the sandbox.",
        GIT_DIFF_SCHEMA,
        lambda path="", staged=False, max_bytes=20000: git_diff(
            context,
            path=path,
            staged=staged,
            max_bytes=max_bytes,
        ),
    )
    registry.register(
        "git.add",
        "Stage git workspace changes inside the sandbox.",
        GIT_ADD_SCHEMA,
        lambda paths=None, all=False: git_add(context, paths=paths, all=all),
        metadata={"risk": "high", "requires_process": True, "writes_files": True},
    )
    registry.register(
        "git.commit",
        "Create a git commit inside the sandbox.",
        GIT_COMMIT_SCHEMA,
        lambda message, all=False, paths=None, allow_empty=False: git_commit(
            context,
            message=message,
            all=all,
            paths=paths,
            allow_empty=allow_empty,
        ),
        metadata={"risk": "high", "requires_process": True, "writes_files": True},
    )
    registry.register(
        "git.log",
        "Return recent git history from inside the sandbox.",
        GIT_LOG_SCHEMA,
        lambda max_count=10, path="", oneline=True, max_bytes=20000: git_log(
            context,
            max_count=max_count,
            path=path,
            oneline=oneline,
            max_bytes=max_bytes,
        ),
        metadata={"risk": "low", "requires_process": True},
    )
    registry.register(
        "git.show",
        "Return a git object or commit diff from inside the sandbox.",
        GIT_SHOW_SCHEMA,
        lambda revision="HEAD", path="", stat=True, patch=True, max_bytes=20000: git_show(
            context,
            revision=revision,
            path=path,
            stat=stat,
            patch=patch,
            max_bytes=max_bytes,
        ),
        metadata={"risk": "low", "requires_process": True},
    )


def _register_tests(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    registry.register(
        "test.discover",
        "Inspect workspace files and suggest likely test commands without running them.",
        TEST_DISCOVER_SCHEMA,
        lambda path=".": discover_tests(context, path=path),
    )
    registry.register(
        "test.run",
        "Run a test command inside the sandbox.",
        TEST_RUN_SCHEMA,
        lambda command="pytest", timeout_seconds=120.0: run_tests(
            context,
            command=command,
            timeout_seconds=timeout_seconds,
        ),
        metadata={"risk": "high", "requires_process": True},
    )


def _register_planning(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    registry.register(
        "todo.write",
        "Update the structured todo list for the current session.",
        TODO_WRITE_SCHEMA,
        lambda todos: todo_write(context, todos=todos),
        metadata={"risk": "low", "writes_state": True},
    )
    registry.register(
        "todo.read",
        "Read the structured todo list for the current session.",
        TODO_READ_SCHEMA,
        lambda: todo_read(context),
        metadata={"risk": "low"},
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
        "Update a tracked task status.",
        TASK_UPDATE_SCHEMA,
        lambda task_id, status: task_update(context, task_id=task_id, status=status),
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
    registry.register(
        "shell.run",
        "Run a shell command in the current workspace when the sandbox allows process execution.",
        RUN_COMMAND_SCHEMA,
        lambda command, timeout_seconds=20.0: run_command(context, command, timeout_seconds=timeout_seconds),
        metadata={"risk": "high", "requires_process": True},
    )


def _register_browser(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    registry.register(
        "browser.open",
        "Fetch an HTTP(S) page inside the sandbox and store it in the run artifact store unless output_path is set.",
        BROWSER_OPEN_SCHEMA,
        lambda url, output_path="", max_bytes=200000: browser_open(
            context,
            url=url,
            output_path=output_path,
            max_bytes=max_bytes,
        ),
        metadata={"risk": "high", "requires_process": True, "requires_network": True, "writes_files": True},
    )
    registry.register(
        "browser.download",
        "Download an HTTP(S) URL inside the sandbox to the artifact store or an explicit workspace path.",
        BROWSER_DOWNLOAD_SCHEMA,
        lambda url, path="", max_bytes=20000000: browser_download(
            context,
            url=url,
            path=path,
            max_bytes=max_bytes,
        ),
        metadata={"risk": "high", "requires_process": True, "requires_network": True, "writes_files": True},
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
