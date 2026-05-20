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
import inspect
import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional

from agents.kernel.schema import ToolCall, ToolResult, ToolSpec
from agents.kernel.capabilities.tools.recording import ToolExecutionObserver, ToolExecutionScope

ToolHandler = Callable[..., Any]
ToolResultFormatter = Callable[[Any], str]


class ToolExecutionError(Exception):
    def __init__(self, content: str, raw: Any = None):
        super().__init__(content)
        self.content = str(content or "")
        self.raw = raw


@dataclass(frozen=True)
class ToolActivity:
    kind: str = "generic"
    title: str = ""
    target_argument: str = ""
    summary: str = ""

    @classmethod
    def from_dict(cls, payload: Dict[str, Any] | None) -> "ToolActivity":
        if not payload:
            return cls()
        return cls(
            kind=str(payload.get("kind") or "generic"),
            title=str(payload.get("title") or ""),
            target_argument=str(payload.get("target_argument") or ""),
            summary=str(payload.get("summary") or ""),
        )

    def to_dict(self) -> Dict[str, Any]:
        payload = {"kind": self.kind}
        if self.title:
            payload["title"] = self.title
        if self.target_argument:
            payload["target_argument"] = self.target_argument
        if self.summary:
            payload["summary"] = self.summary
        return payload


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    parameters: Dict[str, Any]
    handler: ToolHandler
    metadata: Dict[str, Any] = field(default_factory=dict)
    read_only: bool = False
    destructive: bool = False
    writes_state: bool = False
    concurrency_safe: bool = True
    interrupt_behavior: str = "block"
    cancels_siblings_on_error: bool = False
    max_result_size_chars: int | None = None
    strict_input_schema: bool = True
    path_parameters: tuple[str, ...] = field(default_factory=tuple)
    activity: ToolActivity = field(default_factory=ToolActivity)
    result_formatter: ToolResultFormatter | None = None

    @classmethod
    def from_legacy(
        cls,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        handler: ToolHandler,
        metadata: Dict[str, Any] | None = None,
    ) -> "ToolDefinition":
        payload = dict(metadata or {})
        writes_state = bool(payload.get("writes_state", False))
        concurrency_safe = bool(payload.get("concurrency_safe", not writes_state))
        max_result_size = payload.get("max_result_size_chars")
        if max_result_size is not None:
            max_result_size = int(max_result_size)
        path_parameters = _coerce_string_tuple(payload.get("path_parameters"))
        return cls(
            name=name,
            description=description,
            parameters=dict(parameters or {}),
            handler=handler,
            metadata=payload,
            read_only=bool(payload.get("read_only", False)),
            destructive=bool(payload.get("destructive", False)),
            writes_state=writes_state,
            concurrency_safe=concurrency_safe,
            interrupt_behavior=str(payload.get("interrupt_behavior") or "block"),
            cancels_siblings_on_error=bool(payload.get("cancels_siblings_on_error", False)),
            max_result_size_chars=max_result_size,
            strict_input_schema=bool(payload.get("strict_input_schema", True)),
            path_parameters=path_parameters,
            activity=ToolActivity.from_dict(payload.get("activity") if isinstance(payload.get("activity"), dict) else None),
        )

    def spec_metadata(self) -> Dict[str, Any]:
        metadata = dict(self.metadata or {})
        if self.read_only:
            metadata["read_only"] = True
        if self.destructive:
            metadata["destructive"] = True
        if self.writes_state:
            metadata["writes_state"] = True
        if not self.concurrency_safe:
            metadata["concurrency_safe"] = False
        if self.interrupt_behavior != "block":
            metadata["interrupt_behavior"] = self.interrupt_behavior
        if self.cancels_siblings_on_error:
            metadata["cancels_siblings_on_error"] = True
        if self.max_result_size_chars is not None:
            metadata["max_result_size_chars"] = self.max_result_size_chars
        if not self.strict_input_schema:
            metadata["strict_input_schema"] = False
        if self.path_parameters:
            metadata["path_parameters"] = list(self.path_parameters)
        activity = self.activity.to_dict()
        if activity != {"kind": "generic"}:
            metadata["activity"] = activity
        return metadata


