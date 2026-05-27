import asyncio

from agents.kernel.runtime import AgentRuntime, ScriptedModelClient
from agents.kernel.schema import Message, ModelResponse, ModelStreamEvent
from agents.kernel.capabilities.tools.registry import ToolRegistry


def test_agent_runtime_recovers_from_max_output_stop_reason():
    llm = ScriptedModelClient(
        [
            ModelResponse(message=Message.from_text("assistant", "partial"), stop_reason="max_tokens"),
            ModelResponse(message=Message.from_text("assistant", "continued")),
        ]
    )
    runtime = AgentRuntime(model_client=llm, tools=ToolRegistry(), protocol="scripted", model="scripted")

    result = asyncio.run(runtime.run([Message.from_text("user", "write a long answer")]))

    assert result.content == "continued"
    assert result.status == "finished"
    assert [message.role for message in result.messages] == ["user", "assistant", "user", "assistant"]
    assert result.messages[2].raw["is_meta"] is True
    assert "Output token limit hit" in result.messages[2].content_text()
    recovery_events = [event for event in result.events if event.type == "model_recovery"]
    assert recovery_events[0].payload["attempt"] == 1
    assert recovery_events[0].payload["stop_reason"] == "max_tokens"


def test_agent_runtime_stream_recovers_from_openai_length_stop_reason():
    llm = ScriptedModelClient(
        [
            [
                ModelStreamEvent(type="text_delta", delta="partial"),
                ModelStreamEvent(
                    type="message",
                    response=ModelResponse(message=Message.from_text("assistant", "partial"), stop_reason="length"),
                ),
            ],
            [
                ModelStreamEvent(type="text_delta", delta=" continued"),
                ModelStreamEvent(
                    type="message",
                    response=ModelResponse(message=Message.from_text("assistant", "continued")),
                ),
            ],
        ]
    )
    runtime = AgentRuntime(model_client=llm, tools=ToolRegistry(), protocol="scripted", model="scripted")

    events = asyncio.run(_collect(runtime.stream([Message.from_text("user", "write")])))

    assert [event.type for event in events] == ["text_delta", "model_recovery", "text_delta", "done"]
    assert events[1].payload["stop_reason"] == "length"
    assert events[-1].payload["content"] == "continued"
    assert events[-1].payload["status"] == "finished"


def test_agent_runtime_errors_after_max_output_recovery_exhaustion():
    llm = ScriptedModelClient(
        [
            ModelResponse(message=Message.from_text("assistant", "partial 1"), stop_reason="max_tokens"),
            ModelResponse(message=Message.from_text("assistant", "partial 2"), stop_reason="max_tokens"),
            ModelResponse(message=Message.from_text("assistant", "partial 3"), stop_reason="max_tokens"),
            ModelResponse(message=Message.from_text("assistant", "partial 4"), stop_reason="max_tokens"),
        ]
    )
    runtime = AgentRuntime(model_client=llm, tools=ToolRegistry(), protocol="scripted", model="scripted")

    result = asyncio.run(runtime.run([Message.from_text("user", "write a huge answer")]))

    assert result.status == "error"
    assert result.content == "model output limit recovery exhausted after 3 attempts: max_tokens"
    assert len([event for event in result.events if event.type == "model_recovery"]) == 3
    assert result.events[-1].type == "error"


async def _collect(stream):
    return [event async for event in stream]
