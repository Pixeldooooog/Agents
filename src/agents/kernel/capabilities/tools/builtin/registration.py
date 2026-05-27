from __future__ import annotations

from agents.kernel.capabilities.tools.builtin.execution_registration import register_execution_tools
from agents.kernel.capabilities.tools.builtin.extension_registration import (
    register_command_and_extension_tools,
    register_prompt_template_tools,
)
from agents.kernel.capabilities.tools.builtin.interaction_registration import register_interaction_tools
from agents.kernel.capabilities.tools.builtin.mcp.registration import register_mcp_builtin_tools
from agents.kernel.capabilities.tools.builtin.src_origin_aliases import register_src_origin_aliases
from agents.kernel.capabilities.tools.builtin.state_registration import register_state_tools
from agents.kernel.capabilities.tools.builtin.tool_names import BUILTIN_TOOL_NAMES
from agents.kernel.capabilities.tools.builtin.web_registration import register_web_tools
from agents.kernel.capabilities.tools.builtin.workspace_registration import (
    register_workspace_file_tools,
    register_worktree_tools,
)
from agents.kernel.capabilities.tools.context import ToolRuntimeContext
from agents.kernel.capabilities.tools.registry import ToolRegistry
from agents.kernel.capabilities.web import NullWebSearchProvider, WebSearchProvider


def register_builtin_tools(
    registry: ToolRegistry,
    context: ToolRuntimeContext,
    web_provider: WebSearchProvider | None = None,
) -> list[str]:
    context.runtime_event_sink = registry.emit_runtime_event
    context.runtime_event_active = registry.has_runtime_event_sink
    active_web_provider = web_provider or NullWebSearchProvider()

    register_workspace_file_tools(registry, context)
    register_interaction_tools(registry, context)
    register_worktree_tools(registry, context)
    register_src_origin_aliases(registry, context, active_web_provider)
    register_command_and_extension_tools(registry, context)
    register_mcp_builtin_tools(registry, context)
    register_prompt_template_tools(registry, context)
    register_state_tools(registry, context)
    register_web_tools(registry, context, active_web_provider)
    register_execution_tools(registry, context)
    return list(BUILTIN_TOOL_NAMES)