@dataclass(frozen=True)
class RegisteredTool(ToolDefinition):
    pass


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

    def set_execution_observer(self, observer: ToolExecutionObserver | None) -> None:
        self._execution_observer = observer

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
            target = _format_contract_value(payload.get(tool.activity.target_argument))
        return {
            "name": tool.name,
            "description": tool.description,
            "activity": activity,
            "target": target,
            "paths": _extract_contract_paths(tool, payload),
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
        validation_error = _validate_tool_arguments(tool, arguments)
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
        try:
            async with self._semaphore_for_running_loop():
                result = await asyncio.wait_for(
                    _call_handler(tool.handler, arguments),
                    timeout=self._tool_timeout,
                )
            metadata = await self._after_tool(scope, arguments, result=result, duration_ms=_duration_ms(started_at))
            content, raw = _tool_result_payload(tool, result, metadata)
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
                raw=_with_metadata(None, metadata),
            )
        except ToolExecutionError as exc:
            metadata = await self._after_tool(
                scope,
                arguments,
                is_error=True,
                error=exc.content,
                duration_ms=_duration_ms(started_at),
            )
            content, raw = _tool_error_payload(tool, exc, metadata)
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
                raw=_with_metadata(None, metadata),
            )

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


def _format_tool_result(tool: ToolDefinition, result: Any) -> str:
    if tool.result_formatter is not None:
        return str(tool.result_formatter(result))
    if isinstance(result, str):
        return result
    return json.dumps(result, ensure_ascii=False, sort_keys=True)


def _is_interrupt_cancel(exc: asyncio.CancelledError) -> bool:
    return bool(exc.args) and str(exc.args[0]) == "interrupt"


def cancelled_tool_result(
    call: ToolCall,
    canceled_by: ToolResult | None = None,
    *,
    cancel_reason: str = "tool_cancelled",
) -> ToolResult:
    cancelled_by = canceled_by.name if canceled_by is not None else ""
    content = "tool execution canceled"
    if cancelled_by:
        content = "%s by sibling tool failure: %s" % (content, cancelled_by)
    elif cancel_reason == "user_interrupted":
        content = "%s by user interrupt" % content
    return ToolResult(
        tool_call_id=call.id,
        name=call.name,
        content=content,
        is_error=True,
        raw={
            "error": "tool_execution_canceled",
            "canceled": True,
            "canceled_by": cancelled_by,
            "cancel_reason": cancel_reason,
        },
    )


def _tool_result_payload(
    tool: ToolDefinition,
    result: Any,
    metadata: dict[str, Any],
) -> tuple[str, Any]:
    content = _format_tool_result(tool, result)
    output_metadata = dict(metadata or {})
    if tool.max_result_size_chars is not None and len(content) > tool.max_result_size_chars:
        content = content[: tool.max_result_size_chars] + "\n[tool result truncated]"
        output_metadata["result_truncated"] = True
        output_metadata["max_result_size_chars"] = tool.max_result_size_chars
    return content, _with_metadata(result, output_metadata)


def _tool_error_payload(
    tool: ToolDefinition,
    error: ToolExecutionError,
    metadata: dict[str, Any],
) -> tuple[str, Any]:
    content = str(error.content or "")
    output_metadata = dict(metadata or {})
    if tool.max_result_size_chars is not None and len(content) > tool.max_result_size_chars:
        content = content[: tool.max_result_size_chars] + "\n[tool result truncated]"
        output_metadata["result_truncated"] = True
        output_metadata["max_result_size_chars"] = tool.max_result_size_chars
    raw = error.raw if error.raw is not None else {"error": "tool_execution_error"}
    if isinstance(raw, dict) and "error" not in raw:
        raw = {"error": "tool_execution_error", **raw}
    return content, _with_metadata(raw, output_metadata)


