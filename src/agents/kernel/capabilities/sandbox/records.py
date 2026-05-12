from __future__ import annotations

import time
from dataclasses import dataclass, field, replace
from typing import Any

from agents.kernel.context.workspace import WorkspaceContext
from agents.kernel.persistence import json_dict

from .types import SandboxLease, SandboxProfile


@dataclass(frozen=True)
class SandboxLeaseRecord:
    lease_id: str
    provider: str
    tenant_id: str
    user_id: str
    agent_id: str
    workspace_id: str
    run_id: str = ""
    task_id: str = ""
    status: str = "active"
    profile: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, str] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    expires_at: float | None = None

    @classmethod
    def from_lease(cls, lease: SandboxLease) -> "SandboxLeaseRecord":
        workspace = lease.workspace
        return cls(
            lease_id=lease.lease_id,
            provider=lease.provider,
            tenant_id=workspace.tenant_id,
            user_id=workspace.user_id,
            agent_id=workspace.agent_id,
            workspace_id=workspace.workspace_id,
            run_id=str(lease.metadata.get("run_id") or ""),
            task_id=str(lease.metadata.get("task_id") or ""),
            profile=profile_to_dict(lease.profile),
            metadata={key: str(value) for key, value in lease.metadata.items()},
            created_at=lease.created_at,
            expires_at=lease.expires_at,
        )

    @classmethod
    def for_workspace(
        cls,
        lease_id: str,
        provider: str,
        workspace: WorkspaceContext,
        profile: SandboxProfile,
        run_id: str = "",
        task_id: str = "",
    ) -> "SandboxLeaseRecord":
        return cls(
            lease_id=lease_id,
            provider=provider,
            tenant_id=workspace.tenant_id,
            user_id=workspace.user_id,
            agent_id=workspace.agent_id,
            workspace_id=workspace.workspace_id,
            run_id=str(run_id or ""),
            task_id=str(task_id or ""),
            profile=profile_to_dict(profile),
        )

    def with_status(self, status: str) -> "SandboxLeaseRecord":
        return replace(self, status=status, updated_at=time.time())

    def to_event(self, event_type: str, payload: dict[str, str] | None = None) -> "SandboxEventRecord":
        return SandboxEventRecord(
            lease_id=self.lease_id,
            event_type=event_type,
            run_id=self.run_id,
            task_id=self.task_id,
            payload=dict(payload or {}),
        )

    def to_dict(self) -> dict:
        return {
            "lease_id": self.lease_id,
            "provider": self.provider,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "agent_id": self.agent_id,
            "workspace_id": self.workspace_id,
            "run_id": self.run_id,
            "task_id": self.task_id,
            "status": self.status,
            "profile": dict(self.profile),
            "metadata": dict(self.metadata),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "expires_at": self.expires_at,
        }


@dataclass(frozen=True)
class SandboxEventRecord:
    lease_id: str
    event_type: str
    run_id: str = ""
    task_id: str = ""
    tool_call_id: str = ""
    tool_name: str = ""
    status: str = ""
    duration_ms: float = 0.0
    payload: dict[str, str] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "lease_id": self.lease_id,
            "event_type": self.event_type,
            "run_id": self.run_id,
            "task_id": self.task_id,
            "tool_call_id": self.tool_call_id,
            "tool_name": self.tool_name,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "payload": dict(self.payload),
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class SandboxWorkspaceSnapshotRecord:
    snapshot_id: str
    lease_id: str
    run_id: str
    task_id: str = ""
    phase: str = ""
    file_count: int = 0
    total_bytes: int = 0
    manifest: dict[str, Any] = field(default_factory=dict)
    diff: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "snapshot_id": self.snapshot_id,
            "lease_id": self.lease_id,
            "run_id": self.run_id,
            "task_id": self.task_id,
            "phase": self.phase,
            "file_count": self.file_count,
            "total_bytes": self.total_bytes,
            "manifest": dict(self.manifest),
            "diff": dict(self.diff),
            "created_at": self.created_at,
        }


def profile_to_dict(profile: SandboxProfile) -> dict[str, str]:
    return {
        "name": profile.name,
        "provider": profile.provider,
        "image": profile.image,
        "network_mode": profile.network_mode,
        "memory": profile.memory,
        "cpus": profile.cpus,
        "ttl_seconds": str(profile.ttl_seconds),
        "workdir": profile.workdir,
    }


def lease_from_row(row) -> SandboxLeaseRecord:
    return SandboxLeaseRecord(
        lease_id=str(row["lease_id"]),
        provider=str(row["provider"]),
        tenant_id=str(row["tenant_id"]),
        user_id=str(row["user_id"]),
        agent_id=str(row["agent_id"]),
        workspace_id=str(row["workspace_id"]),
        run_id=str(row["run_id"] or ""),
        task_id=str(row["task_id"] or ""),
        status=str(row["status"]),
        profile={key: str(value) for key, value in json_dict(row["profile_json"]).items()},
        metadata={key: str(value) for key, value in json_dict(row["metadata_json"]).items()},
        created_at=float(row["created_at"]),
        updated_at=float(row["updated_at"]),
        expires_at=None if row["expires_at"] is None else float(row["expires_at"]),
    )


def event_from_row(row) -> SandboxEventRecord:
    return SandboxEventRecord(
        lease_id=str(row["lease_id"]),
        event_type=str(row["event_type"]),
        run_id=str(row["run_id"] or ""),
        task_id=str(row["task_id"] or ""),
        tool_call_id=str(row["tool_call_id"] or ""),
        tool_name=str(row["tool_name"] or ""),
        status=str(row["status"] or ""),
        duration_ms=float(row["duration_ms"] or 0.0),
        payload={key: str(value) for key, value in json_dict(row["payload_json"]).items()},
        created_at=float(row["created_at"]),
    )


def snapshot_from_row(row) -> SandboxWorkspaceSnapshotRecord:
    return SandboxWorkspaceSnapshotRecord(
        snapshot_id=str(row["snapshot_id"]),
        lease_id=str(row["lease_id"]),
        run_id=str(row["run_id"]),
        task_id=str(row["task_id"] or ""),
        phase=str(row["phase"] or ""),
        file_count=int(row["file_count"] or 0),
        total_bytes=int(row["total_bytes"] or 0),
        manifest=json_dict(row["manifest_json"]),
        diff=json_dict(row["diff_json"]),
        created_at=float(row["created_at"]),
    )
