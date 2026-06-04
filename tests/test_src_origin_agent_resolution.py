import asyncio
from pathlib import Path

from agents.kernel.capabilities.tools import register_builtin_tools
from agents.kernel.capabilities.tools.registry import ToolRegistry
from agents.kernel.state import InMemoryAgentProfileStore
from agents.kernel.tasks import InMemoryTaskStore

from tests.src_origin_agent_helpers import (
    agent_context,
    init_repo,
    save_profile,
    save_researcher_profile,
)


def test_src_origin_agent_alias_resolves_profile_and_model_override(tmp_path: Path):
    profile_store = InMemoryAgentProfileStore()
    context, captured = agent_context(tmp_path, profile_store=profile_store)
    asyncio.run(save_researcher_profile(profile_store, tmp_path, model="profile-model"))
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    result = asyncio.run(
        registry.execute(
            "Agent",
            {
                "description": "Inspect repo",
                "prompt": "read files",
                "subagent_type": "researcher",
                "model": "opus",
            },
        )
    )

    child = captured[0]
    assert result.raw["agent_id"] == "researcher"
    assert child.agent_id == "researcher"
    assert child.system_prompt == "Profile prompt"
    assert child.enabled_tools == ["filesystem.read"]
    assert child.model.model == "opus"
    assert child.metadata["parent_agent_id"] == "lead"
    assert child.metadata["src_origin_agent_profile"] == "researcher"


def test_src_origin_agent_alias_keeps_explicit_name_while_using_profile(tmp_path: Path):
    profile_store = InMemoryAgentProfileStore()
    context, captured = agent_context(tmp_path, profile_store=profile_store)
    asyncio.run(save_researcher_profile(profile_store, tmp_path, model="profile-model"))
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    asyncio.run(
        registry.execute(
            "Agent",
            {
                "description": "Inspect repo",
                "prompt": "read files",
                "subagent_type": "researcher",
                "name": "custom-reviewer",
            },
        )
    )

    child = captured[0]
    assert child.agent_id == "custom-reviewer"
    assert child.system_prompt == "Profile prompt"
    assert child.model.model == "profile-model"


def test_src_origin_background_agent_stores_resolved_child_spec(tmp_path: Path):
    profile_store = InMemoryAgentProfileStore()
    task_store = InMemoryTaskStore()
    context, captured = agent_context(tmp_path, profile_store=profile_store, task_store=task_store)
    asyncio.run(save_researcher_profile(profile_store, tmp_path, model="profile-model"))
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    async def execute():
        started = await registry.execute(
            "Agent",
            {
                "description": "Inspect repo",
                "prompt": "read files",
                "subagent_type": "researcher",
                "model": "haiku",
                "run_in_background": True,
            },
        )
        task_id = started.raw["task"]["task_id"]
        await context.background_tasks[task_id]
        return started, await task_store.load_task(task_id)

    started, task = asyncio.run(execute())

    assert started.raw["status"] == "async_launched"
    assert task is not None
    assert task.agent_id == "lead"
    assert task.metadata["agent_id"] == "researcher"
    assert task.spec["agent_id"] == "lead"
    assert task.spec["model"]["model"] == "haiku"
    child = captured[0]
    assert child.agent_id == "researcher"
    assert child.system_prompt == "Profile prompt"
    assert child.enabled_tools == ["filesystem.read"]
    assert child.model.model == "haiku"


def test_src_origin_agent_alias_rejects_unknown_subagent_type(tmp_path: Path):
    profile_store = InMemoryAgentProfileStore()
    context, captured = agent_context(tmp_path, profile_store=profile_store)
    asyncio.run(save_researcher_profile(profile_store, tmp_path, model="profile-model"))
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    result = asyncio.run(
        registry.execute(
            "Agent",
            {
                "description": "Inspect repo",
                "prompt": "read files",
                "subagent_type": "missing-agent",
            },
        )
    )

    assert result.is_error is True
    assert "Agent type 'missing-agent' not found" in result.content
    assert "Available agents: general-purpose, researcher" in result.content
    assert captured == []


def test_src_origin_agent_alias_uses_general_purpose_profile_by_default(tmp_path: Path):
    profile_store = InMemoryAgentProfileStore()
    context, captured = agent_context(tmp_path, profile_store=profile_store)
    asyncio.run(
        save_profile(
            profile_store,
            tmp_path,
            agent_id="general-purpose",
            model="default-model",
            system_prompt="General prompt",
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
            },
        )
    )

    child = captured[0]
    assert result.raw["agent_id"] == "general-purpose"
    assert child.agent_id == "general-purpose"
    assert child.system_prompt == "General prompt"
    assert child.model.model == "default-model"


