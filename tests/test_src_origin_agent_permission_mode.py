import asyncio
from pathlib import Path

import pytest

from agents.kernel.capabilities.tools import register_builtin_tools
from agents.kernel.capabilities.tools.registry import ToolRegistry
from agents.kernel.state import InMemoryAgentProfileStore

from tests.src_origin_agent_helpers import agent_context, save_profile


@pytest.mark.parametrize(
    ("src_origin_mode", "local_mode"),
    [
        ("plan", "ask"),
        ("bubble", "ask"),
        ("acceptEdits", "auto"),
        ("bypassPermissions", "auto"),
        ("dontAsk", "auto"),
    ],
)
def test_src_origin_agent_profile_permission_mode_metadata_applies_to_child_spec(
    tmp_path: Path,
    src_origin_mode: str,
    local_mode: str,
):
    profile_store = InMemoryAgentProfileStore()
    context, captured = agent_context(tmp_path, profile_store=profile_store)
    asyncio.run(
        save_profile(
            profile_store,
            tmp_path,
            agent_id="researcher",
            model="profile-model",
            system_prompt="Profile prompt",
            metadata={"permissionMode": src_origin_mode},
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

    child = captured[0]
    assert result.is_error is False
    assert child.permission_profile == src_origin_mode
    assert child.tool_permissions.mode == local_mode


def test_src_origin_agent_profile_permission_mode_ignores_unknown_metadata(tmp_path: Path):
    profile_store = InMemoryAgentProfileStore()
    context, captured = agent_context(tmp_path, profile_store=profile_store)
    asyncio.run(
        save_profile(
            profile_store,
            tmp_path,
            agent_id="researcher",
            model="profile-model",
            system_prompt="Profile prompt",
            metadata={"permissionMode": "invalid"},
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

    child = captured[0]
    assert result.is_error is False
    assert child.permission_profile == ""
    assert child.tool_permissions.mode == "auto"
