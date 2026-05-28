from __future__ import annotations

import subprocess
from dataclasses import replace
from pathlib import Path

from agents.kernel.capabilities.sandbox.local import LocalSandboxProvider
from agents.kernel.capabilities.tools import ToolRuntimeContext
from agents.kernel.context.workspace import WorkspaceContext
from agents.kernel.governance import SandboxPolicy
from agents.kernel.runtime import AgentResult
from agents.kernel.schema import Message
from agents.kernel.specs import AgentSpec
from agents.kernel.state import AgentProfile, InMemoryAgentProfileStore
from agents.kernel.tasks import InMemoryTaskStore


async def save_researcher_profile(profile_store: InMemoryAgentProfileStore, root: Path, *, model: str) -> None:
    await save_profile(
        profile_store,
        root,
        agent_id="researcher",
        model=model,
        system_prompt="Profile prompt",
    )


async def save_profile(
    profile_store: InMemoryAgentProfileStore,
    root: Path,
    *,
    agent_id: str,
    model: str,
    system_prompt: str,
    enabled_tools: list[str] | None = None,
    denied_tools: list[str] | None = None,
    skills: list[str] | None = None,
    metadata: dict[str, object] | None = None,
) -> None:
    spec = AgentSpec.from_overrides(
        tenant_id="tenant",
        user_id="user",
        agent_id=agent_id,
        workspace_id="workspace",
        workspace_path=str(root),
        model=model,
        system_prompt=system_prompt,
        enabled_tools=["filesystem.read"] if enabled_tools is None else list(enabled_tools),
        skills=skills,
        denied_tools=denied_tools,
    )
    if metadata:
        spec = replace(spec, metadata=dict(metadata))
    await profile_store.save(AgentProfile.from_spec(spec, name=agent_id))


def init_repo(path: Path) -> None:
    path.mkdir(parents=True)
    _git(path, "init")
    _git(path, "config", "user.email", "agents-test@example.com")
    _git(path, "config", "user.name", "Agents Test")
    (path / "README.md").write_text("hello\n", encoding="utf-8")
    _git(path, "add", "README.md")
    _git(path, "commit", "-m", "init")


def agent_context(
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


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=str(cwd), text=True, capture_output=True, check=True)
