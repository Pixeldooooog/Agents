from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

from agents.kernel.runtime.checkpoints import RuntimeCheckpoint
from agents.kernel.schema import Message, RuntimeEvent, ToolCall, ToolResult


@dataclass(frozen=True)
class TerminalSessionRecord:
    session_id: str
    updated_at: float
    profile: str
    model: str
    workspace_path: str
    message_count: int
    messages: list[Message] = field(default_factory=list)
    pending_run_id: str = ""
    pending_approval: dict[str, Any] = field(default_factory=dict)
    checkpoint: RuntimeCheckpoint | None = None


class TerminalSessionStore:
    def __init__(self, root: Path):
        self.root = Path(root)

    @classmethod
    def for_workspace(cls, workspace: Path | None) -> "TerminalSessionStore":
        if os.getenv("AGENTS_TERMINAL_SESSION_STORE"):
            return cls(Path(os.environ["AGENTS_TERMINAL_SESSION_STORE"]))
        base = Path(workspace or Path.cwd())
        return cls(base / ".agents" / "terminal-sessions")

    def new_session_id(self) -> str:
        return "session_%s_%s" % (time.strftime("%Y%m%d%H%M%S"), uuid4().hex[:8])

    def save(
        self,
        session_id: str,
        messages: list[Message],
        *,
        profile: str,
        model: str,
        workspace_path: str,
        pending_run_id: str = "",
        pending_approval: dict[str, Any] | None = None,
        checkpoint: RuntimeCheckpoint | None = None,
    ) -> bool:
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            payload = {
                "session_id": session_id,
                "updated_at": time.time(),
                "profile": profile,
                "model": model,
                "workspace_path": workspace_path,
                "messages": [message.to_dict() for message in messages],
                "pending_run_id": pending_run_id,
                "pending_approval": dict(pending_approval or {}),
                "checkpoint": _checkpoint_to_payload(checkpoint) if checkpoint else None,
            }
            self._path(session_id).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            return True
        except Exception:
            return False

    def list(self, limit: int = 20) -> list[TerminalSessionRecord]:
        records = [record for record in (self._read(path, include_messages=False) for path in self._paths()) if record]
        records.sort(key=lambda record: record.updated_at, reverse=True)
        return records[:limit]

    def load(self, query: str) -> TerminalSessionRecord | None:
        query = str(query or "").strip()
        records = self.list(limit=200)
        if not records:
            return None
        if query in {"latest", "-"}:
            return self._read(self._path(records[0].session_id), include_messages=True)
        exact = next((record for record in records if record.session_id == query), None)
        if exact:
            return self._read(self._path(exact.session_id), include_messages=True)
        matches = [record for record in records if record.session_id.startswith(query)]
        if len(matches) == 1:
            return self._read(self._path(matches[0].session_id), include_messages=True)
        return None

    def delete(self, query: str) -> TerminalSessionRecord | None:
        record = self.load(query)
        if record is None:
            return None
        try:
            self._path(record.session_id).unlink()
        except FileNotFoundError:
            pass
        except Exception:
            return None
        return record

    def _paths(self) -> list[Path]:
        try:
            return list(self.root.glob("*.json"))
        except Exception:
            return []

    def _path(self, session_id: str) -> Path:
        safe = "".join(ch for ch in session_id if ch.isalnum() or ch in {"_", "-"})
        return self.root / ("%s.json" % (safe or "session"))

    def _read(self, path: Path, *, include_messages: bool) -> TerminalSessionRecord | None:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        messages_payload = payload.get("messages", [])
        messages = _messages_from_payload(messages_payload) if include_messages else []
        checkpoint_payload = payload.get("checkpoint") if include_messages else None
        return TerminalSessionRecord(
            session_id=str(payload.get("session_id") or path.stem),
            updated_at=float(payload.get("updated_at") or 0),
            profile=str(payload.get("profile") or ""),
            model=str(payload.get("model") or ""),
            workspace_path=str(payload.get("workspace_path") or ""),
            message_count=len(messages_payload) if isinstance(messages_payload, list) else 0,
            messages=messages,
            pending_run_id=str(payload.get("pending_run_id") or ""),
            pending_approval=dict(payload.get("pending_approval") or {}) if isinstance(payload.get("pending_approval"), dict) else {},
            checkpoint=_checkpoint_from_payload(checkpoint_payload) if isinstance(checkpoint_payload, dict) else None,
        )


