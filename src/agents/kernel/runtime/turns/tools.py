from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Iterable, List

from agents.kernel.hooks import AgentHooks, ToolHookDenied
from agents.kernel.governance.permissions import AllowAllToolPermissionPolicy, ToolPermissionDecision, ToolPermissionPolicy
from agents.kernel.runtime.events import tool_result_event
from agents.kernel.schema import Message, RuntimeEvent, ToolCall, ToolResult
from agents.kernel.capabilities.tools.registry import ToolRegistry


@dataclass(frozen=True)
class ToolExecutionBatch:
    results: List[ToolResult]
    events: List[RuntimeEvent]
    messages: List[Message]


@dataclass(frozen=True)
class ToolAuthorization:
    call: ToolCall
    decision: ToolPermissionDecision


@dataclass(frozen=True)
class ToolExecutionPreparation:
    calls: List[ToolCall]
    executable_indexes: List[int]
    executable_calls: List[ToolCall]
    transformed_calls_by_index: dict[int, ToolCall]
    results_by_index: dict[int, ToolResult]


class ToolOrchestrator:
    """Executes model-requested tools and converts results back into history."""

    def __init__(
        self,
        registry: ToolRegistry,
        hooks: AgentHooks,
        permission_policy: ToolPermissionPolicy | None = None,
    ):
        self.registry = registry
        self.hooks = hooks
        self.permission_policy = permission_policy or AllowAllToolPermissionPolicy()

    async def execute(self, calls: Iterable[ToolCall]) -> ToolExecutionBatch:
        call_list = list(calls)
        authorizations = await self.authorize(call_list)
        return await self.execute_with_decisions(call_list, [item.decision for item in authorizations])

    async def authorize(self, calls: Iterable[ToolCall]) -> List[ToolAuthorization]:
        call_list = list(calls)
        decisions = await asyncio.gather(*(self.permission_policy.authorize(call) for call in call_list))
        return [ToolAuthorization(call=call, decision=decision) for call, decision in zip(call_list, decisions)]

    async def execute_with_decisions(
        self,
        calls: Iterable[ToolCall],
        decisions: Iterable[ToolPermissionDecision],
        *,
        run_id: str = "",
        task_id: str = "",
    ) -> ToolExecutionBatch:
        prepared = await self.prepare_with_decisions(calls, decisions)
        return await self.execute_prepared(prepared, run_id=run_id, task_id=task_id)

    async def prepare_with_decisions(
        self,
        calls: Iterable[ToolCall],
        decisions: Iterable[ToolPermissionDecision],
    ) -> ToolExecutionPreparation:
        call_list = list(calls)
        decision_list = list(decisions)
        executable_calls: List[ToolCall] = []
        executable_indexes: List[int] = []
        transformed_calls_by_index: dict[int, ToolCall] = {}
        results_by_index: dict[int, ToolResult] = {}

        for index, (call, decision) in enumerate(zip(call_list, decision_list)):
            if not decision.allowed:
                results_by_index[index] = _denied_result(call, decision)
                continue
            try:
                transformed = await self.hooks.before_tool_use(call)
            except ToolHookDenied as exc:
                results_by_index[index] = _hook_denied_result(call, exc)
                continue
            executable_indexes.append(index)
            executable_calls.append(transformed)
            transformed_calls_by_index[index] = transformed

        return ToolExecutionPreparation(
            calls=call_list,
            executable_indexes=executable_indexes,
            executable_calls=executable_calls,
            transformed_calls_by_index=transformed_calls_by_index,
            results_by_index=results_by_index,
        )

    async def execute_prepared(
        self,
        prepared: ToolExecutionPreparation,
        *,
        run_id: str = "",
        task_id: str = "",
    ) -> ToolExecutionBatch:
        results_by_index = dict(prepared.results_by_index)
        if prepared.executable_calls:
            allowed_results = await self.registry.execute_many(prepared.executable_calls, run_id=run_id, task_id=task_id)
            for index, result in zip(prepared.executable_indexes, allowed_results):
                results_by_index[index] = await self.hooks.after_tool_use(prepared.transformed_calls_by_index[index], result)

        results = [results_by_index[index] for index in range(len(prepared.calls))]
        return ToolExecutionBatch(
            results=results,
            events=[tool_result_event(result) for result in results],
            messages=[self.hooks.format_tool_result(result) for result in results],
        )


def _denied_result(call: ToolCall, decision: ToolPermissionDecision) -> ToolResult:
    reason = decision.reason or "tool call denied by permission policy"
    return ToolResult(
        tool_call_id=call.id,
        name=call.name,
        content=reason,
        is_error=True,
        raw={"permission": decision.to_dict(), "tool_call": call.to_dict()},
    )


def _hook_denied_result(call: ToolCall, error: ToolHookDenied) -> ToolResult:
    return ToolResult(
        tool_call_id=call.id,
        name=call.name,
        content=error.reason,
        is_error=True,
        raw={"hook": {"denied": True, "reason": error.reason}, "tool_call": call.to_dict()},
    )
