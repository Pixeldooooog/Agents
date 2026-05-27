from __future__ import annotations

import inspect
from typing import AsyncIterable, List, Mapping, Optional
from typing import Any

from agents.kernel.context.window import ContextWindowManager
from agents.kernel.context.workspace import WorkspaceContext
from agents.kernel.runtime.loop import AgentRuntime
from agents.kernel.runtime.session_compaction import compact_boundary_event, compact_stats
from agents.kernel.runtime.types import AgentResult
from agents.kernel.schema import Message, RuntimeEvent
from agents.kernel.context.pack import ContextTraceItem


class AgentSession:
    def __init__(
        self,
        runtime: AgentRuntime,
        system_prompt: str = "",
        max_context_tokens: int = 256000,
        compaction_target_tokens: int | None = None,
        context_trace: Optional[List[ContextTraceItem]] = None,
        workspace: Optional[WorkspaceContext] = None,
        tool_context: Any | None = None,
        context_compactor: Any | None = None,
    ):
        self.runtime = runtime
        self.context_trace = list(context_trace or [])
        self.workspace = workspace
        self.tool_context = tool_context
        if self.tool_context is not None:
            self.tool_context.session = self
        self.context_window = ContextWindowManager(
            system_prompt,
            max_context_tokens,
            compaction_target_tokens,
            compactor=context_compactor,
        )
        self.messages: List[Message] = []
        self.clear()

    @property
    def system_prompt(self) -> str:
        return self.context_window.system_prompt

    def set_system_prompt(self, text: str) -> None:
        self.context_window.system_prompt = str(text or "").strip()
        if self.messages and self.messages[0].role == "system":
            if self.context_window.system_prompt:
                self.messages[0] = Message.from_text("system", self.context_window.system_prompt)
            else:
                self.messages.pop(0)
        elif self.context_window.system_prompt:
            self.messages.insert(0, Message.from_text("system", self.context_window.system_prompt))

    @property
    def max_context_tokens(self) -> int:
        return self.context_window.max_context_tokens

    def clear(self) -> None:
        self.messages = self.context_window.initial_messages()

    def _estimate_tokens(self, messages: List[Message]) -> int:
        return self.context_window.estimate_tokens(messages)

    def _fit_with_boundary(self, messages: List[Message], *, trigger: str = "auto") -> tuple[List[Message], RuntimeEvent | None]:
        before_tokens = self._estimate_tokens(messages)
        fitted = self.context_window.fit(messages)
        after_tokens = self._estimate_tokens(fitted)
        return fitted, compact_boundary_event(
            messages,
            fitted,
            trigger=trigger,
            pre_tokens=before_tokens,
            post_tokens=after_tokens,
        )

    async def _afit_with_boundary(self, messages: List[Message], *, trigger: str = "auto") -> tuple[List[Message], RuntimeEvent | None]:
        before_tokens = self._estimate_tokens(messages)
        fitted = await self.context_window.afit(messages)
        after_tokens = self._estimate_tokens(fitted)
        return fitted, compact_boundary_event(
            messages,
            fitted,
            trigger=trigger,
            pre_tokens=before_tokens,
            post_tokens=after_tokens,
        )

    def compact(self, target_tokens: int | None = None) -> dict[str, int]:
        before_messages = len(self.messages)
        before_tokens = self._estimate_tokens(self.messages)
        self.messages = self.context_window.compact(self.messages, target_tokens)
        after_tokens = self._estimate_tokens(self.messages)
        return compact_stats(
            before_messages=before_messages,
            before_tokens=before_tokens,
            after_messages=len(self.messages),
            after_tokens=after_tokens,
        )

    async def async_compact(self, target_tokens: int | None = None) -> dict[str, int]:
        before_messages = len(self.messages)
        before_tokens = self._estimate_tokens(self.messages)
        self.messages = await self.context_window.acompact(self.messages, target_tokens)
        after_tokens = self._estimate_tokens(self.messages)
        return compact_stats(
            before_messages=before_messages,
            before_tokens=before_tokens,
            after_messages=len(self.messages),
            after_tokens=after_tokens,
        )

    async def aclose(self) -> None:
        first_error: Exception | None = None
        tool_context = getattr(self, "tool_context", None)
        if tool_context is not None:
            try:
                from agents.kernel.mcp.oauth_runtime import close_mcp_oauth_waiters

                await close_mcp_oauth_waiters(tool_context)
            except Exception as exc:
                if first_error is None:
                    first_error = exc
        providers = list(getattr(tool_context, "mcp_providers", []) or []) if tool_context is not None else []
        for provider in providers:
            close_provider = getattr(provider, "close", None)
            if close_provider is None:
                continue
            try:
                result = close_provider()
                if inspect.isawaitable(result):
                    await result
            except Exception as exc:
                if first_error is None:
                    first_error = exc
        if tool_context is not None:
            tool_context.mcp_providers = []

        model_client = getattr(self.runtime, "model_client", None)
        close = getattr(model_client, "async_close", None)
        if close is not None:
            try:
                await close()
            except Exception as exc:
                if first_error is None:
                    first_error = exc
        summary_generator = getattr(getattr(self.runtime, "tool_orchestrator", None), "tool_summary_generator", None)
        close = getattr(summary_generator, "async_close", None)
        if close is not None and getattr(summary_generator, "model_client", None) is not model_client:
            try:
                await close()
            except Exception as exc:
                if first_error is None:
                    first_error = exc
        context_compactor = getattr(self.context_window, "compactor", None)
        close = getattr(context_compactor, "async_close", None)
        if close is not None and getattr(context_compactor, "model_client", None) is not model_client:
            try:
                await close()
            except Exception as exc:
                if first_error is None:
                    first_error = exc
        if first_error is not None:
            raise first_error

    async def send(self, text: str, run_id: str | None = None, task_id: str | None = None) -> AgentResult:
        candidate = self.messages + [Message.from_text("user", text)]
        candidate = await self.context_window.afit(candidate)
        result = await self.runtime.run(candidate, run_id=run_id, task_id=task_id)
        self.messages = list(result.messages)
        return result

    async def resume(
        self,
        run_id: str,
        approvals: Mapping[str, bool] | None = None,
        approval_scopes: Mapping[str, str] | None = None,
        approval_grants: Mapping[str, bool] | None = None,
        tool_inputs: Mapping[str, Mapping[str, object]] | None = None,
        task_id: str | None = None,
    ) -> AgentResult:
        result = await self.runtime.resume(
            run_id,
            approvals=approvals,
            approval_scopes=approval_scopes,
            approval_grants=approval_grants,
            tool_inputs=tool_inputs,
            task_id=task_id,
        )
        self.messages = list(result.messages)
        return result

    async def resume_stream(
        self,
        run_id: str,
        approvals: Mapping[str, bool] | None = None,
        approval_scopes: Mapping[str, str] | None = None,
        approval_grants: Mapping[str, bool] | None = None,
        tool_inputs: Mapping[str, Mapping[str, object]] | None = None,
        task_id: str | None = None,
    ) -> AsyncIterable[RuntimeEvent]:
        async for event in self.runtime.resume_stream(
            run_id,
            approvals=approvals,
            approval_scopes=approval_scopes,
            approval_grants=approval_grants,
            tool_inputs=tool_inputs,
            task_id=task_id,
        ):
            yield event
            if event.type == "done" and event.payload.get("messages"):
                self.messages = [Message.from_dict(message) for message in event.payload["messages"]]

    async def stream(
        self,
        text: str,
        run_id: str | None = None,
        task_id: str | None = None,
    ) -> AsyncIterable[RuntimeEvent]:
        candidate = self.messages + [Message.from_text("user", text)]
        candidate, boundary_event = await self._afit_with_boundary(candidate)
        if boundary_event is not None:
            yield boundary_event
        async for event in self.runtime.stream(candidate, run_id=run_id, task_id=task_id):
            yield event
            if event.type == "done" and event.payload.get("messages"):
                self.messages = [Message.from_dict(message) for message in event.payload["messages"]]
