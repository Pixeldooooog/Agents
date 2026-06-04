import asyncio
from pathlib import Path

from agents.kernel.capabilities.tools import register_builtin_tools
from agents.kernel.capabilities.tools.registry import ToolRegistry
from agents.kernel.state import InMemoryAgentProfileStore

from tests.src_origin_agent_helpers import agent_context, save_profile


def test_src_origin_agent_profile_memory_scope_marks_child_spec(tmp_path: Path):
    profile_store = InMemoryAgentProfileStore()
    context, captured = agent_context(tmp_path, profile_store=profile_store)
    asyncio.run(
        save_profile(
            profile_store,
            tmp_path,
            agent_id="researcher",
            model="inherit",
            system_prompt="Research only.",
            metadata={"memory": "user"},
        )
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    result = asyncio.run(
        registry.execute(
            "Agent",
            {
                "description": "Inspect repo",
                "prompt": "read files",
                "subagent_type": "researcher",
            },
        )
    )

    assert result.is_error is False
    assert captured[0].memory_profile == "src-origin:user"
    assert captured[0].metadata["src_origin_memory_scope"] == "user"