def test_src_origin_agent_alias_uses_builtin_general_purpose_by_default(tmp_path: Path):
    profile_store = InMemoryAgentProfileStore()
    context, captured = agent_context(tmp_path, profile_store=profile_store)
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    result = asyncio.run(
        registry.execute(
            "Agent",
            {
                "description": "Inspect repo",
                "prompt": "read files",
            },
        )
    )

    child = captured[0]
    assert result.raw["agent_id"] == "general-purpose"
    assert child.agent_id == "general-purpose"
    assert child.enabled_tools is None
    assert child.metadata["src_origin_agent_profile"] == "general-purpose"
    assert "Searching for code" in (child.system_prompt or "")


def test_src_origin_agent_profile_can_force_background_execution(tmp_path: Path):
    profile_store = InMemoryAgentProfileStore()
    task_store = InMemoryTaskStore()
    context, captured = agent_context(tmp_path, profile_store=profile_store, task_store=task_store)
    asyncio.run(
        save_profile(
            profile_store,
            tmp_path,
            agent_id="researcher",
            model="profile-model",
            system_prompt="Profile prompt",
            metadata={"background": "true"},
        )
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    async def execute():
        started = await registry.execute(
            "Agent",
            {
                "description": "Inspect repo",
                "prompt": "read files",
                "subagent_type": "researcher",
            },
        )
        task_id = started.raw["task"]["task_id"]
        await context.background_tasks[task_id]
        return started, await task_store.load_task(task_id)

    started, task = asyncio.run(execute())

    assert started.raw["status"] == "async_launched"
    assert task is not None
    assert task.metadata["agent_id"] == "researcher"
    assert captured[0].agent_id == "researcher"


def test_src_origin_agent_profile_can_default_worktree_isolation(tmp_path: Path):
    repo = tmp_path / "repo"
    init_repo(repo)
    profile_store = InMemoryAgentProfileStore()
    context, captured = agent_context(repo, profile_store=profile_store)
    asyncio.run(
        save_profile(
            profile_store,
            repo,
            agent_id="researcher",
            model="profile-model",
            system_prompt="Profile prompt",
            metadata={"isolation": "worktree"},
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

    child_path = Path(captured[0].workspace.path)
    assert result.raw["worktreeKept"] is False
    assert child_path.parent == repo / ".agents" / "worktrees"
    assert child_path.exists() is False


def test_src_origin_agent_profile_applies_max_turns_metadata(tmp_path: Path):
    profile_store = InMemoryAgentProfileStore()
    context, captured = agent_context(tmp_path, profile_store=profile_store)
    asyncio.run(
        save_profile(
            profile_store,
            tmp_path,
            agent_id="researcher",
            model="profile-model",
            system_prompt="Profile prompt",
            metadata={"maxTurns": "2"},
        )
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    asyncio.run(
        registry.execute(
            "Agent",
            {
                "description": "Inspect repo",
                "prompt": "read files",
                "subagent_type": "researcher",
            },
        )
    )

    assert captured[0].metadata["max_tool_iterations"] == "2"
    assert captured[0].metadata["src_origin_max_turns"] == "2"


def test_src_origin_agent_profile_rejects_missing_required_mcp_server(tmp_path: Path):
    profile_store = InMemoryAgentProfileStore()
    context, captured = agent_context(
        tmp_path,
        profile_store=profile_store,
        enabled_tools=["mcp__github__search"],
    )
    asyncio.run(
        save_profile(
            profile_store,
            tmp_path,
            agent_id="researcher",
            model="profile-model",
            system_prompt="Profile prompt",
            metadata={"requiredMcpServers": "docs, github"},
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

    assert result.is_error is True
    assert "requires MCP servers matching: docs" in result.content
    assert "MCP servers with tools: github" in result.content
    assert captured == []


def test_src_origin_agent_profile_accepts_required_mcp_server_with_tools(tmp_path: Path):
    profile_store = InMemoryAgentProfileStore()
    context, captured = agent_context(
        tmp_path,
        profile_store=profile_store,
        enabled_tools=["mcp__github__search"],
    )
    asyncio.run(
        save_profile(
            profile_store,
            tmp_path,
            agent_id="researcher",
            model="profile-model",
            system_prompt="Profile prompt",
            metadata={"requiredMcpServers": "hub"},
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
    assert captured[0].agent_id == "researcher"