def _coerce_string_tuple(value: Any) -> tuple[str, ...]:
    if value is None or value == "":
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (list, tuple)):
        return tuple(str(item) for item in value if str(item))
    return ()


def _extract_contract_paths(tool: ToolDefinition, arguments: Dict[str, Any]) -> list[str]:
    paths: list[str] = []
    for name in tool.path_parameters:
        value = arguments.get(name)
        if isinstance(value, str):
            if value:
                paths.append(value)
        elif isinstance(value, (list, tuple)):
            paths.extend(str(item) for item in value if str(item))
    return paths


def _format_contract_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return ", ".join(str(item) for item in value if str(item))
    return str(value)


def _validate_tool_arguments(tool: ToolDefinition, arguments: Dict[str, Any]) -> str:
    if not tool.strict_input_schema:
        return ""
    schema = dict(tool.parameters or {})
    if not schema:
        return ""
    if schema.get("type") not in ("object", None):
        return ""
    properties = dict(schema.get("properties") or {})
    required = [str(item) for item in schema.get("required") or []]
    for key in required:
        if key not in arguments:
            return "missing required argument: %s" % key
    if properties and schema.get("additionalProperties") is False:
        for key in arguments:
            if key not in properties:
                return "unexpected argument: %s" % key
    for key, value in arguments.items():
        if key not in properties:
            continue
        error = _validate_json_schema_value(key, value, dict(properties[key] or {}))
        if error:
            return error
    return ""


def _validate_json_schema_value(path: str, value: Any, schema: Dict[str, Any]) -> str:
    if "enum" in schema and value not in list(schema.get("enum") or []):
        return "%s must be one of %s" % (path, ", ".join(map(str, schema.get("enum") or [])))
    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        if any(_json_schema_type_matches(value, str(item)) for item in schema_type):
            return ""
        return "%s must match one of: %s" % (path, ", ".join(map(str, schema_type)))
    if schema_type and not _json_schema_type_matches(value, str(schema_type)):
        return "%s must be %s" % (path, schema_type)
    if schema_type == "object":
        if not isinstance(value, dict):
            return "%s must be object" % path
        properties = dict(schema.get("properties") or {})
        for key in schema.get("required") or []:
            if key not in value:
                return "missing required argument: %s.%s" % (path, key)
        if properties and schema.get("additionalProperties") is False:
            for key in value:
                if key not in properties:
                    return "unexpected argument: %s.%s" % (path, key)
        for key, nested in properties.items():
            if key in value:
                error = _validate_json_schema_value("%s.%s" % (path, key), value[key], dict(nested or {}))
                if error:
                    return error
    if schema_type == "array":
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                error = _validate_json_schema_value("%s[%d]" % (path, index), item, dict(item_schema))
                if error:
                    return error
    return ""


def _json_schema_type_matches(value: Any, schema_type: str) -> bool:
    if schema_type == "string":
        return isinstance(value, str)
    if schema_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if schema_type == "number":
        return (isinstance(value, int) or isinstance(value, float)) and not isinstance(value, bool)
    if schema_type == "boolean":
        return isinstance(value, bool)
    if schema_type == "object":
        return isinstance(value, dict)
    if schema_type == "array":
        return isinstance(value, list)
    if schema_type == "null":
        return value is None
    return True


def _duration_ms(started_at: float) -> float:
    return round((time.perf_counter() - started_at) * 1000, 3)


def _with_metadata(result: Any, metadata: dict[str, Any]) -> Any:
    if not metadata:
        return result
    if isinstance(result, dict):
        payload = dict(result)
        payload["_meta"] = dict(payload.get("_meta") or {})
        payload["_meta"].update(metadata)
        return payload
    return {"result": result, "_meta": dict(metadata)}
