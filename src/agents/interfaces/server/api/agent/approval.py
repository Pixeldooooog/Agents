from __future__ import annotations

from agents.kernel.governance.approval_grants import (
    APPROVAL_ALLOW_FOR_RUN,
    approval_grant_key,
    approval_is_allowed,
    normalize_approval_decision,
)
from agents.kernel.schema import RuntimeEvent
from agents.interfaces.server.api.agent.schemas import RunApprovalRequest


def decision_map_from_request(request_data: RunApprovalRequest, pending_calls) -> dict[str, str]:
    if request_data.decisions:
        return {str(key): normalize_approval_decision(value) for key, value in request_data.decisions.items()}
    if request_data.approvals:
        return {str(key): normalize_approval_decision(value) for key, value in request_data.approvals.items()}
    pending_ids = [call.id or call.name for call in pending_calls]
    selected = request_data.tool_call_ids or pending_ids
    decision = normalize_approval_decision(request_data.decision, request_data.approved)
    return {str(item): decision for item in selected}


def approval_bool_map(decisions: dict[str, str]) -> dict[str, bool]:
    return {approval_id: approval_is_allowed(decision) for approval_id, decision in decisions.items()}


def approval_grant_map(pending_calls, approvals: dict[str, bool], decisions: dict[str, str]) -> dict[str, bool]:
    grants: dict[str, bool] = {}
    for call in pending_calls:
        approval_id = call.id or call.name
        if approvals.get(approval_id) and decisions.get(approval_id) == APPROVAL_ALLOW_FOR_RUN:
            grants[approval_grant_key(call)] = True
    return grants


def new_runtime_events(record_events, result_events) -> list[RuntimeEvent]:
    recorded_runtime_events = [event for event in record_events if event.type != "run_created"]
    return list(result_events)[len(recorded_runtime_events):]
