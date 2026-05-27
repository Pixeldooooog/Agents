from __future__ import annotations

from agents.kernel.capabilities.tools.builtin.agents import AGENT_RUN_SCHEMA, agent_run
from agents.kernel.capabilities.tools.builtin.agent_profiles import (
    AGENT_PROFILES_SCHEMA,
    AGENT_SAVE_PROFILE_SCHEMA,
    agent_profiles,
    agent_save_profile,
)
from agents.kernel.capabilities.tools.builtin.browser import BROWSER_DOWNLOAD_SCHEMA, BROWSER_OPEN_SCHEMA, browser_download, browser_open
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
from agents.kernel.capabilities.tools.builtin.registration_helpers import register_builtin_tool as _register_builtin_tool
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
from agents.kernel.capabilities.tools.builtin.sleep import SLEEP_WAIT_SCHEMA, sleep_wait
from agents.kernel.capabilities.tools.builtin.task_schemas import (
    TASK_BACKGROUND_SCHEMA,
    TASK_BACKGROUNDS_SCHEMA,
    TASK_CREATE_SCHEMA,
    TASK_GET_SCHEMA,
    TASK_LIST_SCHEMA,
    TASK_OUTPUT_SCHEMA,
    TASK_RUN_SCHEMA,
    TASK_STOP_SCHEMA,
    TASK_UPDATE_SCHEMA,
)
from agents.kernel.capabilities.tools.builtin.tasks import (
    task_background,
    task_backgrounds,
    task_create,
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


def register_execution_tools(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
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
