import asyncio
from pathlib import Path

from agents.kernel.capabilities.sandbox.local import LocalSandboxProvider
from agents.kernel.capabilities.tools import ToolRuntimeContext, register_builtin_tools
from agents.kernel.capabilities.tools.registry import ToolRegistry
from agents.kernel.context.workspace import WorkspaceContext
from agents.kernel.governance import SandboxPolicy
from agents.kernel.runtime import AgentResult
from agents.kernel.schema import Message
from agents.kernel.specs import AgentSpec
from agents.kernel.state import AgentProfile, InMemoryAgentProfileStore
from agents.kernel.tasks import InMemoryTaskStore


def test_src_origin_agent_alias_resolves_profile_and_model_override(tmp_path: Path):
    profile_store = InMemoryAgentProfileStore()
    context, captured = _agent_context(tmp_path, profile_store=profile_store)
    asyncio.run(_save_researcher_profile(profile_store, tmp_path, model="profile-model"))
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
    context, captured = _agent_context(tmp_path, profile_store=profile_store)
    asyncio.run(_save_researcher_profile(profile_store, tmp_path, model="profile-model"))
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
    context, captured = _agent_context(tmp_path, profile_store=profile_store, task_store=task_store)
    asyncio.run(_save_researcher_profile(profile_store, tmp_path, model="profile-model"))
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


async def _save_researcher_profile(profile_store: InMemoryAgentProfileStore, root: Path, *, model: str) -> None:
    spec = AgentSpec.from_overrides(
        tenant_id="tenant",
        user_id="user",
        agent_id="researcher",
        workspace_id="workspace",
        workspace_path=str(root),
        model=model,
        system_prompt="Profile prompt",
        enabled_tools=["filesystem.read"],
    )
    await profile_store.save(AgentProfile.from_spec(spec, name="Researcher"))


def _agent_context(
    root: Path,
    *,
    profile_store: InMemoryAgentProfileStore,
    task_store: InMemoryTaskStore | None = None,
) -> tuple[ToolRuntimeContext, list[AgentSpec]]:
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="lead",
        workspace_id="workspace",
        root=root,
        path=root,
    )
    policy = SandboxPolicy.for_workspace(workspace.path)
    captured: list[AgentSpec] = []

    class ChildSession:
        async def send(self, prompt, run_id=None, task_id=None):
            return AgentResult(content="done: %s" % prompt, messages=[Message.from_text("assistant", "done")])

    async def create_child(spec, task_id=""):
        captured.append(spec)
        return ChildSession()

    return (
        ToolRuntimeContext(
            workspace=workspace,
            sandbox=policy,
            sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
            task_store=task_store,
            agent_profile_store=profile_store,
            agent_spec=AgentSpec.from_overrides(
                tenant_id="tenant",
                user_id="user",
                agent_id="lead",
                workspace_id="workspace",
                workspace_path=str(root),
            ),
            agent_session_factory=create_child,
        ),
        captured,
    )
