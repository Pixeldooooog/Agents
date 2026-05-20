from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
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
    tool_inputs: Mapping[str, Mapping[str, object]] | None = None,
) -> None:
    if approvals:
        state.tool_approvals.update({str(key): bool(value) for key, value in approvals.items()})
    if approval_scopes:
        state.tool_approval_scopes.update({str(key): str(value) for key, value in approval_scopes.items()})
    if approval_grants:
        state.tool_approval_grants.update({str(key): bool(value) for key, value in approval_grants.items()})
    if tool_inputs:
        state.pending_tool_calls = _apply_tool_inputs(state.pending_tool_calls, tool_inputs)
    derive_run_grants_from_scopes(state)


def derive_run_grants_from_scopes(state: RuntimeState) -> None:
    for call in state.pending_tool_calls:
        approval_id = tool_approval_id(call)
        if not state.tool_approvals.get(approval_id):
            continue
        if state.tool_approval_scopes.get(approval_id) == APPROVAL_ALLOW_FOR_RUN:
            state.tool_approval_grants[approval_grant_key(call)] = True


def _apply_tool_inputs(calls, tool_inputs: Mapping[str, Mapping[str, object]]) -> list:
    updates = {str(key): dict(value) for key, value in tool_inputs.items() if isinstance(value, Mapping)}
    if not updates:
        return list(calls)
    result = []
    for call in calls:
        approval_id = tool_approval_id(call)
        update = updates.get(approval_id)
        if update is None:
            result.append(call)
            continue
        arguments = dict(call.arguments or {})
        arguments.update(update)
        result.append(replace(call, arguments=arguments))
    return result


ToolContractProvider = Callable[[object], dict]


def pending_approval_events(
    state: RuntimeState,
    authorizations: Iterable,
    contract_provider: ToolContractProvider | None = None,
) -> List[RuntimeEvent]:
    events: List[RuntimeEvent] = []
    for item in authorizations:
        approval_id = tool_approval_id(item.call)
        if approval_id in state.tool_approvals:
            continue
        if item.decision.requires_approval and approval_grant_key(item.call) in state.tool_approval_grants:
            continue
        if item.decision.requires_approval:
            events.append(tool_approval_required_event(item.call, item.decision, contract=_contract(contract_provider, item.call)))
    return events


def resolve_authorization_decisions(
    state: RuntimeState,
    authorizations: Iterable,
    contract_provider: ToolContractProvider | None = None,
) -> ApprovalDecisionResolution:
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
                    contract=_contract(contract_provider, item.call),
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
                    contract=_contract(contract_provider, item.call),
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


def _contract(contract_provider: ToolContractProvider | None, call: object) -> dict:
    if contract_provider is None:
        return {}
    return dict(contract_provider(call) or {})
