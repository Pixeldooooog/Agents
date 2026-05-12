from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List
from typing import Mapping

from agents.kernel.governance.approval_grants import APPROVAL_ALLOW_FOR_RUN, APPROVAL_ALLOW_ONCE, APPROVAL_DENY, approval_grant_key
from agents.kernel.governance.permissions import ToolPermissionDecision
from agents.kernel.runtime.events import tool_approval_decision_event, tool_approval_id, tool_approval_required_event
from agents.kernel.runtime.state import RuntimeState
from agents.kernel.schema import RuntimeEvent


@dataclass(frozen=True)
class ApprovalDecisionResolution:
    decisions: List[ToolPermissionDecision]
    events: List[RuntimeEvent]
    decided_call_ids: set[str]


def apply_approval_updates(
    state: RuntimeState,
    approvals: Mapping[str, bool] | None = None,
    approval_scopes: Mapping[str, str] | None = None,
    approval_grants: Mapping[str, bool] | None = None,
) -> None:
    if approvals:
        state.tool_approvals.update({str(key): bool(value) for key, value in approvals.items()})
    if approval_scopes:
        state.tool_approval_scopes.update({str(key): str(value) for key, value in approval_scopes.items()})
    if approval_grants:
        state.tool_approval_grants.update({str(key): bool(value) for key, value in approval_grants.items()})
    derive_run_grants_from_scopes(state)


def derive_run_grants_from_scopes(state: RuntimeState) -> None:
    for call in state.pending_tool_calls:
        approval_id = tool_approval_id(call)
        if not state.tool_approvals.get(approval_id):
            continue
        if state.tool_approval_scopes.get(approval_id) == APPROVAL_ALLOW_FOR_RUN:
            state.tool_approval_grants[approval_grant_key(call)] = True


def pending_approval_events(state: RuntimeState, authorizations: Iterable) -> List[RuntimeEvent]:
    events: List[RuntimeEvent] = []
    for item in authorizations:
        approval_id = tool_approval_id(item.call)
        if approval_id in state.tool_approvals:
            continue
        if item.decision.requires_approval and approval_grant_key(item.call) in state.tool_approval_grants:
            continue
        if item.decision.requires_approval:
            events.append(tool_approval_required_event(item.call, item.decision))
    return events


def resolve_authorization_decisions(state: RuntimeState, authorizations: Iterable) -> ApprovalDecisionResolution:
    decisions: List[ToolPermissionDecision] = []
    events: List[RuntimeEvent] = []
    decided_call_ids: set[str] = set()
    for item in authorizations:
        approval_id = tool_approval_id(item.call)
        grant_key = approval_grant_key(item.call)
        if item.decision.requires_approval and approval_id in state.tool_approvals:
            approved = state.tool_approvals[approval_id]
            scope = state.tool_approval_scopes.get(approval_id, APPROVAL_ALLOW_ONCE if approved else APPROVAL_DENY)
            decided_call_ids.add(approval_id)
            if approved and scope == APPROVAL_ALLOW_FOR_RUN:
                state.tool_approval_grants[grant_key] = True
            events.append(
                tool_approval_decision_event(
                    item.call,
                    approved,
                    scope=scope,
                    grant_key=grant_key if scope == APPROVAL_ALLOW_FOR_RUN else "",
                )
            )
            decisions.append(
                ToolPermissionDecision(
                    allowed=approved,
                    reason="" if approved else "tool denied by user approval",
                    metadata={"source": "user_approval", "scope": scope, "grant_key": grant_key if scope == APPROVAL_ALLOW_FOR_RUN else ""},
                )
            )
            continue
        if item.decision.requires_approval and grant_key in state.tool_approval_grants:
            approved = state.tool_approval_grants[grant_key]
            events.append(
                tool_approval_decision_event(
                    item.call,
                    approved,
                    reason="run approval grant",
                    scope=APPROVAL_ALLOW_FOR_RUN,
                    grant_key=grant_key,
                )
            )
            decisions.append(
                ToolPermissionDecision(
                    allowed=approved,
                    reason="" if approved else "tool denied by run approval grant",
                    metadata={"source": "run_approval_grant", "scope": APPROVAL_ALLOW_FOR_RUN, "grant_key": grant_key},
                )
            )
            continue
        decisions.append(item.decision)
    return ApprovalDecisionResolution(decisions=decisions, events=events, decided_call_ids=decided_call_ids)
