from __future__ import annotations

from agents.kernel.capabilities.tools.builtin.registration_helpers import register_builtin_tool
from agents.kernel.capabilities.tools.builtin.schedules import (
    SRC_ORIGIN_CRON_CREATE_SCHEMA,
    SRC_ORIGIN_CRON_DELETE_SCHEMA,
    SRC_ORIGIN_CRON_LIST_SCHEMA,
    format_src_origin_cron_create_result,
    format_src_origin_cron_delete_result,
    format_src_origin_cron_list_result,
    src_origin_cron_create,
    src_origin_cron_delete,
    src_origin_cron_list,
)
from agents.kernel.capabilities.tools.context import ToolRuntimeContext
from agents.kernel.capabilities.tools.registry import ToolRegistry


def register_src_origin_schedule_aliases(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    register_builtin_tool(
        registry,
        name="CronCreate",
        description="Schedule a recurring or one-shot prompt. src-origin alias for schedule.create.",
        parameters=SRC_ORIGIN_CRON_CREATE_SCHEMA,
        handler=lambda cron, prompt, recurring=True, durable=False: src_origin_cron_create(
            context,
            cron=cron,
            prompt=prompt,
            recurring=recurring,
            durable=durable,
        ),
        metadata={
            "risk": "medium",
            "writes_state": True,
            "defer": True,
            "alias_of": "schedule.create",
            "src_origin_tool": "CronCreate",
        },
        writes_state=True,
        max_result_size_chars=100000,
        activity_kind="state",
        activity_title="Create schedule",
        activity_target_argument="cron",
        result_formatter=format_src_origin_cron_create_result,
    )
    register_builtin_tool(
        registry,
        name="CronList",
        description="List scheduled prompts. src-origin alias for schedule.list.",
        parameters=SRC_ORIGIN_CRON_LIST_SCHEMA,
        handler=lambda: src_origin_cron_list(context),
        metadata={"risk": "low", "defer": True, "alias_of": "schedule.list", "src_origin_tool": "CronList"},
        read_only=True,
        max_result_size_chars=100000,
        activity_kind="state",
        activity_title="List schedules",
        result_formatter=format_src_origin_cron_list_result,
    )
    register_builtin_tool(
        registry,
        name="CronDelete",
        description="Delete a scheduled prompt. src-origin alias for schedule.delete.",
        parameters=SRC_ORIGIN_CRON_DELETE_SCHEMA,
        handler=lambda id: src_origin_cron_delete(context, id=id),
        metadata={
            "risk": "medium",
            "writes_state": True,
            "defer": True,
            "alias_of": "schedule.delete",
            "src_origin_tool": "CronDelete",
        },
        writes_state=True,
        max_result_size_chars=100000,
        activity_kind="state",
        activity_title="Delete schedule",
        activity_target_argument="id",
        result_formatter=format_src_origin_cron_delete_result,
    )
