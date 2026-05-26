from __future__ import annotations

from typing import Any

from agents.kernel.capabilities.tools.registry import ToolActivity, ToolDefinition, ToolRegistry


def register_builtin_tool(
    registry: ToolRegistry,
    *,
    name: str,
    description: str,
    parameters: dict[str, Any],
    handler: Any,
    metadata: dict[str, Any] | None = None,
    read_only: bool = False,
    destructive: bool = False,
    writes_state: bool = False,
    concurrency_safe: bool = True,
    interrupt_behavior: str = "block",
    cancels_siblings_on_error: bool = False,
    max_result_size_chars: int | None = None,
    path_parameters: tuple[str, ...] = (),
    activity_kind: str = "generic",
    activity_title: str = "",
    activity_target_argument: str = "",
    activity_summary: str = "",
    result_formatter: Any = None,
) -> None:
    registry.register_definition(
        ToolDefinition(
            name=name,
            description=description,
            parameters=parameters,
            handler=handler,
            metadata=dict(metadata or {}),
            read_only=read_only,
            destructive=destructive,
            writes_state=writes_state,
            concurrency_safe=concurrency_safe,
            interrupt_behavior=interrupt_behavior,
            cancels_siblings_on_error=cancels_siblings_on_error,
            max_result_size_chars=max_result_size_chars,
            path_parameters=path_parameters,
            activity=ToolActivity(
                kind=activity_kind,
                title=activity_title,
                target_argument=activity_target_argument,
                summary=activity_summary,
            ),
            result_formatter=result_formatter,
        )
    )
