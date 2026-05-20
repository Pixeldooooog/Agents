from __future__ import annotations

from dataclasses import dataclass
from typing import AsyncIterable, List, Mapping, Optional

from agents.kernel.hooks import AgentHooks
from agents.kernel.models.errors import ModelClientError
from agents.kernel.runtime.checkpoints import CheckpointStore, NullCheckpointStore, RuntimeCheckpoint
from agents.kernel.runtime.config import RuntimeConfig
from agents.kernel.runtime.errors import AgentRuntimeError
from agents.kernel.runtime.approvals import apply_approval_updates, pending_approval_events, resolve_authorization_decisions
from agents.kernel.runtime.events import (
    done_event,
    error_event,
    model_message_event,
    tool_start_event,
)
from agents.kernel.governance.permissions import ToolPermissionPolicy
from agents.kernel.context.compiler import ModelRequestCompiler
from agents.kernel.runtime.state import RuntimeState
from agents.kernel.runtime.turns import ModelTurnRunner, ToolOrchestrator
from agents.kernel.runtime.types import AgentResult, ModelClientProtocol
from agents.kernel.schema import Message, ModelResponse, RuntimeEvent, ToolCall
from agents.kernel.capabilities.tools.registry import ToolRegistry


@dataclass(frozen=True)
class ToolExecutionOutcome:
    events: List[RuntimeEvent]
    approval_required: bool = False
    canceled: bool = False


