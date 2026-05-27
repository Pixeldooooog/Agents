"""Registration orchestrator for src-origin compatibility aliases."""

from __future__ import annotations

from agents.kernel.capabilities.tools.builtin.src_origin_agent_aliases import register_src_origin_agent_aliases
from agents.kernel.capabilities.tools.builtin.src_origin_core_aliases import register_src_origin_core_aliases
from agents.kernel.capabilities.tools.builtin.src_origin_discovery_aliases import register_src_origin_discovery_aliases
from agents.kernel.capabilities.tools.builtin.src_origin_plan_aliases import register_src_origin_plan_aliases
from agents.kernel.capabilities.tools.builtin.src_origin_schedule_aliases import register_src_origin_schedule_aliases
from agents.kernel.capabilities.tools.builtin.src_origin_session_aliases import register_src_origin_session_aliases
from agents.kernel.capabilities.tools.builtin.src_origin_task_aliases import register_src_origin_task_aliases
from agents.kernel.capabilities.tools.context import ToolRuntimeContext
from agents.kernel.capabilities.tools.registry import ToolRegistry
from agents.kernel.capabilities.web import WebSearchProvider


def register_src_origin_aliases(
    registry: ToolRegistry,
    context: ToolRuntimeContext,
    active_web_provider: WebSearchProvider,
) -> None:
    register_src_origin_core_aliases(registry, context)
    register_src_origin_discovery_aliases(registry, context, active_web_provider)
    register_src_origin_task_aliases(registry, context)
    register_src_origin_schedule_aliases(registry, context)
    register_src_origin_plan_aliases(registry, context)
    register_src_origin_agent_aliases(registry, context)
    register_src_origin_session_aliases(registry, context)
