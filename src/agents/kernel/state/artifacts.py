from __future__ import annotations

import time
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, TYPE_CHECKING
from uuid import uuid4

from agents.kernel.persistence import SQLiteDatabase, json_dict, json_dumps

if TYPE_CHECKING:
    from agents.kernel.context.workspace import WorkspaceContext


_SAFE_SCOPE = re.compile(r"[^A-Za-z0-9_.-]+")


@dataclass(frozen=True)
class ArtifactRecord:
    artifact_id: str
    tenant_id: str
    user_id: str
    agent_id: str
    workspace_id: str
    run_id: str
    task_id: str = ""
    tool_call_id: str = ""
    kind: str = "file"
    role: str = "tool_artifact"
    storage_backend: str = "local"
    uri: str = ""
    workspace_path: str = ""
    mime_type: str = ""
    size_bytes: int = 0
    sha256: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    expires_at: float | None = None

    @classmethod
    def for_workspace(
        cls,
        workspace: WorkspaceContext,
        *,
        run_id: str,
        task_id: str = "",
        tool_call_id: str = "",
        kind: str = "file",
        role: str = "tool_artifact",
        storage_backend: str = "local",
        uri: str = "",
        workspace_path: str = "",
        mime_type: str = "",
        size_bytes: int = 0,
        sha256: str = "",
        metadata: dict[str, Any] | None = None,
        expires_at: float | None = None,
    ) -> "ArtifactRecord":
        return cls(
            artifact_id=new_artifact_id(),
            tenant_id=workspace.tenant_id,
            user_id=workspace.user_id,
            agent_id=workspace.agent_id,
            workspace_id=workspace.workspace_id,
            run_id=str(run_id or ""),
            task_id=str(task_id or ""),
            tool_call_id=str(tool_call_id or ""),
            kind=str(kind or "file"),
            role=str(role or "tool_artifact"),
            storage_backend=str(storage_backend or "local"),
            uri=str(uri or ""),
            workspace_path=str(workspace_path or ""),
            mime_type=str(mime_type or ""),
            size_bytes=int(size_bytes or 0),
            sha256=str(sha256 or ""),
            metadata=dict(metadata or {}),
            expires_at=expires_at,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "agent_id": self.agent_id,
            "workspace_id": self.workspace_id,
            "run_id": self.run_id,
            "task_id": self.task_id,
            "tool_call_id": self.tool_call_id,
            "kind": self.kind,
            "role": self.role,
            "storage_backend": self.storage_backend,
            "uri": self.uri,
            "workspace_path": self.workspace_path,
            "mime_type": self.mime_type,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "metadata": dict(self.metadata),
            "created_at": self.created_at,
            "expires_at": self.expires_at,
        }


class ArtifactStore(Protocol):
    async def save_artifact(self, artifact: ArtifactRecord) -> None:
        raise NotImplementedError()

    async def list_for_run(self, run_id: str) -> List[ArtifactRecord]:
        raise NotImplementedError()


@dataclass(frozen=True)
class ArtifactBlobLocation:
    host_path: Path
    uri: str
    sandbox_path: str
    relative_path: str
    category: str
    filename: str


class ArtifactBlobStore(Protocol):
    def run_artifact_root(self, workspace: WorkspaceContext, run_id: str) -> Path:
        raise NotImplementedError()

    def allocate(
        self,
        workspace: WorkspaceContext,
        *,
        run_id: str,
        category: str,
        filename: str,
    ) -> ArtifactBlobLocation:
        raise NotImplementedError()


class LocalArtifactBlobStore:
    def __init__(self, root: Path, *, include_workspace_scope: bool = True, sandbox_mount: str = "/artifacts"):
        self.root = Path(root).expanduser()
        self.include_workspace_scope = bool(include_workspace_scope)
        self.sandbox_mount = str(sandbox_mount or "/artifacts").rstrip("/") or "/artifacts"

    @classmethod
    def for_cli_workspace(cls, workspace_path: Path | str) -> "LocalArtifactBlobStore":
        digest = _workspace_hash(Path(workspace_path).expanduser().resolve())
        return cls(Path.home() / ".agents" / "projects" / digest, include_workspace_scope=False)

    @classmethod
    def for_server_root(cls, root_path: Path | str) -> "LocalArtifactBlobStore":
        return cls(Path(root_path) / ".agents" / "server" / "artifacts", include_workspace_scope=True)

    def run_artifact_root(self, workspace: WorkspaceContext, run_id: str) -> Path:
        parts = [self.root]
        if self.include_workspace_scope:
            parts.extend(
                [
                    Path(safe_scope_id(workspace.tenant_id, default="tenant")),
                    Path(safe_scope_id(workspace.user_id, default="user")),
                    Path(safe_scope_id(workspace.agent_id, default="agent")),
                    Path(safe_scope_id(workspace.workspace_id, default="workspace")),
                ]
            )
        parts.extend([Path("runs"), Path(safe_scope_id(run_id, default="manual")), Path("artifacts")])
        path = parts[0]
        for part in parts[1:]:
            path = path / part
        return path

    def allocate(
        self,
        workspace: WorkspaceContext,
        *,
        run_id: str,
        category: str,
        filename: str,
    ) -> ArtifactBlobLocation:
        safe_category = safe_scope_id(category, default="files")
        safe_name = safe_scope_id(filename, default="artifact.bin")
        root = self.run_artifact_root(workspace, run_id)
        host_path = root / safe_category / safe_name
        host_path.parent.mkdir(parents=True, exist_ok=True)
        relative = "%s/%s" % (safe_category, safe_name)
        return ArtifactBlobLocation(
            host_path=host_path,
            uri=host_path.as_posix(),
            sandbox_path="%s/%s" % (self.sandbox_mount, relative),
            relative_path=relative,
            category=safe_category,
            filename=safe_name,
        )


