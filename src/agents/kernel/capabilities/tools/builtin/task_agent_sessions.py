from __future__ import annotations

from typing import Any

from agents.kernel.capabilities.tools.builtin.agent_isolation import (
    AgentIsolationScope,
    prepare_agent_isolation_scope,
    with_agent_workspace_path,
)
from agents.kernel.capabilities.tools.builtin.agent_child_specs import child_agent_spec
from agents.kernel.capabilities.tools.context import ToolRuntimeContext
from agents.kernel.schema import RuntimeEvent


class TaskAgentSessionFactory:
    def __init__(self, context: ToolRuntimeContext):
        self.context = context

    async def create(self, task: Any) -> Any:
        spec = task.to_agent_spec()
        metadata = dict(getattr(task, "metadata", {}) or {})
        child_agent_id = _task_child_agent_id(task, spec, metadata)
        if _has_explicit_child_agent(metadata):
            spec = child_agent_spec(
                self.context,
                base_spec=spec,
                agent_id=child_agent_id,
                description=getattr(task, "title", ""),
            )
            child_agent_id = spec.agent_id
        scope = await prepare_agent_isolation_scope(
            self.context,
            child_agent_id=child_agent_id,
            isolation=str(metadata.get("isolation") or ""),
            cwd=str(metadata.get("cwd") or ""),
        )
        if scope.workspace_path is not None:
            spec = with_agent_workspace_path(spec, scope.workspace_path)
        try:
            session = await self.context.agent_session_factory(spec, task_id=task.task_id)
        except Exception:
            scope.close()
            raise
        return _TaskAgentSession(session, scope)


class _TaskAgentSession:
    def __init__(self, session: Any, scope: AgentIsolationScope):
        self.session = session
        self.scope = scope
        self._last_result: Any | None = None

    async def send(self, *args: Any, **kwargs: Any) -> Any:
        self._last_result = await self.session.send(*args, **kwargs)
        return self._last_result

    async def aclose(self) -> None:
        try:
            close = getattr(self.session, "aclose", None)
            if close is not None:
                await close()
        finally:
            self.scope.close()
            _annotate_result(self._last_result, self.scope.result_fields())


def agent_worktree_result_fields(result: Any) -> dict[str, Any]:
    for event in reversed(list(getattr(result, "events", []) or [])):
        if event.type == "agent_worktree" and isinstance(event.payload, dict):
            return dict(event.payload)
    return {}


def _annotate_result(result: Any | None, fields: dict[str, Any]) -> None:
    if result is None or not fields:
        return
    result.events.append(RuntimeEvent(type="agent_worktree", name="agent_worktree", payload=dict(fields)))
    if fields.get("worktreePath"):
        result.content = _append_worktree_notice(result.content, fields)


def _append_worktree_notice(content: str, fields: dict[str, Any]) -> str:
    lines = ["worktreePath: %s" % fields["worktreePath"]]
    if fields.get("worktreeBranch"):
        lines.append("worktreeBranch: %s" % fields["worktreeBranch"])
    body = str(content or "").rstrip()
    notice = "\n".join(lines)
    return "%s\n\n%s" % (body, notice) if body else notice


def _task_child_agent_id(task: Any, spec: Any, metadata: dict[str, Any]) -> str:
    return str(
        metadata.get("name")
        or metadata.get("agent_id")
        or getattr(task, "task_id", "")
        or spec.agent_id
        or getattr(task, "agent_id", "")
    )


def _has_explicit_child_agent(metadata: dict[str, Any]) -> bool:
    return bool(metadata.get("name") or metadata.get("agent_id"))
