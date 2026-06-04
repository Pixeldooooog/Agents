from __future__ import annotations

from dataclasses import replace

from agents.kernel.capabilities.tools.context import ToolRuntimeContext
from agents.kernel.capabilities.tools.builtin.src_origin.agent_builtin_prompts import (
    EXPLORE_SYSTEM_PROMPT,
    GENERAL_PURPOSE_SYSTEM_PROMPT,
    PLAN_SYSTEM_PROMPT,
)
from agents.kernel.specs import AgentSpec
from agents.kernel.state import AgentProfile


GENERAL_PURPOSE_AGENT_ID = "general-purpose"
EXPLORE_AGENT_ID = "Explore"
PLAN_AGENT_ID = "Plan"
SRC_ORIGIN_BUILTIN_AGENT_IDS = (EXPLORE_AGENT_ID, GENERAL_PURPOSE_AGENT_ID, PLAN_AGENT_ID)
READ_ONLY_DENIED_TOOLS = ("Agent", "Task", "ExitPlanMode", "Edit", "Write", "NotebookEdit")
READ_ONLY_DENIED_TOOLS_VALUE = ", ".join(READ_ONLY_DENIED_TOOLS)


def src_origin_builtin_agent_ids() -> tuple[str, ...]:
    return SRC_ORIGIN_BUILTIN_AGENT_IDS


def src_origin_builtin_agent_profile(
    context: ToolRuntimeContext,
    base: AgentSpec,
    agent_id: str,
) -> AgentProfile | None:
    definition = _BUILTIN_DEFINITIONS.get(_agent_key(agent_id))
    if definition is None:
        return None
    profile_id, prompt, model, metadata = definition
    spec = AgentSpec.from_overrides(
        tenant_id=base.workspace.tenant_id or context.workspace.tenant_id,
        user_id=base.workspace.user_id or context.workspace.user_id,
        agent_id=profile_id,
        workspace_id=base.workspace.workspace_id or context.workspace.workspace_id,
        workspace_path=base.workspace.path or str(context.workspace.path),
        model=model,
        system_prompt=prompt,
        enabled_tools=None,
    )
    spec = replace(
        spec,
        metadata={
            "src_origin_builtin_agent": "true",
            **metadata,
        },
    )
    return AgentProfile.from_spec(spec, name=profile_id)


def _agent_key(value: str) -> str:
    return str(value or "").strip().lower()


_BUILTIN_DEFINITIONS = {
    _agent_key(GENERAL_PURPOSE_AGENT_ID): (
        GENERAL_PURPOSE_AGENT_ID,
        GENERAL_PURPOSE_SYSTEM_PROMPT,
        None,
        {"tools": "*"},
    ),
    _agent_key(EXPLORE_AGENT_ID): (
        EXPLORE_AGENT_ID,
        EXPLORE_SYSTEM_PROMPT,
        "haiku",
        {
            "disallowedTools": READ_ONLY_DENIED_TOOLS_VALUE,
            "omitClaudeMd": "true",
        },
    ),
    _agent_key(PLAN_AGENT_ID): (
        PLAN_AGENT_ID,
        PLAN_SYSTEM_PROMPT,
        None,
        {
            "disallowedTools": READ_ONLY_DENIED_TOOLS_VALUE,
            "omitClaudeMd": "true",
        },
    ),
}
