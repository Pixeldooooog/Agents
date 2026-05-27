from __future__ import annotations

from agents.kernel.capabilities.tools.builtin.browser import BROWSER_DOWNLOAD_SCHEMA, BROWSER_OPEN_SCHEMA, browser_download, browser_open
from agents.kernel.capabilities.tools.builtin.registration_helpers import register_builtin_tool as _register_builtin_tool
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
from agents.kernel.capabilities.tools.context import ToolRuntimeContext
from agents.kernel.capabilities.tools.registry import ToolRegistry


def register_runtime_tools(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    _register_shell(registry, context)
    _register_sleep(registry, context)
    _register_browser(registry, context)


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