def save_session_snapshot(
    state: Any,
    *,
    pending_run_id: str = "",
    pending_approval: dict[str, Any] | None = None,
    checkpoint: RuntimeCheckpoint | None = None,
) -> None:
    state.session_store.save(
        state.session_id,
        list(getattr(state.session, "messages", []) or []),
        profile=state.profile,
        model=session_model_label(state.session),
        workspace_path=str(state.active_workspace or ""),
        pending_run_id=pending_run_id,
        pending_approval=pending_approval,
        checkpoint=checkpoint,
    )


def session_model_label(session: Any) -> str:
    runtime = getattr(session, "runtime", None)
    protocol = str(getattr(runtime, "protocol", "") or "")
    model = str(getattr(runtime, "model", "") or "")
    if protocol and model:
        return "%s · %s" % (protocol, model)
    return protocol or model


def _messages_from_payload(payload: Any) -> list[Message]:
    if not isinstance(payload, list):
        return []
    messages: list[Message] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        try:
            messages.append(Message.from_dict(item))
        except Exception:
            continue
    return messages


def _checkpoint_to_payload(checkpoint: RuntimeCheckpoint | None) -> dict[str, Any] | None:
    if checkpoint is None:
        return None
    return {
        "run_id": checkpoint.run_id,
        "step": checkpoint.step,
        "iteration": checkpoint.iteration,
        "messages": [message.to_dict() for message in checkpoint.messages],
        "tool_results": [result.to_dict() for result in checkpoint.tool_results],
        "events": [event.to_dict() for event in checkpoint.events],
        "pending_tool_calls": [call.to_dict() for call in checkpoint.pending_tool_calls],
        "tool_approvals": dict(checkpoint.tool_approvals),
        "tool_approval_scopes": dict(checkpoint.tool_approval_scopes),
        "tool_approval_grants": dict(checkpoint.tool_approval_grants),
        "created_at": checkpoint.created_at,
    }


def _checkpoint_from_payload(payload: dict[str, Any]) -> RuntimeCheckpoint | None:
    try:
        return RuntimeCheckpoint(
            run_id=str(payload.get("run_id") or ""),
            step=str(payload.get("step") or ""),
            iteration=int(payload.get("iteration") or 0),
            messages=[Message.from_dict(item) for item in payload.get("messages", []) if isinstance(item, dict)],
            tool_results=[ToolResult.from_dict(item) for item in payload.get("tool_results", []) if isinstance(item, dict)],
            events=[_runtime_event_from_payload(item) for item in payload.get("events", []) if isinstance(item, dict)],
            pending_tool_calls=[ToolCall.from_dict(item) for item in payload.get("pending_tool_calls", []) if isinstance(item, dict)],
            tool_approvals={str(key): bool(value) for key, value in dict(payload.get("tool_approvals") or {}).items()},
            tool_approval_scopes={str(key): str(value) for key, value in dict(payload.get("tool_approval_scopes") or {}).items()},
            tool_approval_grants={str(key): bool(value) for key, value in dict(payload.get("tool_approval_grants") or {}).items()},
            created_at=float(payload.get("created_at") or 0),
        )
    except Exception:
        return None


def _runtime_event_from_payload(payload: dict[str, Any]) -> RuntimeEvent:
    return RuntimeEvent(
        type=str(payload.get("type") or ""),
        name=str(payload.get("name") or ""),
        payload=dict(payload.get("payload") or {}),
        raw=payload.get("raw"),
    )
