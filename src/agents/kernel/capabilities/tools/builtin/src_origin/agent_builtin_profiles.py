from __future__ import annotations

from dataclasses import replace

from agents.kernel.capabilities.tools.context import ToolRuntimeContext
from agents.kernel.specs import AgentSpec
from agents.kernel.state import AgentProfile


GENERAL_PURPOSE_AGENT_ID = "general-purpose"
SRC_ORIGIN_BUILTIN_AGENT_IDS = (GENERAL_PURPOSE_AGENT_ID,)

GENERAL_PURPOSE_SYSTEM_PROMPT = """You are an agent for Claude Code, Anthropic's official CLI for Claude. Given the user's message, use the tools available to complete the task. Complete the task fully without gold-plating or leaving it half-done.

Your strengths:
- Searching for code, configurations, and patterns across large codebases
- Analyzing multiple files to understand system architecture
- Investigating complex questions that require exploring many files
- Performing multi-step research tasks

Guidelines:
- For file searches, search broadly when you do not know where something lives. Use Read when you know the specific file path.
- For analysis, start broad and narrow down. Use multiple search strategies if the first does not yield results.
- Be thorough: check multiple locations, consider different naming conventions, and look for related files.
- Never create files unless they are absolutely necessary for achieving the goal. Prefer editing an existing file.
- Never proactively create documentation files. Only create documentation files if explicitly requested.

When you complete the task, respond with a concise report covering what was done and any key findings."""


def src_origin_builtin_agent_ids() -> tuple[str, ...]:
    return SRC_ORIGIN_BUILTIN_AGENT_IDS


def src_origin_builtin_agent_profile(
    context: ToolRuntimeContext,
    base: AgentSpec,
    agent_id: str,
) -> AgentProfile | None:
    if _agent_key(agent_id) != GENERAL_PURPOSE_AGENT_ID:
        return None
    spec = AgentSpec.from_overrides(
        tenant_id=base.workspace.tenant_id or context.workspace.tenant_id,
        user_id=base.workspace.user_id or context.workspace.user_id,
        agent_id=GENERAL_PURPOSE_AGENT_ID,
        workspace_id=base.workspace.workspace_id or context.workspace.workspace_id,
        workspace_path=base.workspace.path or str(context.workspace.path),
        system_prompt=GENERAL_PURPOSE_SYSTEM_PROMPT,
        enabled_tools=None,
    )
    spec = replace(
        spec,
        metadata={
            "src_origin_builtin_agent": "true",
            "tools": "*",
        },
    )
    return AgentProfile.from_spec(spec, name=GENERAL_PURPOSE_AGENT_ID)


def _agent_key(value: str) -> str:
    return str(value or "").strip().lower()
