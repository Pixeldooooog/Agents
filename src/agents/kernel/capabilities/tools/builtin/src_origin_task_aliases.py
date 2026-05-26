from __future__ import annotations

from agents.kernel.capabilities.tools.builtin.registration_helpers import register_builtin_tool
from agents.kernel.capabilities.tools.builtin.tasks import (
    SRC_ORIGIN_TASK_CREATE_SCHEMA,
    SRC_ORIGIN_TASK_GET_SCHEMA,
    SRC_ORIGIN_TASK_LIST_SCHEMA,
    SRC_ORIGIN_TASK_OUTPUT_SCHEMA,
    SRC_ORIGIN_TASK_STOP_SCHEMA,
    SRC_ORIGIN_TASK_UPDATE_SCHEMA,
    format_src_origin_task_create_result,
    format_src_origin_task_get_result,
    format_src_origin_task_list_result,
    format_src_origin_task_update_result,
    src_origin_task_create,
    src_origin_task_get,
    src_origin_task_list,
    src_origin_task_output,
    src_origin_task_stop,
    src_origin_task_update,
)
from agents.kernel.capabilities.tools.context import ToolRuntimeContext
from agents.kernel.capabilities.tools.registry import ToolRegistry


def register_src_origin_task_aliases(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    for alias_name, src_origin_tool, alias_of in (
        ("TaskOutput", "TaskOutput", "task.output"),
        ("AgentOutputTool", "AgentOutputTool", "task.output"),
        ("BashOutputTool", "BashOutputTool", "shell.output"),
    ):
        register_builtin_tool(
            registry,
            name=alias_name,
            description="Read output from a tracked or background task. src-origin alias for task.output/shell.output.",
            parameters=SRC_ORIGIN_TASK_OUTPUT_SCHEMA,
            handler=lambda task_id, block=True, timeout=30000: src_origin_task_output(
                context,
                task_id=task_id,
                block=block,
                timeout=timeout,
            ),
            metadata={"risk": "low", "defer": True, "alias_of": alias_of, "src_origin_tool": src_origin_tool},
            read_only=True,
            max_result_size_chars=100000,
            activity_kind="state",
            activity_title="Read task output",
            activity_target_argument="task_id",
        )

    for alias_name, src_origin_tool in (("TaskStop", "TaskStop"), ("KillShell", "KillShell")):
        register_builtin_tool(
            registry,
            name=alias_name,
            description="Stop a tracked or background task. src-origin alias for task.stop/shell.kill.",
            parameters=SRC_ORIGIN_TASK_STOP_SCHEMA,
            handler=lambda task_id="", shell_id="": src_origin_task_stop(context, task_id=task_id, shell_id=shell_id),
            metadata={
                "risk": "medium",
                "writes_state": True,
                "defer": True,
                "alias_of": "task.stop",
                "src_origin_tool": src_origin_tool,
            },
            writes_state=True,
            concurrency_safe=False,
            max_result_size_chars=100000,
            activity_kind="state",
            activity_title="Stop task",
            activity_target_argument="task_id",
        )

    register_builtin_tool(
        registry,
        name="TaskCreate",
        description="Create a tracked task. src-origin alias for task.create.",
        parameters=SRC_ORIGIN_TASK_CREATE_SCHEMA,
        handler=lambda subject, description, activeForm="", metadata=None: src_origin_task_create(
            context,
            subject=subject,
            description=description,
            activeForm=activeForm,
            metadata=metadata,
        ),
        metadata={
            "risk": "medium",
            "writes_state": True,
            "defer": True,
            "alias_of": "task.create",
            "src_origin_tool": "TaskCreate",
        },
        writes_state=True,
        max_result_size_chars=100000,
        activity_kind="state",
        activity_title="Create task",
        activity_target_argument="subject",
        result_formatter=format_src_origin_task_create_result,
    )
    register_builtin_tool(
        registry,
        name="TaskList",
        description="List tracked tasks. src-origin alias for task.list.",
        parameters=SRC_ORIGIN_TASK_LIST_SCHEMA,
        handler=lambda: src_origin_task_list(context),
        metadata={"risk": "low", "defer": True, "alias_of": "task.list", "src_origin_tool": "TaskList"},
        read_only=True,
        max_result_size_chars=100000,
        activity_kind="state",
        activity_title="List tasks",
        result_formatter=format_src_origin_task_list_result,
    )
    register_builtin_tool(
        registry,
        name="TaskGet",
        description="Load a tracked task by id. src-origin alias for task.get.",
        parameters=SRC_ORIGIN_TASK_GET_SCHEMA,
        handler=lambda taskId: src_origin_task_get(context, taskId=taskId),
        metadata={"risk": "low", "defer": True, "alias_of": "task.get", "src_origin_tool": "TaskGet"},
        read_only=True,
        max_result_size_chars=100000,
        activity_kind="state",
        activity_title="Read task",
        activity_target_argument="taskId",
        result_formatter=format_src_origin_task_get_result,
    )
    register_builtin_tool(
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
        metadata=None: src_origin_task_update(
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
        metadata={
            "risk": "medium",
            "writes_state": True,
            "defer": True,
            "alias_of": "task.update",
            "src_origin_tool": "TaskUpdate",
        },
        writes_state=True,
        concurrency_safe=False,
        max_result_size_chars=100000,
        activity_kind="state",
        activity_title="Update task",
        activity_target_argument="taskId",
        result_formatter=format_src_origin_task_update_result,
    )
