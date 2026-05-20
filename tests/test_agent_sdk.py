import asyncio

import pytest
from pydantic import ValidationError

from agents.kernel.schema import Message, ModelResponse, ToolCall
from agents.kernel.models.protocol import message_event, text_delta
from agents.kernel.runtime import AgentRuntime, AgentSession, ScriptedModelClient
from agents.kernel.capabilities.tools.registry import ToolRegistry
from agents.kernel.context.workspace import WorkspaceContext
from agents.sdk import (
    AgentSDKClient,
    SDKListSessionsOptions,
    SDKOptions,
    SDKSessionInfo,
    SDKSession,
    sdk_message_json_schema,
    sdk_options_json_schema,
    sdk_result_json_schema,
    sdk_session_info_json_schema,
    validate_sdk_message,
)
from agents.sdk.client import _spec_from_options
from agents.sdk.types import (
    SDKResultMessage,
    SDKSystemMessage,
    SDKToolProgressMessage,
)


async def _session_factory(settings, spec):
    tools = ToolRegistry()
    tools.register(
        "echo",
        "Echo text",
        {},
        lambda text: text,
        metadata={"activity": {"kind": "terminal", "title": "Echo text", "target_argument": "text"}},
    )
    llm = ScriptedModelClient(
        [
            ModelResponse(
                message=Message.from_text(
                    "assistant",
                    "",
                    tool_calls=[ToolCall(id="call-1", name="echo", arguments={"text": "hi"})],
                ),
                stop_reason="tool_calls",
            ),
            [
                text_delta("done"),
                message_event(ModelResponse(message=Message.from_text("assistant", "done"))),
            ],
        ]
    )
    runtime = AgentRuntime(
        model_client=llm,
        tools=tools,
        protocol=spec.model.protocol or "scripted",
        model=spec.model.model or "scripted",
        enabled_tools=["echo"],
    )
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=".",
        path=".",
    )
    return AgentSession(runtime, system_prompt="", workspace=workspace)


def test_sdk_query_hides_store_wiring_and_streams_typed_messages():
    client = AgentSDKClient(session_factory=_session_factory)

    messages = asyncio.run(_collect(client.query("say hi", SDKOptions(session_id="session-1"))))

    assert isinstance(messages[0], SDKSystemMessage)
    assert messages[0].session_id == "session-1"
    assert messages[0].tools == ["echo"]
    assert [message.type for message in messages] == [
        "system",
        "tool_progress",
        "tool_progress",
        "assistant",
        "result",
    ]
    assert isinstance(messages[1], SDKToolProgressMessage)
    assert messages[1].status == "started"
    assert messages[1].activity == {"kind": "terminal", "title": "Echo text", "target_argument": "text"}
    assert messages[1].target == "hi"
    assert messages[2].status == "completed"
    assert messages[2].activity["kind"] == "terminal"
    assert messages[2].target == "hi"
    assert isinstance(messages[-1], SDKResultMessage)
    assert messages[-1].content == "done"
    assert messages[-1].status == "finished"
    assert [validate_sdk_message(message.model_dump()) for message in messages] == messages


def test_sdk_prompt_returns_final_result():
    client = AgentSDKClient(session_factory=_session_factory)

    result = asyncio.run(client.prompt("say hi"))

    assert result.type == "result"
    assert result.content == "done"
    assert result.subtype == "success"


