import asyncio
import subprocess
from dataclasses import replace
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


def test_src_origin_agent_alias_rejects_unknown_subagent_type(tmp_path: Path):
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
                "subagent_type": "missing-agent",
            },
        )
    )

    assert result.is_error is True
    assert "Agent type 'missing-agent' not found" in result.content
    assert "Available agents: researcher" in result.content
    assert captured == []


def test_src_origin_agent_alias_uses_general_purpose_profile_by_default(tmp_path: Path):
    profile_store = InMemoryAgentProfileStore()
    context, captured = _agent_context(tmp_path, profile_store=profile_store)
    asyncio.run(
        _save_profile(
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


def test_src_origin_agent_profile_can_force_background_execution(tmp_path: Path):
    profile_store = InMemoryAgentProfileStore()
    task_store = InMemoryTaskStore()
    context, captured = _agent_context(tmp_path, profile_store=profile_store, task_store=task_store)
    asyncio.run(
        _save_profile(
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
    _init_repo(repo)
    profile_store = InMemoryAgentProfileStore()
    context, captured = _agent_context(repo, profile_store=profile_store)
    asyncio.run(
        _save_profile(
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
    context, captured = _agent_context(tmp_path, profile_store=profile_store)
    asyncio.run(
        _save_profile(
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
    context, captured = _agent_context(
        tmp_path,
        profile_store=profile_store,
        enabled_tools=["mcp__github__search"],
    )
    asyncio.run(
        _save_profile(
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
    context, captured = _agent_context(
        tmp_path,
        profile_store=profile_store,
        enabled_tools=["mcp__github__search"],
    )
    asyncio.run(
        _save_profile(
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


async def _save_researcher_profile(profile_store: InMemoryAgentProfileStore, root: Path, *, model: str) -> None:
    await _save_profile(
        profile_store,
        root,
        agent_id="researcher",
        model=model,
        system_prompt="Profile prompt",
    )


async def _save_profile(
    profile_store: InMemoryAgentProfileStore,
    root: Path,
    *,
    agent_id: str,
    model: str,
    system_prompt: str,
    metadata: dict[str, str] | None = None,
) -> None:
    spec = AgentSpec.from_overrides(
        tenant_id="tenant",
        user_id="user",
        agent_id=agent_id,
        workspace_id="workspace",
        workspace_path=str(root),
        model=model,
        system_prompt=system_prompt,
        enabled_tools=["filesystem.read"],
    )
    if metadata:
        spec = replace(spec, metadata=dict(metadata))
    await profile_store.save(AgentProfile.from_spec(spec, name=agent_id))


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True)
    _git(path, "init")
    _git(path, "config", "user.email", "agents-test@example.com")
    _git(path, "config", "user.name", "Agents Test")
    (path / "README.md").write_text("hello\n", encoding="utf-8")
    _git(path, "add", "README.md")
    _git(path, "commit", "-m", "init")


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=str(cwd), text=True, capture_output=True, check=True)


def _agent_context(
    root: Path,
    *,
    profile_store: InMemoryAgentProfileStore,
    task_store: InMemoryTaskStore | None = None,
    enabled_tools: list[str] | None = None,
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
            enabled_tools=list(enabled_tools or []),
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
