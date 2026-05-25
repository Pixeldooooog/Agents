from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from agents.kernel.capabilities.sandbox.factory import (
    create_sandbox_client,
    create_sandbox_client_from_profile,
    sandbox_policy_from_settings,
    sandbox_profile_from_settings,
)
from agents.kernel.capabilities.sandbox.local import LocalSandboxProvider
from agents.kernel.capabilities.sandbox.store import SandboxLeaseRecord, SandboxStore
from agents.kernel.capabilities.sandbox.types import SandboxClient, SandboxProfile
from agents.kernel.context.workspace import WorkspaceContext
from agents.kernel.governance import SandboxPolicy
from agents.kernel.hooks import SessionHookRegistry
from agents.kernel.schema import RuntimeEvent
from agents.kernel.state.artifacts import ArtifactBlobLocation, ArtifactBlobStore, ArtifactStore, InMemoryArtifactStore, LocalArtifactBlobStore


@dataclass
class ToolRuntimeContext:
    workspace: WorkspaceContext
    sandbox: SandboxPolicy
    sandbox_client: SandboxClient | None = None
    sandbox_profile: SandboxProfile | None = None
    sandbox_store: SandboxStore | None = None
    artifact_store: ArtifactStore | None = None
    artifact_blob_store: ArtifactBlobStore | None = None
    task_store: Any | None = None
    run_service: Any | None = None
    agent_profile_store: Any | None = None
    memory_store: Any | None = None
    schedule_store: Any | None = None
    team_store: Any | None = None
    hook_store: Any | None = None
    mcp_config_store: Any | None = None
    mcp_auth_store: Any | None = None
    mcp_elicitation_handler: Any | None = None
    sdk_mcp_handlers: dict[str, Any] = field(default_factory=dict)
    mcp_oauth_flows: dict[str, Any] = field(default_factory=dict)
    session_state_store: Any | None = None
    skill_registry: Any | None = None
    mcp_providers: list[Any] = field(default_factory=list)
    lsp_provider: Any | None = None
    settings: Any | None = None
    enabled_tools: list[str] = field(default_factory=list)
    agent_spec: Any | None = None
    file_reading_limits: dict[str, int] = field(default_factory=dict)
    session: Any | None = None
    agent_session_factory: Any | None = None
    subagent_depth: int = 0
    max_subagent_depth: int = 1
    todos: list[dict[str, str]] = field(default_factory=list)
    plan_mode: bool = False
    plan_text: str = ""
    plan_allowed_prompts: list[dict[str, str]] = field(default_factory=list)
    system_prompt_override: str = ""
    system_prompt_overridden: bool = False
    permission_profile_override: str = ""
    permission_mode_override: str = ""
    permission_restrict_allowed_tools: bool = False
    permission_allowed_tools_override: list[str] = field(default_factory=list)
    permission_denied_tools_override: list[str] = field(default_factory=list)
    approval_required_tools_override: list[str] = field(default_factory=list)
    permission_overridden: bool = False
    config_overrides: dict[str, str] = field(default_factory=dict)
    enabled_skills: set[str] = field(default_factory=set)
    enabled_plugins: set[str] = field(default_factory=set)
    skill_tools: dict[str, list[str]] = field(default_factory=dict)
    plugin_tools: dict[str, list[str]] = field(default_factory=dict)
    background_tasks: dict[str, Any] = field(default_factory=dict)
    background_task_results: dict[str, Any] = field(default_factory=dict)
    background_commands: dict[str, Any] = field(default_factory=dict)
    background_command_metadata: dict[str, dict[str, Any]] = field(default_factory=dict)
    active_worktree_session: dict[str, Any] = field(default_factory=dict)
    file_read_state: dict[str, dict[str, Any]] = field(default_factory=dict)
    file_read_listeners: list[Callable[[str, str], None]] = field(default_factory=list)
    sleep_wake_event: Any | None = None
    sleep_wake_check: Callable[[], bool] | None = None
    async_message_enqueue: Callable[[dict[str, Any]], None] | None = None
    dynamic_skill_dirs_checked: set[str] = field(default_factory=set)
    dynamic_skill_dirs: set[str] = field(default_factory=set)
    dynamic_skill_dir_triggers: set[str] = field(default_factory=set)
    conditional_skill_names_activated: set[str] = field(default_factory=set)
    conditional_skill_triggers: dict[str, str] = field(default_factory=dict)
    scheduled_tasks: dict[str, dict[str, Any]] = field(default_factory=dict)
    hook_registry: SessionHookRegistry = field(default_factory=SessionHookRegistry)
    teams: dict[str, Any] = field(default_factory=dict)
    team_messages: list[dict[str, Any]] = field(default_factory=list)
    task_id: str = ""
    current_run_id: str = ""
    current_task_id: str = ""
    current_tool_call_id: str = ""
    current_tool_name: str = ""
    runtime_event_sink: Callable[[RuntimeEvent], None] | None = None
    runtime_event_active: Callable[[], bool] | None = None

    def __post_init__(self) -> None:
        if self.artifact_store is None:
            self.artifact_store = InMemoryArtifactStore()
        if self.artifact_blob_store is None:
            self.artifact_blob_store = LocalArtifactBlobStore.for_cli_workspace(self.workspace.path)
        if self.sandbox_profile is None:
            self.sandbox_profile = SandboxProfile(provider="local")
        if self.sandbox_client is None:
            self.sandbox_client = LocalSandboxProvider().acquire(self.workspace, self.sandbox, self.sandbox_profile)

    @classmethod
    def for_workspace(cls, workspace: WorkspaceContext) -> "ToolRuntimeContext":
        sandbox = SandboxPolicy.for_workspace(workspace.path)
        client = LocalSandboxProvider().acquire(workspace, sandbox)
        return cls(workspace=workspace, sandbox=sandbox, sandbox_client=client)

    @classmethod
    def from_settings(
        cls,
        settings: Any,
        workspace: WorkspaceContext,
        sandbox_store: SandboxStore | None = None,
        artifact_store: ArtifactStore | None = None,
        artifact_blob_store: ArtifactBlobStore | None = None,
        task_store: Any | None = None,
        run_service: Any | None = None,
        agent_profile_store: Any | None = None,
        memory_store: Any | None = None,
        schedule_store: Any | None = None,
        team_store: Any | None = None,
        hook_store: Any | None = None,
        mcp_config_store: Any | None = None,
        mcp_auth_store: Any | None = None,
        mcp_elicitation_handler: Any | None = None,
        sdk_mcp_handlers: dict[str, Any] | None = None,
        session_state_store: Any | None = None,
        skill_registry: Any | None = None,
        agent_spec: Any | None = None,
        agent_session_factory: Any | None = None,
        subagent_depth: int = 0,
        max_subagent_depth: int = 1,
        task_id: str = "",
    ) -> "ToolRuntimeContext":
        profile = sandbox_profile_from_settings(settings)
        sandbox = sandbox_policy_from_settings(settings, workspace, profile)
        client = create_sandbox_client(settings, workspace, sandbox)
        return cls(
            workspace=workspace,
            sandbox=sandbox,
            sandbox_client=client,
            sandbox_profile=profile,
            sandbox_store=sandbox_store,
            artifact_store=artifact_store,
            artifact_blob_store=artifact_blob_store,
            task_store=task_store,
            run_service=run_service,
            agent_profile_store=agent_profile_store,
            memory_store=memory_store,
            schedule_store=schedule_store,
            team_store=team_store,
            hook_store=hook_store,
            mcp_config_store=mcp_config_store,
            mcp_auth_store=mcp_auth_store,
            mcp_elicitation_handler=mcp_elicitation_handler,
            sdk_mcp_handlers=dict(sdk_mcp_handlers or {}),
            session_state_store=session_state_store,
            skill_registry=skill_registry,
            settings=settings,
            agent_spec=agent_spec,
            agent_session_factory=agent_session_factory,
            subagent_depth=subagent_depth,
            max_subagent_depth=max_subagent_depth,
            task_id=str(task_id or ""),
        )

    async def bind_execution_scope(
        self,
        run_id: str = "",
        task_id: str = "",
        tool_call_id: str = "",
        tool_name: str = "",
    ) -> SandboxClient:
        scoped_run_id = str(run_id or "")
        scoped_task_id = str(task_id or self.task_id or "")
        self.current_run_id = scoped_run_id
        self.current_task_id = scoped_task_id
        self.current_tool_call_id = str(tool_call_id or self.current_tool_call_id or "")
        self.current_tool_name = str(tool_name or self.current_tool_name or "")
        if not scoped_run_id:
            return self.sandbox_client
        lease_id = _scoped_lease_id(scoped_run_id, scoped_task_id)
        if self.sandbox_client and self.sandbox_client.lease.lease_id == lease_id:
            return self.sandbox_client
        metadata = {"run_id": scoped_run_id}
        if scoped_task_id:
            metadata["task_id"] = scoped_task_id
        if self.artifact_blob_store is not None:
            artifact_root = self.artifact_blob_store.run_artifact_root(self.workspace, scoped_run_id)
            metadata.update(
                {
                    "artifacts_root": artifact_root.as_posix(),
                    "artifact_host_root": artifact_root.as_posix(),
                    "artifact_mount_path": "/artifacts",
                }
            )
        self.sandbox_client = create_sandbox_client_from_profile(
            self.workspace,
            self.sandbox,
            self.sandbox_profile or SandboxProfile(provider="local"),
            lease_id=lease_id,
            metadata=metadata,
        )
        if self.sandbox_store is not None:
            lease = SandboxLeaseRecord.from_lease(self.sandbox_client.lease)
            await self.sandbox_store.save_lease(lease)
            await self.sandbox_store.record_event(lease.to_event("lease_acquired"))
        return self.sandbox_client

    def allocate_artifact_blob(self, category: str, filename: str, run_id: str = "") -> ArtifactBlobLocation:
        scoped_run_id = str(run_id or self.current_run_id or "manual")
        root = self.artifact_blob_store.run_artifact_root(self.workspace, scoped_run_id)
        lease = getattr(self.sandbox_client, "lease", None)
        metadata = getattr(lease, "metadata", None)
        if isinstance(metadata, dict):
            metadata.update(
                {
                    "artifacts_root": root.as_posix(),
                    "artifact_host_root": root.as_posix(),
                    "artifact_mount_path": "/artifacts",
                }
            )
        return self.artifact_blob_store.allocate(
            self.workspace,
            run_id=scoped_run_id,
            category=category,
            filename=filename,
        )

    def emit_runtime_event(self, event_type: str, *, name: str = "", payload: dict[str, Any] | None = None) -> None:
        sink = self.runtime_event_sink
        if sink is None:
            return
        sink(RuntimeEvent(type=str(event_type or ""), name=str(name or ""), payload=dict(payload or {})))

    def has_runtime_event_sink(self) -> bool:
        active = self.runtime_event_active
        return bool(active and active())

    def artifact_destination_path(self, location: ArtifactBlobLocation) -> str:
        provider = getattr(getattr(self.sandbox_client, "lease", None), "provider", "")
        if provider == "docker":
            return location.sandbox_path
        return location.host_path.as_posix()


def _scoped_lease_id(run_id: str, task_id: str = "") -> str:
    parts = ["sandbox", _safe_token(run_id)]
    if task_id:
        parts.append(_safe_token(task_id))
    return "_".join(parts)


def _safe_token(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("_", "-", ".") else "-" for ch in str(value or "")).strip(".-") or "scope"
