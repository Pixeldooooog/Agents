# !/usr/bin/env python
# -*- coding: utf-8 -*-
# =====================================================
# @File   ：registry.py
# @Date   ：2026/04/24 00:00
# @Author ：Zegen
#
# 2026/04/24   Create
# =====================================================

from __future__ import annotations

import asyncio
import contextvars
import inspect
import time
from contextlib import contextmanager
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional

from agents.kernel.capabilities.tools.contracts import (
    RegisteredTool,
    ToolActivity,
    ToolDefinition,
    ToolExecutionError,
    ToolHandler,
    ToolResultFormatter,
    extract_contract_paths,
    format_contract_value,
)
from agents.kernel.capabilities.tools.recording import ToolExecutionObserver, ToolExecutionScope
from agents.kernel.capabilities.tools.results import cancelled_tool_result, tool_error_payload, tool_result_payload, with_metadata
from agents.kernel.capabilities.tools.validation import validate_tool_arguments
from agents.kernel.schema import RuntimeEvent, ToolCall, ToolResult, ToolSpec


__all__ = [
    "RegisteredTool",
    "ToolActivity",
    "ToolDefinition",
    "ToolExecutionError",
    "ToolHandler",
    "ToolRegistry",
    "ToolResultFormatter",
]


class ToolRegistry:
    def __init__(
        self,
        max_concurrent: int = 10,
        tool_timeout: float = 60.0,
        execution_observer: ToolExecutionObserver | None = None,
    ):
        self._tools: Dict[str, ToolDefinition] = {}
        self._max_concurrent = max_concurrent
        self._semaphores: Dict[int, asyncio.Semaphore] = {}
        self._tool_timeout = tool_timeout
        self._execution_observer = execution_observer
        self._runtime_event_sink: contextvars.ContextVar[Callable[[RuntimeEvent], None] | None] = contextvars.ContextVar(
            "tool_runtime_event_sink_%s" % id(self),
            default=None,
        )
        self._runtime_event_scope: contextvars.ContextVar[ToolExecutionScope | None] = contextvars.ContextVar(
            "tool_runtime_event_scope_%s" % id(self),
            default=None,
        )

    def set_execution_observer(self, observer: ToolExecutionObserver | None) -> None:
        self._execution_observer = observer

    def has_runtime_event_sink(self) -> bool:
        return self._runtime_event_sink.get() is not None

    @contextmanager
    def runtime_event_sink(self, sink: Callable[[RuntimeEvent], None] | None) -> Iterator[None]:
        token = self._runtime_event_sink.set(sink)
        try:
            yield
        finally:
            self._runtime_event_sink.reset(token)

    def emit_runtime_event(self, event: RuntimeEvent) -> None:
        sink = self._runtime_event_sink.get()
        if sink is None:
            return
        scope = self._runtime_event_scope.get()
        if scope is None:
            sink(event)
            return
        payload = dict(event.payload or {})
        payload.setdefault("tool_call_id", scope.tool_call_id)
        payload.setdefault("tool_name", scope.tool_name)
        sink(
            RuntimeEvent(
                type=event.type,
                name=event.name or scope.tool_name,
                payload=payload,
                raw=event.raw,
            )
        )

    def register(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        handler: ToolHandler,
        metadata: Dict[str, Any] | None = None,
    ) -> None:
        self.register_definition(
            RegisteredTool.from_legacy(name, description, parameters, handler, metadata),
        )

    def register_definition(self, definition: ToolDefinition) -> None:
        if definition.name in self._tools:
            raise ValueError("tool already registered: %s" % definition.name)
        self._tools[definition.name] = definition

    def unregister_matching(self, predicate: Callable[[ToolDefinition], bool]) -> List[str]:
        removed: list[str] = []
        for name, definition in list(self._tools.items()):
            if predicate(definition):
                removed.append(name)
                self._tools.pop(name, None)
        return sorted(removed)

    def definitions_matching(self, predicate: Callable[[ToolDefinition], bool]) -> List[ToolDefinition]:
        return [definition for _name, definition in sorted(self._tools.items()) if predicate(definition)]

    def names(self) -> List[str]:
        return sorted(self._tools)

    def specs(self, names: Optional[Iterable[str]] = None) -> List[ToolSpec]:
        selected = list(names) if names is not None else self.names()
        return [self._spec_for(name) for name in selected]

    def describe_call(self, name: str, arguments: Dict[str, Any] | None = None) -> Dict[str, Any]:
        if name not in self._tools:
            raise KeyError("unknown tool: %s" % name)
        tool = self._tools[name]
        payload = dict(arguments or {})
        activity = tool.activity.to_dict()
        target = ""
        if tool.activity.target_argument:
            target = format_contract_value(payload.get(tool.activity.target_argument))
        return {
            "name": tool.name,
            "description": tool.description,
            "activity": activity,
            "target": target,
            "paths": extract_contract_paths(tool, payload),
            "metadata": tool.spec_metadata(),
        }

    async def execute(
        self,
        name: str,
        arguments: Dict[str, Any],
        *,
        run_id: str = "",
        task_id: str = "",
        tool_call_id: str = "",
    ) -> ToolResult:
        if name not in self._tools:
            return ToolResult(tool_call_id="", name=name, content="unknown tool: %s" % name, is_error=True)
        tool = self._tools[name]
        validation_error = validate_tool_arguments(tool, arguments)
        if validation_error:
            return ToolResult(
                tool_call_id="",
                name=name,
                content="invalid tool input: %s" % validation_error,
                is_error=True,
                raw={
                    "error": "invalid_tool_input",
                    "details": validation_error,
                    "arguments": dict(arguments),
                },
            )
        scope = ToolExecutionScope(
            run_id=str(run_id or ""),
            task_id=str(task_id or ""),
            tool_call_id=str(tool_call_id or ""),
            tool_name=name,
        )
        started_at = time.perf_counter()
        await self._before_tool(scope, arguments)
        scope_token = self._runtime_event_scope.set(scope)
        try:
            async with self._semaphore_for_running_loop():
                result = await asyncio.wait_for(
                    _call_handler(tool.handler, arguments),
                    timeout=self._tool_timeout,
                )
            metadata = await self._after_tool(scope, arguments, result=result, duration_ms=_duration_ms(started_at))
            content, raw = tool_result_payload(tool, result, metadata)
            return ToolResult(
                tool_call_id="",
                name=name,
                content=content,
                raw=raw,
            )
        except asyncio.CancelledError:
            await self._after_tool(
                scope,
                arguments,
                is_error=True,
                error="tool execution canceled",
                duration_ms=_duration_ms(started_at),
            )
            raise
        except asyncio.TimeoutError:
            metadata = await self._after_tool(
                scope,
                arguments,
                is_error=True,
                error="tool execution timed out",
                duration_ms=_duration_ms(started_at),
            )
            return ToolResult(
                tool_call_id="",
                name=name,
                content="tool execution timed out",
                is_error=True,
                raw=with_metadata(None, metadata),
            )
        except ToolExecutionError as exc:
            metadata = await self._after_tool(
                scope,
                arguments,
                is_error=True,
                error=exc.content,
                duration_ms=_duration_ms(started_at),
            )
            content, raw = tool_error_payload(tool, exc, metadata)
            return ToolResult(
                tool_call_id="",
                name=name,
                content=content,
                is_error=True,
                raw=raw,
            )
        except Exception as exc:  # noqa: BLE001 - tool failures are model-visible tool results.
            metadata = await self._after_tool(
                scope,
                arguments,
                is_error=True,
                error=str(exc),
                duration_ms=_duration_ms(started_at),
            )
            return ToolResult(
                tool_call_id="",
                name=name,
                content=str(exc),
                is_error=True,
                raw=with_metadata(None, metadata),
            )
        finally:
            self._runtime_event_scope.reset(scope_token)

    async def execute_many(
        self,
        calls: Iterable[ToolCall],
        *,
        run_id: str = "",
        task_id: str = "",
    ) -> List[ToolResult]:
        call_list = list(calls)

        async def run(call: ToolCall) -> ToolResult:
            result = await self.execute(
                call.name,
                dict(call.arguments),
                run_id=run_id,
                task_id=task_id,
                tool_call_id=call.id,
            )
            return ToolResult(
                tool_call_id=call.id,
                name=call.name,
                content=result.content,
                is_error=result.is_error,
                raw=result.raw,
            )

        if self._requires_sequential_execution(call_list):
            return await self._execute_many_sequential(call_list, run)
        return await self._execute_many_concurrent(call_list, run)

    async def _execute_many_sequential(
        self,
        calls: List[ToolCall],
        run,
    ) -> List[ToolResult]:
        results: list[ToolResult] = []
        for index, call in enumerate(calls):
            task = asyncio.create_task(run(call))
            try:
                if self._blocks_interrupt(call):
                    results.append(await asyncio.shield(task))
                else:
                    results.append(await task)
            except asyncio.CancelledError as exc:
                if _is_interrupt_cancel(exc) and self._blocks_interrupt(call):
                    results.append(await task)
                    continue
                if not task.done():
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
                results.append(cancelled_tool_result(call, cancel_reason="user_interrupted"))
                for remaining in calls[index + 1 :]:
                    results.append(cancelled_tool_result(remaining, cancel_reason="user_interrupted"))
                return results
        return results

    async def _execute_many_concurrent(
        self,
        calls: List[ToolCall],
        run,
    ) -> List[ToolResult]:
        if not calls:
            return []
        results: list[ToolResult | None] = [None] * len(calls)
        tasks = {asyncio.create_task(run(call)): index for index, call in enumerate(calls)}
        pending = set(tasks)
        cancel_trigger: tuple[int, ToolResult] | None = None

        try:
            while pending:
                done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    index = tasks[task]
                    call = calls[index]
                    try:
                        result = task.result()
                    except asyncio.CancelledError:
                        result = cancelled_tool_result(
                            call,
                            canceled_by=cancel_trigger[1] if cancel_trigger else None,
                        )
                    results[index] = result
                    if result.is_error and self._cancels_siblings(call):
                        cancel_trigger = (index, result)
                if cancel_trigger and pending:
                    for task in pending:
                        task.cancel()
                    await asyncio.gather(*pending, return_exceptions=True)
                    for task in list(pending):
                        index = tasks[task]
                        if results[index] is None:
                            results[index] = cancelled_tool_result(
                                calls[index],
                                canceled_by=cancel_trigger[1],
                                cancel_reason="sibling_error",
                            )
                    pending = set()
        except asyncio.CancelledError as exc:
            if _is_interrupt_cancel(exc):
                cancelable = {task for task in pending if not self._blocks_interrupt(calls[tasks[task]])}
                blocking = pending - cancelable
            else:
                cancelable = set(pending)
                blocking = set()
            for task in cancelable:
                task.cancel()
            await asyncio.gather(*cancelable, return_exceptions=True)
            for task in list(cancelable):
                index = tasks[task]
                if results[index] is None:
                    results[index] = cancelled_tool_result(calls[index], cancel_reason="user_interrupted")
            for task in list(blocking):
                index = tasks[task]
                if results[index] is None:
                    try:
                        results[index] = await task
                    except asyncio.CancelledError:
                        results[index] = cancelled_tool_result(calls[index], cancel_reason="tool_cancelled")

        return [result for result in results if result is not None]

    def _spec_for(self, name: str) -> ToolSpec:
        if name not in self._tools:
            raise KeyError("unknown tool: %s" % name)
        tool = self._tools[name]
        metadata = tool.spec_metadata()
        return ToolSpec(
            name=tool.name,
            description=tool.description,
            parameters=tool.parameters,
            source="registry",
            raw={"metadata": metadata} if metadata else None,
        )

    def _requires_sequential_execution(self, calls: Iterable[ToolCall]) -> bool:
        for call in calls:
            tool = self._tools.get(call.name)
            if tool is not None and (tool.writes_state or not tool.concurrency_safe):
                return True
        return False

    def _cancels_siblings(self, call: ToolCall) -> bool:
        tool = self._tools.get(call.name)
        return tool is not None and tool.cancels_siblings_on_error

    def _blocks_interrupt(self, call: ToolCall) -> bool:
        tool = self._tools.get(call.name)
        if tool is None:
            return True
        return str(tool.interrupt_behavior or "block") != "cancel"

    def _semaphore_for_running_loop(self) -> asyncio.Semaphore:
        loop = asyncio.get_running_loop()
        key = id(loop)
        semaphore = self._semaphores.get(key)
        if semaphore is None:
            semaphore = asyncio.Semaphore(self._max_concurrent)
            self._semaphores[key] = semaphore
        return semaphore

    async def _before_tool(self, scope: ToolExecutionScope, arguments: Dict[str, Any]) -> dict[str, Any]:
        if self._execution_observer is None:
            return {}
        return await self._execution_observer.before_tool(scope, dict(arguments))

    async def _after_tool(
        self,
        scope: ToolExecutionScope,
        arguments: Dict[str, Any],
        *,
        result: Any = None,
        is_error: bool = False,
        error: str = "",
        duration_ms: float = 0.0,
    ) -> dict[str, Any]:
        if self._execution_observer is None:
            return {}
        return await self._execution_observer.after_tool(
            scope,
            dict(arguments),
            result=result,
            is_error=is_error,
            error=error,
            duration_ms=duration_ms,
        )


async def _call_handler(handler: ToolHandler, arguments: Dict[str, Any]) -> Any:
    result = handler(**arguments)
    if inspect.isawaitable(result):
        result = await result
    return result


def _is_interrupt_cancel(exc: asyncio.CancelledError) -> bool:
    return bool(exc.args) and str(exc.args[0]) == "interrupt"


def _duration_ms(started_at: float) -> float:
    return round((time.perf_counter() - started_at) * 1000, 3)
