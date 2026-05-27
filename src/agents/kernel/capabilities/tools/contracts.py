from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict


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
        path_parameters = coerce_string_tuple(payload.get("path_parameters"))
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


def coerce_string_tuple(value: Any) -> tuple[str, ...]:
    if value is None or value == "":
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (list, tuple)):
        return tuple(str(item) for item in value if str(item))
    return ()


def extract_contract_paths(tool: ToolDefinition, arguments: Dict[str, Any]) -> list[str]:
    paths: list[str] = []
    for name in tool.path_parameters:
        value = arguments.get(name)
        if isinstance(value, str):
            if value:
                paths.append(value)
        elif isinstance(value, (list, tuple)):
            paths.extend(str(item) for item in value if str(item))
    return paths


def format_contract_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return ", ".join(str(item) for item in value if str(item))
    return str(value)
