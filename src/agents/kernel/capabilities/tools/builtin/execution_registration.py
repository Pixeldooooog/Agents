from __future__ import annotations

from agents.kernel.capabilities.tools.builtin.automation_registration import register_automation_tools
from agents.kernel.capabilities.tools.builtin.collaboration_registration import register_collaboration_tools
from agents.kernel.capabilities.tools.builtin.development_registration import register_development_tools
from agents.kernel.capabilities.tools.builtin.runtime_registration import register_runtime_tools
from agents.kernel.capabilities.tools.context import ToolRuntimeContext
from agents.kernel.capabilities.tools.registry import ToolRegistry


def register_execution_tools(registry: ToolRegistry, context: ToolRuntimeContext) -> None:
    register_development_tools(registry, context)
    register_automation_tools(registry, context)
    register_runtime_tools(registry, context)
    register_collaboration_tools(registry, context)
