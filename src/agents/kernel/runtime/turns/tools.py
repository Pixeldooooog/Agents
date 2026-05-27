from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Iterable, List
from uuid import uuid4

from agents.kernel.hooks import AgentHooks, ToolHookDenied
from agents.kernel.governance.permissions import AllowAllToolPermissionPolicy, ToolPermissionDecision, ToolPermissionPolicy
from agents.kernel.runtime.events import tool_result_event
from agents.kernel.runtime.turns.tool_summary import ToolUseSummaryGenerator, build_tool_use_summary
from agents.kernel.schema import ContentBlock, Message, RuntimeEvent, ToolCall, ToolResult
from agents.kernel.capabilities.tools.registry import ToolRegistry


@dataclass(frozen=True)
class ToolExecutionBatch:
    results: List[ToolResult]
    events: List[RuntimeEvent]
    messages: List[Message]
    canceled: bool = False


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
    events: List[RuntimeEvent]


class ToolOrchestrator:
    """Executes model-requested tools and converts results back into history."""

    def __init__(
        self,
        registry: ToolRegistry,
        hooks: AgentHooks,
        permission_policy: ToolPermissionPolicy | None = None,
        tool_summary_generator: ToolUseSummaryGenerator | None = None,
    ):
        self.registry = registry
        self.hooks = hooks
        self.permission_policy = permission_policy or AllowAllToolPermissionPolicy()
        self.tool_summary_generator = tool_summary_generator

    def describe_call(self, call: ToolCall) -> dict:
        try:
            return self.registry.describe_call(call.name, dict(call.arguments))
        except KeyError:
            return {
                "name": call.name,
                "description": "",
                "activity": {"kind": "generic"},
                "target": "",
                "paths": [],
                "metadata": {},
            }

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
            events=self.hooks.drain_runtime_events(),
        )

    async def execute_prepared(
        self,
        prepared: ToolExecutionPreparation,
        *,
        run_id: str = "",
        task_id: str = "",
        include_preparation_events: bool = True,
        last_assistant_text: str = "",
    ) -> ToolExecutionBatch:
        results_by_index = dict(prepared.results_by_index)
        hook_events: List[RuntimeEvent] = []
        canceled = False
        if prepared.executable_calls:
            allowed_results = await self.registry.execute_many(prepared.executable_calls, run_id=run_id, task_id=task_id)
            for index, result in zip(prepared.executable_indexes, allowed_results):
                final_result = await self.hooks.after_tool_use(prepared.transformed_calls_by_index[index], result)
                hook_events.extend(self.hooks.drain_runtime_events())
                if _is_user_interrupted_result(final_result):
                    canceled = True
                results_by_index[index] = final_result

        results = [results_by_index[index] for index in range(len(prepared.calls))]
        result_events = list(prepared.events) if include_preparation_events else []
        result_events.extend(hook_events)
        for index, result in enumerate(results):
            call = prepared.transformed_calls_by_index.get(index, prepared.calls[index])
            result_events.append(tool_result_event(result, contract=self.describe_call(call)))
        summary_calls = [
            prepared.transformed_calls_by_index.get(index, prepared.calls[index])
            for index in range(len(prepared.calls))
        ]
        summary = await _tool_use_summary_event(
            self.tool_summary_generator,
            results,
            summary_calls,
            self.describe_call,
            last_assistant_text=last_assistant_text,
        )
        if summary is not None:
            result_events.append(summary)
        return ToolExecutionBatch(
            results=results,
            events=result_events,
            messages=_tool_result_messages(results, self.hooks),
            canceled=canceled,
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


def _is_user_interrupted_result(result: ToolResult) -> bool:
    raw = result.raw if isinstance(result.raw, dict) else {}
    return raw.get("error") == "tool_execution_canceled" and raw.get("cancel_reason") == "user_interrupted"


def _tool_result_messages(results: List[ToolResult], hooks: AgentHooks) -> List[Message]:
    messages: List[Message] = []
    for result in results:
        messages.append(hooks.format_tool_result(result))
        messages.extend(_supplemental_tool_result_messages(result))
    return messages


def _supplemental_tool_result_messages(result: ToolResult) -> List[Message]:
    raw = result.raw if isinstance(result.raw, dict) else {}
    raw_messages = raw.get("newMessages") if isinstance(raw.get("newMessages"), list) else raw.get("new_messages")
    if not isinstance(raw_messages, list):
        return []
    messages: List[Message] = []
    for item in raw_messages:
        if not isinstance(item, dict):
            continue
        blocks = [
            block
            for block in (_content_block_from_supplemental(raw_block) for raw_block in item.get("content") or [])
            if block is not None
        ]
        if not blocks:
            continue
        messages.append(
            Message(
                role=str(item.get("role") or "user"),
                content=blocks,
                raw={
                    "isMeta": bool(item.get("isMeta", item.get("is_meta", True))),
                    "source_tool_call_id": result.tool_call_id,
                    "source_tool": result.name,
                },
            )
        )
    return messages


def _content_block_from_supplemental(raw_block: Any) -> ContentBlock | None:
    if not isinstance(raw_block, dict):
        return None
    block_type = str(raw_block.get("type") or "")
    if block_type == "text":
        return ContentBlock.from_text(str(raw_block.get("text") or ""), raw=raw_block)
    if block_type == "image":
        source = raw_block.get("source") if isinstance(raw_block.get("source"), dict) else {}
        if not source:
            return None
        return ContentBlock(type="image", data={"source": dict(source)}, raw=raw_block)
    if block_type == "document":
        source = raw_block.get("source") if isinstance(raw_block.get("source"), dict) else {}
        if not source:
            return None
        return ContentBlock(type="document", data={"source": dict(source)}, raw=raw_block)
    return None


async def _tool_use_summary_event(
    generator: ToolUseSummaryGenerator | None,
    results: List[ToolResult],
    calls: List[ToolCall],
    contract_provider,
    *,
    last_assistant_text: str = "",
) -> RuntimeEvent | None:
    preceding_tool_use_ids = [result.tool_call_id for result in results if result.tool_call_id]
    if not preceding_tool_use_ids:
        return None
    summary = await build_tool_use_summary(
        generator,
        results,
        calls,
        contract_provider,
        last_assistant_text=last_assistant_text,
    )
    if summary is None:
        return None
    return RuntimeEvent(
        type="tool_use_summary",
        name="tools",
        payload={
            "summary": summary.summary,
            "summary_source": summary.source,
            "preceding_tool_use_ids": preceding_tool_use_ids,
            "uuid": str(uuid4()),
        },
    )
