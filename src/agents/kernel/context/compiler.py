from __future__ import annotations

from typing import List

from agents.kernel.runtime.config import RuntimeConfig
from agents.kernel.schema import Message, ModelRequest
from agents.kernel.capabilities.tools.registry import ToolRegistry


class ModelRequestCompiler:
    """Builds protocol-neutral model requests from runtime state."""

    def __init__(self, tools: ToolRegistry):
        self.tools = tools

    def compile(self, messages: List[Message], config: RuntimeConfig) -> ModelRequest:
        return ModelRequest(
            protocol=config.protocol,
            model=config.model,
            messages=list(messages),
            tools=self.tools.specs(config.tool_names()),
        )
