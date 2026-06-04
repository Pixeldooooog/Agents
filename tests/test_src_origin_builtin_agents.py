import asyncio
from dataclasses import replace
from pathlib import Path

from agents.kernel.capabilities.tools import register_builtin_tools
from agents.kernel.capabilities.tools.registry import ToolRegistry
from agents.kernel.specs import AgentSpec
from agents.kernel.state import InMemoryAgentProfileStore

from tests.src_origin_agent_helpers import agent_context


READ_ONLY_DENIED_TOOLS = ["Agent", "Task", "ExitPlanMode", "Edit", "Write", "NotebookEdit"]


def test_src_origin_agent_alias_uses_builtin_general_purpose_by_default(tmp_path: Path):
    result, child = _spawn_builtin(tmp_path, "")

    assert result.raw["agent_id"] == "general-purpose"
    assert child.agent_id == "general-purpose"
    assert child.enabled_tools is None
    assert child.metadata["src_origin_agent_profile"] == "general-purpose"
    assert "Searching for code" in (child.system_prompt or "")


def test_src_origin_agent_alias_resolves_builtin_explore_profile(tmp_path: Path):
    result, child = _spawn_builtin(tmp_path, "Explore")

    assert result.raw["agent_id"] == "Explore"
    assert child.agent_id == "Explore"
    assert child.enabled_tools is None
    assert child.model.model == "haiku"
    assert child.tool_permissions.denied_tools == READ_ONLY_DENIED_TOOLS
    assert child.metadata["omit_workspace_instructions"] == "true"
    assert "READ-ONLY exploration task" in (child.system_prompt or "")


def test_src_origin_agent_alias_resolves_builtin_without_profile_store(tmp_path: Path):
    result, child = _spawn_builtin(tmp_path, "Explore", include_profile_store=False)

    assert result.raw["agent_id"] == "Explore"
    assert child.agent_id == "Explore"
    assert child.model.model == "haiku"
    assert child.tool_permissions.denied_tools == READ_ONLY_DENIED_TOOLS
    assert "READ-ONLY exploration task" in (child.system_prompt or "")


def test_src_origin_agent_alias_resolves_builtin_plan_profile_with_inherited_model(tmp_path: Path):
    result, child = _spawn_builtin(tmp_path, "Plan", parent_model="parent-model")

    assert result.raw["agent_id"] == "Plan"
    assert child.agent_id == "Plan"
    assert child.enabled_tools is None
    assert child.model.model == "parent-model"
    assert child.tool_permissions.denied_tools == READ_ONLY_DENIED_TOOLS
    assert child.metadata["omit_workspace_instructions"] == "true"
    assert "Critical Files for Implementation" in (child.system_prompt or "")


def _spawn_builtin(
    tmp_path: Path,
    subagent_type: str,
    *,
    parent_model: str = "",
    include_profile_store: bool = True,
):
    profile_store = InMemoryAgentProfileStore()
    context, captured = agent_context(tmp_path, profile_store=profile_store)
    if not include_profile_store:
        context.agent_profile_store = None
    if parent_model:
        context.agent_spec = replace(context.agent_spec, model=AgentSpec.from_overrides(model=parent_model).model)
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    result = asyncio.run(
        registry.execute(
            "Agent",
            {
                "description": "Inspect repo",
                "prompt": "read files",
                "subagent_type": subagent_type,
            },
        )
    )

    assert result.is_error is False
    return result, captured[0]
