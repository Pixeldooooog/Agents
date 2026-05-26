from __future__ import annotations

from agents.kernel.capabilities.tools.builtin.planning import (
    SRC_ORIGIN_PLAN_ENTER_SCHEMA,
    SRC_ORIGIN_PLAN_EXIT_SCHEMA,
    format_src_origin_plan_enter_result,
    format_src_origin_plan_exit_result,
    src_origin_plan_enter,
    src_origin_plan_exit,
)
from agents.kernel.capabilities.tools.builtin.registration_helpers import register_builtin_tool
from agents.kernel.capabilities.tools.context import ToolRuntimeContext
from agents.kernel.capabilities.tools.registry import ToolRegistry


def register_src_origin_plan_aliases(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    register_builtin_tool(
        registry,
        name="EnterPlanMode",
        description="Enter plan mode. src-origin alias for plan.enter.",
        parameters=SRC_ORIGIN_PLAN_ENTER_SCHEMA,
        handler=lambda: src_origin_plan_enter(context),
        metadata={
            "risk": "low",
            "writes_state": True,
            "defer": True,
            "alias_of": "plan.enter",
            "src_origin_tool": "EnterPlanMode",
        },
        writes_state=True,
        max_result_size_chars=100000,
        activity_kind="state",
        activity_title="Enter plan mode",
        result_formatter=format_src_origin_plan_enter_result,
    )
    register_builtin_tool(
        registry,
        name="ExitPlanMode",
        description="Exit plan mode with a concrete plan. src-origin alias for plan.exit.",
        parameters=SRC_ORIGIN_PLAN_EXIT_SCHEMA,
        handler=lambda plan, allowedPrompts=None, planFilePath=None: src_origin_plan_exit(
            context,
            plan=plan,
            allowedPrompts=allowedPrompts,
            planFilePath=planFilePath,
        ),
        metadata={
            "risk": "medium",
            "writes_state": True,
            "requires_approval": True,
            "defer": True,
            "alias_of": "plan.exit",
            "src_origin_tool": "ExitPlanMode",
        },
        writes_state=True,
        max_result_size_chars=100000,
        activity_kind="state",
        activity_title="Exit plan mode",
        activity_target_argument="plan",
        result_formatter=format_src_origin_plan_exit_result,
    )