class InMemoryArtifactStore:
    def __init__(self):
        self._records: Dict[str, ArtifactRecord] = {}

    async def save_artifact(self, artifact: ArtifactRecord) -> None:
        self._records[artifact.artifact_id] = artifact

    async def list_for_run(self, run_id: str) -> List[ArtifactRecord]:
        return sorted(
            [record for record in self._records.values() if record.run_id == run_id],
            key=lambda record: record.created_at,
        )


class SQLiteArtifactStore:
    def __init__(self, database: SQLiteDatabase):
        self.database = database

    async def save_artifact(self, artifact: ArtifactRecord) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO artifact_records (
                    artifact_id, tenant_id, user_id, agent_id, workspace_id, run_id, task_id,
                    tool_call_id, kind, role, storage_backend, uri, workspace_path, mime_type,
                    size_bytes, sha256, metadata_json, created_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(artifact_id) DO UPDATE SET
                    role = excluded.role,
                    storage_backend = excluded.storage_backend,
                    uri = excluded.uri,
                    workspace_path = excluded.workspace_path,
                    mime_type = excluded.mime_type,
                    size_bytes = excluded.size_bytes,
                    sha256 = excluded.sha256,
                    metadata_json = excluded.metadata_json,
                    expires_at = excluded.expires_at
                """,
                (
                    artifact.artifact_id,
                    artifact.tenant_id,
                    artifact.user_id,
                    artifact.agent_id,
                    artifact.workspace_id,
                    artifact.run_id,
                    artifact.task_id,
                    artifact.tool_call_id,
                    artifact.kind,
                    artifact.role,
                    artifact.storage_backend,
                    artifact.uri,
                    artifact.workspace_path,
                    artifact.mime_type,
                    artifact.size_bytes,
                    artifact.sha256,
                    json_dumps(artifact.metadata),
                    artifact.created_at,
                    artifact.expires_at,
                ),
            )

    async def list_for_run(self, run_id: str) -> List[ArtifactRecord]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM artifact_records
                WHERE run_id = ?
                ORDER BY created_at ASC, artifact_id ASC
                """,
                (run_id,),
            ).fetchall()
        return [_artifact_from_row(row) for row in rows]


def new_artifact_id() -> str:
    return "artifact_%s" % uuid4().hex


def safe_scope_id(value: str, default: str = "scope") -> str:
    cleaned = _SAFE_SCOPE.sub("-", str(value or "").strip()).strip(".-")
    return cleaned or default


def _workspace_hash(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.as_posix().encode("utf-8")).hexdigest()[:16]


def _artifact_from_row(row) -> ArtifactRecord:
    return ArtifactRecord(
        artifact_id=str(row["artifact_id"]),
        tenant_id=str(row["tenant_id"]),
        user_id=str(row["user_id"]),
        agent_id=str(row["agent_id"]),
        workspace_id=str(row["workspace_id"]),
        run_id=str(row["run_id"]),
        task_id=str(row["task_id"] or ""),
        tool_call_id=str(row["tool_call_id"] or ""),
        kind=str(row["kind"] or "file"),
        role=str(row["role"] or "tool_artifact"),
        storage_backend=str(row["storage_backend"] or "local"),
        uri=str(row["uri"] or ""),
        workspace_path=str(row["workspace_path"] or ""),
        mime_type=str(row["mime_type"] or ""),
        size_bytes=int(row["size_bytes"] or 0),
        sha256=str(row["sha256"] or ""),
        metadata=json_dict(row["metadata_json"]),
        created_at=float(row["created_at"]),
        expires_at=None if row["expires_at"] is None else float(row["expires_at"]),
    )
