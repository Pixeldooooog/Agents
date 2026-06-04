import asyncio
from pathlib import Path

from agents.kernel.capabilities.tools import register_builtin_tools
from agents.kernel.capabilities.tools.registry import ToolRegistry
from agents.kernel.state import InMemoryAgentProfileStore

from tests.src_origin_agent_helpers import agent_context, save_profile


def test_src_origin_agent_profile_critical_system_reminder_metadata(tmp_path: Path):
    profile_store = InMemoryAgentProfileStore()
    context, captured = agent_context(tmp_path, profile_store=profile_store)
    asyncio.run(
        save_profile(
            profile_store,
            tmp_path,
            agent_id="verification",
            model="inherit",
            system_prompt="Verify only.",
            metadata={
                "criticalSystemReminder_EXPERIMENTAL": "VERDICT required. Do not edit project files.",
            },
        )
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    result = asyncio.run(
        registry.execute(
            "Agent",
            {
                "description": "Verify changes",
                "prompt": "check repo",
                "subagent_type": "verification",
            },
        )
    )

    assert result.is_error is False
    assert captured[0].metadata["critical_system_reminder"] == "VERDICT required. Do not edit project files."
    assert captured[0].metadata["src_origin_critical_system_reminder"] == "true"
