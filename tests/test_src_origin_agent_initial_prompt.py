import asyncio
from pathlib import Path

from agents.kernel.capabilities.tools import register_builtin_tools
from agents.kernel.capabilities.tools.registry import ToolRegistry
from agents.kernel.state import InMemoryAgentProfileStore
from agents.kernel.tasks import InMemoryTaskStore

from tests.src_origin_agent_helpers import agent_context, save_profile


def test_src_origin_agent_profile_initial_prompt_prepends_sync_agent_prompt(tmp_path: Path):
    profile_store = InMemoryAgentProfileStore()
    context, captured = agent_context(tmp_path, profile_store=profile_store)
    asyncio.run(
        save_profile(
            profile_store,
            tmp_path,
            agent_id="researcher",
            model="inherit",
            system_prompt="Research only.",
            metadata={"initialPrompt": "First inspect the local repo state."},
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

    assert result.raw["content"] == "done: First inspect the local repo state.\n\nread files"
    assert captured[0].metadata["initial_prompt"] == "First inspect the local repo state."
    assert captured[0].metadata["src_origin_initial_prompt"] == "true"


def test_src_origin_agent_profile_initial_prompt_prepends_background_task_input(tmp_path: Path):
    profile_store = InMemoryAgentProfileStore()
    task_store = InMemoryTaskStore()
    context, _captured = agent_context(tmp_path, profile_store=profile_store, task_store=task_store)
    asyncio.run(
        save_profile(
            profile_store,
            tmp_path,
            agent_id="researcher",
            model="inherit",
            system_prompt="Research only.",
            metadata={"initialPrompt": "First inspect the local repo state."},
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
                "run_in_background": True,
            },
        )
        task_id = started.raw["task"]["task_id"]
        await context.background_tasks[task_id]
        return started, await task_store.load_task(task_id)

    started, task = asyncio.run(execute())

    assert started.raw["prompt"] == "First inspect the local repo state.\n\nread files"
    assert task is not None
    assert task.input == "First inspect the local repo state.\n\nread files"