class AgentRuntime:
    def __init__(
        self,
        model_client: ModelClientProtocol,
        tools: ToolRegistry,
        protocol: str,
        model: str,
        enabled_tools: List[str] = None,
        max_tool_iterations: int | None = 0,
        hooks: Optional[AgentHooks] = None,
        permission_policy: Optional[ToolPermissionPolicy] = None,
        checkpoint_store: Optional[CheckpointStore] = None,
    ):
        self.model_client = model_client
        self.tools = tools
        self.config = RuntimeConfig(
            protocol=protocol,
            model=model,
            enabled_tools=list(enabled_tools or []),
            max_tool_iterations=max_tool_iterations,
        )
        self.hooks = hooks or AgentHooks()
        self.model_request_compiler = ModelRequestCompiler(tools)
        self.model_turn_runner = ModelTurnRunner(self.model_client, self.model_request_compiler, self.hooks)
        self.tool_orchestrator = ToolOrchestrator(tools, self.hooks, permission_policy=permission_policy)
        self.checkpoints = checkpoint_store or NullCheckpointStore()

    @property
    def protocol(self) -> str:
        return self.config.protocol

    @property
    def model(self) -> str:
        return self.config.model

    @property
    def enabled_tools(self) -> List[str]:
        return list(self.config.enabled_tools)

    @property
    def max_tool_iterations(self) -> int | None:
        return self.config.max_tool_iterations

    async def run(self, messages: List[Message], run_id: str | None = None, task_id: str | None = None) -> AgentResult:
        return await self._run_state(RuntimeState.from_messages(messages), run_id=run_id, task_id=task_id)

    async def resume(
        self,
        run_id: str,
        approvals: Mapping[str, bool] | None = None,
        approval_scopes: Mapping[str, str] | None = None,
        approval_grants: Mapping[str, bool] | None = None,
        tool_inputs: Mapping[str, Mapping[str, object]] | None = None,
        task_id: str | None = None,
    ) -> AgentResult:
        checkpoint = await self.checkpoints.load(run_id)
        if checkpoint is None:
            raise AgentRuntimeError("checkpoint not found: %s" % run_id)
        state = checkpoint.to_state()
        apply_approval_updates(state, approvals, approval_scopes, approval_grants, tool_inputs)
        return await self._run_state(state, run_id=run_id, task_id=task_id)

    async def _run_state(
        self,
        state: RuntimeState,
        run_id: str | None = None,
        task_id: str | None = None,
    ) -> AgentResult:
        try:
            if state.pending_tool_calls:
                outcome = await self._execute_pending_tools(state, run_id, task_id)
                if outcome.approval_required:
                    return self._approval_result(state)
                if outcome.canceled:
                    return self._canceled_result(state)
                state.iteration += 1

            while self._can_continue_tool_loop(state):
                response = await self._complete_once(state.messages)
                calls = await self._apply_model_response(state, response, run_id)
                if not calls:
                    return AgentResult(response.content_text(), state.messages, state.tool_results, state.events)
                outcome = await self._execute_pending_tools(state, run_id, task_id)
                if outcome.approval_required:
                    return self._approval_result(state)
                if outcome.canceled:
                    return self._canceled_result(state)
                state.iteration += 1
        except ModelClientError as exc:
            recovery = await self.hooks.on_error(exc, state.messages)
            if recovery is not None:
                return recovery
            error_msg = "model error: %s" % exc
            await self._record_error(state, run_id, "model", error_msg)
            return AgentResult(error_msg, state.messages, state.tool_results, state.events)
        except AgentRuntimeError as exc:
            recovery = await self.hooks.on_error(exc, state.messages)
            if recovery is not None:
                return recovery
            error_msg = str(exc)
            await self._record_error(state, run_id, "runtime", error_msg)
            return AgentResult(error_msg, state.messages, state.tool_results, state.events)
        except Exception as exc:
            recovery = await self.hooks.on_error(exc, state.messages)
            if recovery is not None:
                return recovery
            error_msg = "unexpected error: %s" % exc
            await self._record_error(state, run_id, "runtime", error_msg)
            return AgentResult(error_msg, state.messages, state.tool_results, state.events)
        error_msg = "tool-call loop exceeded max iterations"
        await self._record_error(state, run_id, "runtime", error_msg)
        return AgentResult(error_msg, state.messages, state.tool_results, state.events)

    async def stream(
        self,
        messages: List[Message],
        run_id: str | None = None,
        task_id: str | None = None,
    ) -> AsyncIterable[RuntimeEvent]:
        state = RuntimeState.from_messages(messages)
        async for event in self._stream_state(state, run_id=run_id, task_id=task_id):
            yield event

    async def resume_stream(
        self,
        run_id: str,
        approvals: Mapping[str, bool] | None = None,
        approval_scopes: Mapping[str, str] | None = None,
        approval_grants: Mapping[str, bool] | None = None,
        tool_inputs: Mapping[str, Mapping[str, object]] | None = None,
        task_id: str | None = None,
    ) -> AsyncIterable[RuntimeEvent]:
        checkpoint = await self.checkpoints.load(run_id)
        if checkpoint is None:
            message = "checkpoint not found: %s" % run_id
            yield error_event("runtime", message)
            yield done_event(message, [], 0, error=message, status="error")
            return
        state = checkpoint.to_state()
        apply_approval_updates(state, approvals, approval_scopes, approval_grants, tool_inputs)
        async for event in self._stream_state(state, run_id=run_id, task_id=task_id):
            yield event

    async def _stream_state(
        self,
        state: RuntimeState,
        run_id: str | None = None,
        task_id: str | None = None,
    ) -> AsyncIterable[RuntimeEvent]:
        error_msg = None
        terminal_status = "finished"
        terminal_content = ""
        try:
            if state.pending_tool_calls:
                outcome = await self._execute_pending_tools(state, run_id, task_id)
                for event in outcome.events:
                    yield event
                if outcome.approval_required:
                    terminal_status = "awaiting_approval"
                    terminal_content = "tool approval required"
                    return
                if outcome.canceled:
                    terminal_status = "canceled"
                    terminal_content = "run canceled"
                    return
                state.iteration += 1

            while self._can_continue_tool_loop(state):
                final_response = None
                async for update in self.model_turn_runner.stream(state.messages, self.config):
                    if update.event is not None:
                        yield update.event
                    if update.response is not None:
                        final_response = update.response
                if final_response is None:
                    raise AgentRuntimeError("model stream did not include final message")

                calls = await self._apply_model_response(state, final_response, run_id)
                if not calls:
                    terminal_content = final_response.content_text()
                    return
                outcome = await self._execute_pending_tools(state, run_id, task_id)
                for event in outcome.events:
                    yield event
                if outcome.approval_required:
                    terminal_status = "awaiting_approval"
                    terminal_content = "tool approval required"
                    return
                if outcome.canceled:
                    terminal_status = "canceled"
                    terminal_content = "run canceled"
                    return
                state.iteration += 1
            error_msg = "tool-call loop exceeded max iterations"
            yield await self._record_error(state, run_id, "runtime", error_msg)
        except ModelClientError as exc:
            error_msg = "model error: %s" % exc
            yield await self._record_error(state, run_id, "model", error_msg)
        except AgentRuntimeError as exc:
            error_msg = str(exc)
            yield await self._record_error(state, run_id, "runtime", error_msg)
        except Exception as exc:
            error_msg = "unexpected error: %s" % exc
            yield await self._record_error(state, run_id, "runtime", error_msg)
        finally:
            yield done_event(
                error_msg or terminal_content or (state.messages[-1].content_text() if state.messages else ""),
                state.messages,
                len(state.events),
                error=error_msg,
                status="error" if error_msg else terminal_status,
            )

    async def _complete_once(self, messages: List[Message]) -> ModelResponse:
        return await self.model_turn_runner.complete(messages, self.config)

    def _can_continue_tool_loop(self, state: RuntimeState) -> bool:
        limit = self.config.max_tool_iterations
        return limit is None or limit <= 0 or state.iteration < limit

    async def _apply_model_response(
        self,
        state: RuntimeState,
        response: ModelResponse,
        run_id: str | None,
    ) -> List[ToolCall]:
        state.messages.append(response.message)
        state.events.append(model_message_event(response))
        calls = response.tool_calls
        if not calls:
            await self._save_checkpoint(run_id, "finished", state)
            return []
        state.pending_tool_calls = list(calls)
        await self._save_checkpoint(run_id, "model_response", state)
        return calls

    async def _execute_pending_tools(
        self,
        state: RuntimeState,
        run_id: str | None,
        task_id: str | None = None,
    ) -> ToolExecutionOutcome:
        if not state.pending_tool_calls:
            return ToolExecutionOutcome([])
        emitted: List[RuntimeEvent] = []
        authorizations = await self.tool_orchestrator.authorize(state.pending_tool_calls)
        approval_events = pending_approval_events(
            state,
            authorizations,
            contract_provider=self.tool_orchestrator.describe_call,
        )
        if approval_events:
            state.events.extend(approval_events)
            await self._save_checkpoint(run_id, "approval_required", state)
            return ToolExecutionOutcome(approval_events, approval_required=True)

        approval_resolution = resolve_authorization_decisions(
            state,
            authorizations,
            contract_provider=self.tool_orchestrator.describe_call,
        )
        state.events.extend(approval_resolution.events)
        emitted.extend(approval_resolution.events)
        decisions = approval_resolution.decisions

        prepared = await self.tool_orchestrator.prepare_with_decisions(state.pending_tool_calls, decisions)

        for call in prepared.executable_calls:
            event = tool_start_event(call, contract=self.tool_orchestrator.describe_call(call))
            state.events.append(event)
            emitted.append(event)
        batch = await self.tool_orchestrator.execute_prepared(
            prepared,
            run_id=run_id or "",
            task_id=task_id or "",
        )
        state.tool_results.extend(batch.results)
        state.events.extend(batch.events)
        emitted.extend(batch.events)
        state.messages.extend(batch.messages)
        for approval_id in approval_resolution.decided_call_ids:
            state.tool_approvals.pop(approval_id, None)
            state.tool_approval_scopes.pop(approval_id, None)
        state.pending_tool_calls = []
        await self._save_checkpoint(run_id, "canceled" if batch.canceled else "tool_results", state)
        return ToolExecutionOutcome(emitted, canceled=batch.canceled)

    async def _record_error(
        self,
        state: RuntimeState,
        run_id: str | None,
        kind: str,
        message: str,
    ) -> RuntimeEvent:
        event = error_event(kind, message)
        state.events.append(event)
        await self._save_checkpoint(run_id, "error", state)
        return event

    async def _save_checkpoint(self, run_id: str | None, step: str, state: RuntimeState) -> None:
        if run_id is None:
            return
        await self.checkpoints.save(RuntimeCheckpoint.from_state(run_id, step, state))

    def _approval_result(self, state: RuntimeState) -> AgentResult:
        return AgentResult(
            "tool approval required",
            state.messages,
            state.tool_results,
            state.events,
            status="awaiting_approval",
        )

    def _canceled_result(self, state: RuntimeState) -> AgentResult:
        return AgentResult(
            "run canceled",
            state.messages,
            state.tool_results,
            state.events,
            status="canceled",
        )