def test_sdk_session_helpers_list_replay_and_mutate_run_backed_sessions():
    client = AgentSDKClient(session_factory=_session_factory)

    result = asyncio.run(client.prompt("first meaningful prompt", SDKOptions(session_id="session-1", cwd=".")))
    sessions = asyncio.run(client.list_sessions())
    info = asyncio.run(client.get_session_info("session-1"))
    messages = asyncio.run(client.get_session_messages("session-1"))

    assert result.session_id == "session-1"
    assert len(sessions) == 1
    assert isinstance(sessions[0], SDKSessionInfo)
    assert sessions[0].session_id == "session-1"
    assert sessions[0].summary == "first meaningful prompt"
    assert sessions[0].first_prompt == "first meaningful prompt"
    assert sessions[0].run_ids == [result.run_id]
    assert info == sessions[0]
    assert messages[0].type == "system"
    assert any(isinstance(message, SDKToolProgressMessage) and message.status == "started" for message in messages)
    assert any(isinstance(message, SDKResultMessage) and message.content == "done" for message in messages)

    asyncio.run(client.rename_session("session-1", "Pinned title"))
    asyncio.run(client.tag_session("session-1", "review"))
    renamed = asyncio.run(client.get_session_info("session-1"))
    paged = asyncio.run(client.list_sessions(SDKListSessionsOptions(limit=1, offset=0)))
    replay_without_system = asyncio.run(
        client.get_session_messages("session-1", {"include_system_messages": False, "limit": 2})
    )

    assert renamed.summary == "Pinned title"
    assert renamed.custom_title == "Pinned title"
    assert renamed.tag == "review"
    assert paged[0].summary == "Pinned title"
    assert all(message.type != "system" for message in replay_without_system)
    assert len(replay_without_system) == 2
    with pytest.raises(ValueError):
        asyncio.run(client.rename_session("session-1", " "))
    with pytest.raises(KeyError):
        asyncio.run(client.tag_session("missing-session", "review"))


def test_sdk_session_object_keeps_stable_session_id_across_prompts():
    client = AgentSDKClient(session_factory=_session_factory)
    session = client.create_sdk_session(
        SDKOptions(session_id="conversation-1", metadata={"caller": "test"})
    )

    first = asyncio.run(session.prompt("turn one"))
    resumed = asyncio.run(client.resume_session("conversation-1"))
    second_messages = asyncio.run(_collect(resumed.query("turn two", {"metadata": {"turn": "two"}})))
    info = asyncio.run(resumed.info())

    assert isinstance(session, SDKSession)
    assert resumed.session_id == "conversation-1"
    assert first.session_id == "conversation-1"
    assert all(message.session_id == "conversation-1" for message in second_messages)
    assert info.run_ids == [first.run_id, second_messages[-1].run_id]
    assert info.first_prompt == "turn one"
    assert info.metadata["run_count"] == 2

    asyncio.run(resumed.rename("Conversation title"))
    asyncio.run(resumed.tag("followup"))
    renamed = asyncio.run(session.info())
    assert renamed.summary == "Conversation title"
    assert renamed.tag == "followup"
    with pytest.raises(KeyError):
        asyncio.run(client.resume_session("missing-session"))


def test_sdk_output_format_projects_structured_output_schema():
    schema = {
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
    }

    spec = _spec_from_options(SDKOptions(output_format={"type": "json_schema", "schema": schema}, metadata={"caller": "test"}))

    assert spec.metadata["caller"] == "test"
    assert spec.metadata["structured_output_schema"] == schema


def test_sdk_exports_json_schemas_and_rejects_invalid_messages():
    options_schema = sdk_options_json_schema()
    message_schema = sdk_message_json_schema()
    result_schema = sdk_result_json_schema()
    session_schema = sdk_session_info_json_schema()

    assert options_schema["additionalProperties"] is False
    assert "SDKSystemMessage" in message_schema["$defs"]
    assert "SDKToolProgressMessage" in message_schema["$defs"]
    assert result_schema["properties"]["type"]["const"] == "result"
    assert session_schema["properties"]["session_id"]["title"] == "Session Id"

    valid = validate_sdk_message(
        {
            "type": "result",
            "subtype": "success",
            "session_id": "session-1",
            "run_id": "run-1",
            "content": "done",
        }
    )
    assert isinstance(valid, SDKResultMessage)
    assert valid.status == "finished"

    with pytest.raises(ValidationError):
        validate_sdk_message(
            {
                "type": "result",
                "subtype": "success",
                "session_id": "session-1",
                "run_id": "run-1",
                "unexpected": True,
            }
        )


async def _collect(messages):
    return [message async for message in messages]
