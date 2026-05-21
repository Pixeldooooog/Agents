from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional

from agents.kernel.schema import Message, ModelResponse, RuntimeEvent, ToolCall, ToolResult

if TYPE_CHECKING:
    from agents.kernel.runtime import AgentResult


class AgentHooks:
    """Agent Runtime 扩展钩子。子类覆盖需要的方法即可。"""

    def emit_runtime_event(self, event: RuntimeEvent) -> None:
        events = getattr(self, "_runtime_events", None)
        if events is None:
            events = []
            setattr(self, "_runtime_events", events)
        events.append(event)

    def drain_runtime_events(self) -> List[RuntimeEvent]:
        events = list(getattr(self, "_runtime_events", []) or [])
        setattr(self, "_runtime_events", [])
        return events

    async def before_request(self, messages: List[Message]) -> List[Message]:
        """在消息发给模型前调用，可修改/增强消息列表。"""
        return messages

    async def after_response(self, response: ModelResponse) -> ModelResponse:
        """在模型返回后调用，可检查/修改响应。"""
        return response

    async def before_tool_use(self, call: ToolCall) -> ToolCall:
        """在工具执行前调用，可修改或拒绝工具调用。"""
        return call

    async def after_tool_use(self, call: ToolCall, result: ToolResult) -> ToolResult:
        """在工具执行后调用，可记录或修改工具结果。"""
        return result

    def format_tool_result(self, result: ToolResult) -> Message:
        """在工具结果加入消息列表前调用，返回格式化后的消息。"""
        return Message.from_text(
            "tool",
            result.content,
            tool_call_id=result.tool_call_id,
            name=result.name,
            raw=result.to_dict(),
        )

    async def on_error(self, error: Exception, messages: List[Message]) -> Optional[AgentResult]:
        """出错时调用，返回恢复结果则覆盖默认错误处理，返回 None 走默认逻辑。"""
        return None


class ToolHookDenied(RuntimeError):
    def __init__(self, tool_name: str, reason: str = "tool denied by hook"):
        super().__init__(reason)
        self.tool_name = tool_name
        self.reason = reason
