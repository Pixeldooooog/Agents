from __future__ import annotations

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
from agents.kernel.capabilities.tools.builtin.tests import TEST_DISCOVER_SCHEMA, TEST_RUN_SCHEMA, discover_tests, run_tests
from agents.kernel.capabilities.tools.context import ToolRuntimeContext
from agents.kernel.capabilities.tools.registry import ToolRegistry


def register_development_tools(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    _register_git(registry, context)
    _register_tests(registry, context)
    _register_planning(registry, context)


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
