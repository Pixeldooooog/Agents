import asyncio
from pathlib import Path

from agents.kernel.capabilities.tools import register_builtin_tools
from agents.kernel.capabilities.tools.registry import ToolRegistry
from agents.kernel.state import InMemoryAgentProfileStore

from tests.src_origin_agent_helpers import agent_context, save_profile


def test_src_origin_agent_profile_tools_metadata_overrides_enabled_tools(tmp_path: Path):
    profile_store = InMemoryAgentProfileStore()
    context, captured = agent_context(tmp_path, profile_store=profile_store)
    asyncio.run(
        save_profile(
            profile_store,
            tmp_path,
            agent_id="researcher",
            model="profile-model",
            system_prompt="Profile prompt",
            metadata={"tools": "Read Bash(git status) WebSearch"},
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
    assert captured[0].enabled_tools == ["filesystem.read", "shell.run", "web.search"]


def test_src_origin_agent_profile_tools_wildcard_allows_all_tools(tmp_path: Path):
    profile_store = InMemoryAgentProfileStore()
    context, captured = agent_context(tmp_path, profile_store=profile_store)
    asyncio.run(
        save_profile(
            profile_store,
            tmp_path,
            agent_id="researcher",
            model="profile-model",
            system_prompt="Profile prompt",
            metadata={"tools": "*"},
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
    assert captured[0].enabled_tools is None


def test_src_origin_agent_profile_disallowed_tools_merge_denied_rules(tmp_path: Path):
    profile_store = InMemoryAgentProfileStore()
    context, captured = agent_context(tmp_path, profile_store=profile_store)
    asyncio.run(
        save_profile(
            profile_store,
            tmp_path,
            agent_id="researcher",
            model="profile-model",
            system_prompt="Profile prompt",
            denied_tools=["Read"],
            metadata={"disallowedTools": "Bash(git status), Write"},
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
    assert captured[0].tool_permissions.denied_tools == ["Read", "Bash(git status)", "Write"]
