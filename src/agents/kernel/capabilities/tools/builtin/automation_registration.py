from __future__ import annotations

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
from agents.kernel.capabilities.tools.builtin.workflows import (
    WORKFLOW_DELETE_SCHEMA,
    WORKFLOW_READ_SCHEMA,
    WORKFLOW_RUN_SAVED_SCHEMA,
    WORKFLOW_RUN_SCHEMA,
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


def register_automation_tools(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    _register_workflows(registry, context)
    _register_tasks(registry, context)
    _register_schedules(registry, context)


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
