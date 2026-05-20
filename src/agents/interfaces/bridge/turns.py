from __future__ import annotations

import asyncio
from typing import Any, Callable

from agents.interfaces.bridge.sessions import save_session_snapshot
from agents.kernel.governance.approval_grants import (
    APPROVAL_ALLOW_ONCE,
    APPROVAL_DENY,
    normalize_approval_decision,
)
from agents.kernel.governance.audit import ApprovalAuditRecord
from agents.kernel.schema import RuntimeEvent

BridgeWrite = Callable[[dict[str, Any]], None]


async def run_turn(state: Any, text: str, run_id: str, write: BridgeWrite) -> None:
    if not text.strip():
        return
    write({"type": "turn_started", "run_id": run_id})
    status = "finished"
    persisted_events = 0
    event_offset: int | None = None
    pending_approval: dict[str, Any] | None = None
    try:
        async for event in state.session.stream(text, run_id=run_id):
            if event.type == "done":
                status = str(event.payload.get("status") or status)
                raw_event_count = event.payload.get("event_count")
                if isinstance(raw_event_count, int):
                    event_offset = raw_event_count
            elif event.type == "tool_approval_required":
                pending_approval = event.to_dict()
                persisted_events += 1
            elif is_persisted_runtime_event(event):
                persisted_events += 1
            write({"type": "runtime_event", "event": event.to_dict()})
    except asyncio.CancelledError:
        status = "cancelled"
    except Exception as exc:  # noqa: BLE001 - bridge must keep the client alive after one bad turn.
        status = "error"
        write({"type": "runtime_event", "event": {"type": "error", "name": "bridge", "payload": {"message": str(exc)}}})
    state.event_offsets[run_id] = event_offset if event_offset is not None else persisted_events
    if status == "awaiting_approval":
        checkpoint = await _load_checkpoint(state, run_id)
        save_session_snapshot(state, pending_run_id=run_id, pending_approval=pending_approval, checkpoint=checkpoint)
    else:
        save_session_snapshot(state)
    write({"type": "turn_finished", "status": status, "run_id": run_id})


async def run_approval(state: Any, command: dict[str, Any], write: BridgeWrite) -> None:
    run_id = str(command.get("run_id") or "")
    if not run_id:
        write({"type": "error", "message": "approval command requires run_id"})
        write({"type": "turn_finished", "status": "error", "run_id": run_id})
        return
    approvals_payload = command.get("approvals") if isinstance(command.get("approvals"), dict) else {}
    scopes_payload = command.get("approval_scopes") if isinstance(command.get("approval_scopes"), dict) else {}
    tool_inputs = command.get("tool_inputs") if isinstance(command.get("tool_inputs"), dict) else {}
    approvals: dict[str, bool] = {}
    approval_scopes: dict[str, str] = {}
    for approval_id, raw_approved in approvals_payload.items():
        approval_key = str(approval_id)
        approved = bool(raw_approved)
        raw_scope = scopes_payload.get(approval_key, APPROVAL_ALLOW_ONCE if approved else APPROVAL_DENY)
        try:
            scope = normalize_approval_decision(raw_scope, approved=approved)
        except ValueError as exc:
            write({"type": "error", "message": str(exc)})
            write({"type": "turn_finished", "status": "error", "run_id": run_id})
            return
        approvals[approval_key] = scope != APPROVAL_DENY
        approval_scopes[approval_key] = scope if approvals[approval_key] else APPROVAL_DENY
    await _record_approval_audit(state, run_id, approvals, approval_scopes)
    status = "finished"
    try:
        resume_stream = getattr(state.session, "resume_stream", None)
        if resume_stream is not None:
            event_offset: int | None = None
            resume_kwargs = {"approvals": approvals, "approval_scopes": approval_scopes}
            if tool_inputs:
                resume_kwargs["tool_inputs"] = tool_inputs
            async for event in resume_stream(run_id, **resume_kwargs):
                if event.type == "done":
                    status = str(event.payload.get("status") or status)
                    raw_event_count = event.payload.get("event_count")
                    if isinstance(raw_event_count, int):
                        event_offset = raw_event_count
                write({"type": "runtime_event", "event": event.to_dict()})
            if event_offset is not None:
                state.event_offsets[run_id] = event_offset
        else:
            resume_kwargs = {"approvals": approvals, "approval_scopes": approval_scopes}
            if tool_inputs:
                resume_kwargs["tool_inputs"] = tool_inputs
            result = await state.session.resume(run_id, **resume_kwargs)
            for event in new_events(result.events, state.event_offsets.get(run_id, 0)):
                write({"type": "runtime_event", "event": event.to_dict()})
            state.event_offsets[run_id] = len(result.events)
            status = result.status
        if status != "awaiting_approval":
            save_session_snapshot(state)
    except asyncio.CancelledError:
        status = "cancelled"
    except Exception as exc:  # noqa: BLE001 - keep the bridge process alive after a failed resume.
        status = "error"
        write({"type": "runtime_event", "event": {"type": "error", "name": "bridge", "payload": {"message": str(exc)}}})
    write({"type": "turn_finished", "status": status, "run_id": run_id})


def is_persisted_runtime_event(event: RuntimeEvent) -> bool:
    return event.type in {
        "model_message",
        "tool_approval_required",
        "tool_approval_decision",
        "tool_start",
        "tool_result",
        "error",
    }


def new_events(events: list[RuntimeEvent], offset: int) -> list[RuntimeEvent]:
    if offset and len(events) >= offset:
        return list(events)[offset:]
    return list(events)


async def _load_checkpoint(state: Any, run_id: str) -> Any:
    checkpoints = getattr(getattr(state, "persistence", None), "checkpoints", None)
    load = getattr(checkpoints, "load", None)
    if load is None:
        return None
    try:
        return await load(run_id)
    except Exception:
        return None


async def _record_approval_audit(state: Any, run_id: str, approvals: dict[str, bool], approval_scopes: dict[str, str]) -> None:
    store = getattr(getattr(state, "persistence", None), "approval_audit", None)
    record = getattr(store, "record", None)
    if record is None:
        return
    checkpoint = await _load_checkpoint(state, run_id)
    pending_calls = list(getattr(checkpoint, "pending_tool_calls", []) or []) if checkpoint is not None else []
    try:
        for call in pending_calls:
            approval_id = str(getattr(call, "id", "") or getattr(call, "name", ""))
            if approval_id not in approvals:
                continue
            await record(
                ApprovalAuditRecord.from_tool_call(
                    run_id=run_id,
                    call=call,
                    approved=approvals[approval_id],
                    decision=approval_scopes.get(approval_id, APPROVAL_ALLOW_ONCE if approvals[approval_id] else APPROVAL_DENY),
                )
            )
    except Exception:
        return None
