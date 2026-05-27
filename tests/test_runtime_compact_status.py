import asyncio

from agents.kernel.capabilities.tools import ToolRegistry
from agents.kernel.models.protocol import message_event, text_delta
from agents.kernel.runtime import AgentRuntime, AgentSession, ScriptedModelClient
from agents.kernel.schema import Message, ModelResponse


def test_agent_session_stream_emits_compacting_status_around_boundary():
    client = ScriptedModelClient(
        [
            [
                text_delta("done"),
                message_event(ModelResponse(message=Message.from_text("assistant", "done"))),
            ],
        ]
    )
    runtime = AgentRuntime(
        model_client=client,
        tools=ToolRegistry(),
        protocol="scripted",
        model="scripted",
        enabled_tools=[],
    )
    session = AgentSession(runtime, max_context_tokens=24, compaction_target_tokens=8)
    session.messages.extend(
        [
            Message.from_text("user", "old user context " * 40),
            Message.from_text("assistant", "old assistant context " * 40),
        ]
    )

    events = asyncio.run(_collect(session.stream("new prompt", run_id="run-1", user_message_id="user-new")))

    assert [event.type for event in events[:3]] == ["status", "status", "compact_boundary"]
    assert events[0].payload["status"] == "compacting"
    assert events[1].payload["status"] is None
    assert events[2].payload["preserved_segment"]["tail_uuid"] == "user-new"


async def _collect(stream):
    return [event async for event in stream]
