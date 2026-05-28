from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from agents.kernel.capabilities.tools.builtin.agent_worktree import AgentWorktree, cleanup_agent_worktree, create_agent_worktree
from agents.kernel.capabilities.tools.context import ToolRuntimeContext
from agents.kernel.specs import AgentSpec, WorkspaceRef


@dataclass
class AgentIsolationScope:
    workspace_path: Path | None = None
    worktree: AgentWorktree | None = None
    _cleanup_fields: dict[str, Any] = field(default_factory=dict)

    def close(self) -> None:
        if self.worktree is None:
            return
        self._cleanup_fields = cleanup_agent_worktree(self.worktree)

    def result_fields(self) -> dict[str, Any]:
        return dict(self._cleanup_fields)


async def prepare_agent_isolation_scope(
    context: ToolRuntimeContext,
    *,
    child_agent_id: str,
    isolation: str = "",
    cwd: str = "",
) -> AgentIsolationScope:
    resolved_cwd = resolve_agent_cwd(context, cwd)
    kind = _normalized_isolation(isolation)
    if kind == "worktree":
        worktree = await create_agent_worktree(context, child_agent_id)
        return AgentIsolationScope(workspace_path=resolved_cwd or worktree.path, worktree=worktree)
    return AgentIsolationScope(workspace_path=resolved_cwd)


def resolve_agent_cwd(context: ToolRuntimeContext, cwd: str) -> Path | None:
    value = str(cwd or "").strip()
    if not value:
        return None
    base = Path(context.workspace.path).expanduser().resolve()
    raw_path = Path(value).expanduser()
    resolved = raw_path.resolve() if raw_path.is_absolute() else (base / raw_path).resolve()
    _require_inside_workspace(resolved, base, "cwd")
    if not resolved.is_dir():
        raise ValueError("cwd does not exist or is not a directory: %s" % resolved)
    return resolved


def with_agent_workspace_path(spec: AgentSpec, workspace_path: Path) -> AgentSpec:
    workspace = spec.workspace
    updated = WorkspaceRef(
        tenant_id=workspace.tenant_id,
        user_id=workspace.user_id,
        agent_id=workspace.agent_id,
        workspace_id=workspace.workspace_id,
        path=str(workspace_path),
    )
    return replace(spec, workspace=updated)


def _normalized_isolation(isolation: str) -> str:
    value = str(isolation or "").strip().lower()
    if value in {"", "none"}:
        return ""
    if value == "worktree":
        return value
    if value == "remote":
        raise ValueError("remote agent isolation is not supported for synchronous agent.run yet")
    raise ValueError("unsupported agent isolation: %s" % isolation)


def _require_inside_workspace(path: Path, workspace_path: Path, label: str) -> None:
    try:
        path.relative_to(workspace_path)
    except ValueError as exc:
        raise ValueError("%s must stay inside the current workspace: %s" % (label, path)) from exc
