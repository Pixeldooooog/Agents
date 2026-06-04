import asyncio
from pathlib import Path

from agents.kernel.capabilities.tools import register_builtin_tools
from agents.kernel.capabilities.tools.registry import ToolRegistry
from agents.kernel.state import InMemoryAgentProfileStore

from tests.src_origin_agent_helpers import agent_context, save_profile


def test_src_origin_agent_profile_omit_claude_md_marks_child_spec_context_options(
    tmp_path: Path,
):
    profile_store = InMemoryAgentProfileStore()
    context, captured = agent_context(tmp_path, profile_store=profile_store)
    asyncio.run(
        save_profile(
            profile_store,
            tmp_path,
            agent_id="explore",
            model="inherit",
            system_prompt="Explore only.",
            metadata={"omitClaudeMd": "true"},
        )
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    result = asyncio.run(
        registry.execute(
            "Agent",
            {
                "description": "Explore repo",
                "prompt": "inspect only",
                "subagent_type": "explore",
            },
        )
    )

    assert result.is_error is False
    assert captured[0].metadata["omit_workspace_instructions"] == "true"
    assert captured[0].metadata["src_origin_omit_claude_md"] == "true"
