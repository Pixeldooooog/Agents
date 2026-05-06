from __future__ import annotations

from pathlib import Path
from typing import Any

from agents.kernel.capabilities.sandbox import InMemorySandboxStore, SandboxStore, SQLiteSandboxStore
from agents.kernel.governance.audit import (
    ApprovalAuditStore,
    InMemoryApprovalAuditStore,
    SQLiteApprovalAuditStore,
)
from agents.kernel.capabilities.memory import InMemoryMemoryStore, MemoryStore, SQLiteMemoryStore
from agents.kernel.persistence import SQLiteDatabase, resolve_database_path
from agents.kernel.runtime import CheckpointStore, InMemoryCheckpointStore, SQLiteCheckpointStore
from agents.kernel.tasks import InMemoryTaskStore, SQLiteTaskStore, TaskStore
from agents.kernel.governance import CredentialRefStore, InMemoryCredentialRefStore, SQLiteCredentialRefStore
from agents.kernel.state import (
    AgentProfileStore,
    ArtifactStore,
    IdentityStore,
    InMemoryAgentProfileStore,
    InMemoryArtifactStore,
    InMemoryIdentityStore,
    InMemoryRunStore,
    InMemoryWorkspaceStore,
    LocalFileRunStore,
    RunStore,
    SQLiteAgentProfileStore,
    SQLiteArtifactStore,
    SQLiteIdentityStore,
    SQLiteRunStore,
    SQLiteWorkspaceStore,
    WorkspaceStore,
)
from agents.kernel.governance.tracing import InMemoryTraceStore, RuntimeTraceRecorder, SQLiteTraceStore, TraceStore


def create_run_store(settings: Any, store_kind: str | None = None) -> RunStore:
    store_kind = _store_kind(settings, store_kind)
    if store_kind == "file":
        configured_root = Path(str(getattr(settings.agent, "RUN_ROOT", ".agents/runs")))
        root = configured_root if configured_root.is_absolute() else Path(settings.server.ROOT_PATH) / configured_root
        return LocalFileRunStore(root)
    if store_kind == "sqlite":
        return SQLiteRunStore(_sqlite_database(settings))
    if store_kind == "memory":
        return InMemoryRunStore()
    raise ValueError("unsupported AGENT_RUN_STORE: %s" % store_kind)


def create_checkpoint_store(settings: Any, store_kind: str | None = None) -> CheckpointStore:
    if _uses_sqlite(settings, store_kind):
        return SQLiteCheckpointStore(_sqlite_database(settings))
    return InMemoryCheckpointStore()


def create_approval_audit_store(settings: Any, store_kind: str | None = None) -> ApprovalAuditStore:
    if _uses_sqlite(settings, store_kind):
        return SQLiteApprovalAuditStore(_sqlite_database(settings))
    return InMemoryApprovalAuditStore()


def create_trace_store(settings: Any, store_kind: str | None = None) -> TraceStore:
    if _uses_sqlite(settings, store_kind):
        return SQLiteTraceStore(_sqlite_database(settings))
    return InMemoryTraceStore()


def create_trace_recorder(settings: Any, store: TraceStore | None = None) -> RuntimeTraceRecorder:
    return RuntimeTraceRecorder(store or create_trace_store(settings))


def create_identity_store(settings: Any, store_kind: str | None = None) -> IdentityStore:
    if _uses_sqlite(settings, store_kind):
        return SQLiteIdentityStore(_sqlite_database(settings))
    return InMemoryIdentityStore()


def create_agent_profile_store(settings: Any, store_kind: str | None = None) -> AgentProfileStore:
    if _uses_sqlite(settings, store_kind):
        return SQLiteAgentProfileStore(_sqlite_database(settings))
    return InMemoryAgentProfileStore()


def create_workspace_store(settings: Any, store_kind: str | None = None) -> WorkspaceStore:
    if _uses_sqlite(settings, store_kind):
        return SQLiteWorkspaceStore(_sqlite_database(settings))
    return InMemoryWorkspaceStore()


def create_artifact_store(settings: Any, store_kind: str | None = None) -> ArtifactStore:
    if _uses_sqlite(settings, store_kind):
        return SQLiteArtifactStore(_sqlite_database(settings))
    return InMemoryArtifactStore()


def create_memory_store(settings: Any, store_kind: str | None = None) -> MemoryStore:
    if _uses_sqlite(settings, store_kind):
        return SQLiteMemoryStore(_sqlite_database(settings))
    return InMemoryMemoryStore()


def create_credential_ref_store(settings: Any, store_kind: str | None = None) -> CredentialRefStore:
    if _uses_sqlite(settings, store_kind):
        return SQLiteCredentialRefStore(_sqlite_database(settings))
    return InMemoryCredentialRefStore()


def create_task_store(settings: Any, store_kind: str | None = None) -> TaskStore:
    if _uses_sqlite(settings, store_kind):
        return SQLiteTaskStore(_sqlite_database(settings))
    return InMemoryTaskStore()


def create_sandbox_store(settings: Any, store_kind: str | None = None) -> SandboxStore:
    if _uses_sqlite(settings, store_kind):
        return SQLiteSandboxStore(_sqlite_database(settings))
    return InMemorySandboxStore()


def _uses_sqlite(settings: Any, store_kind: str | None = None) -> bool:
    return _store_kind(settings, store_kind) == "sqlite"


def _store_kind(settings: Any, override: str | None = None) -> str:
    return str(override or getattr(settings.agent, "RUN_STORE", "memory") or "memory").strip().lower()


def _sqlite_database(settings: Any) -> SQLiteDatabase:
    configured_path = str(getattr(settings.agent, "DB_PATH", ".agents/agents.db"))
    path = resolve_database_path(Path(settings.server.ROOT_PATH), configured_path)
    return SQLiteDatabase(path)
