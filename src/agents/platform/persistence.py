from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agents.kernel.capabilities.sandbox import SandboxStore
from agents.kernel.governance.audit import ApprovalAuditStore
from agents.kernel.capabilities.memory import MemoryStore
from agents.kernel.runtime import CheckpointStore
from agents.kernel.governance import CredentialRefStore
from agents.kernel.state import (
    AgentProfileStore,
    ArtifactBlobStore,
    ArtifactStore,
    IdentityStore,
    LocalArtifactBlobStore,
    RunStore,
    WorkspaceStore,
)
from agents.kernel.tasks import TaskStore
from agents.kernel.governance.tracing import TraceStore
from agents.platform.sessions import (
    create_agent_profile_store,
    create_approval_audit_store,
    create_artifact_store,
    create_checkpoint_store,
    create_credential_ref_store,
    create_identity_store,
    create_memory_store,
    create_run_store,
    create_sandbox_store,
    create_task_store,
    create_trace_store,
    create_workspace_store,
)


@dataclass(frozen=True)
class PlatformPersistence:
    runs: RunStore
    checkpoints: CheckpointStore
    traces: TraceStore
    approval_audit: ApprovalAuditStore
    identities: IdentityStore
    agent_profiles: AgentProfileStore
    workspaces: WorkspaceStore
    artifacts: ArtifactStore
    artifact_blobs: ArtifactBlobStore
    memories: MemoryStore
    credentials: CredentialRefStore
    tasks: TaskStore
    sandboxes: SandboxStore


def create_platform_persistence(settings: Any) -> PlatformPersistence:
    store_kind = str(getattr(settings.agent, "RUN_STORE", "memory") or "memory").strip().lower()
    return _create_persistence(settings, store_kind=store_kind, durable_artifacts=store_kind == "sqlite")


def create_ephemeral_persistence(settings: Any, *, workspace_path: str = "") -> PlatformPersistence:
    return _create_persistence(settings, store_kind="memory", durable_artifacts=False, workspace_path=workspace_path)


def create_durable_persistence(settings: Any) -> PlatformPersistence:
    return _create_persistence(settings, store_kind="sqlite", durable_artifacts=True)


def _create_persistence(
    settings: Any,
    *,
    store_kind: str,
    durable_artifacts: bool,
    workspace_path: str = "",
) -> PlatformPersistence:
    return PlatformPersistence(
        runs=create_run_store(settings, store_kind=store_kind),
        checkpoints=create_checkpoint_store(settings, store_kind=store_kind),
        traces=create_trace_store(settings, store_kind=store_kind),
        approval_audit=create_approval_audit_store(settings, store_kind=store_kind),
        identities=create_identity_store(settings, store_kind=store_kind),
        agent_profiles=create_agent_profile_store(settings, store_kind=store_kind),
        workspaces=create_workspace_store(settings, store_kind=store_kind),
        artifacts=create_artifact_store(settings, store_kind=store_kind),
        artifact_blobs=_create_artifact_blob_store(settings, durable=durable_artifacts, workspace_path=workspace_path),
        memories=create_memory_store(settings, store_kind=store_kind),
        credentials=create_credential_ref_store(settings, store_kind=store_kind),
        tasks=create_task_store(settings, store_kind=store_kind),
        sandboxes=create_sandbox_store(settings, store_kind=store_kind),
    )


def _create_artifact_blob_store(
    settings: Any,
    *,
    durable: bool,
    workspace_path: str = "",
) -> ArtifactBlobStore:
    if durable:
        return LocalArtifactBlobStore.for_server_root(getattr(settings.server, "ROOT_PATH", "."))
    return LocalArtifactBlobStore.for_cli_workspace(workspace_path or getattr(settings.server, "ROOT_PATH", "."))
