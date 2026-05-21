import asyncio
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from agents.kernel.mcp_config import MCPServerRecord
from agents.kernel.schema import Message, ModelResponse, RuntimeEvent, ToolCall
from agents.kernel.models.protocol import message_event, reasoning_delta, retry_event, text_delta
from agents.kernel.runtime import AgentRuntime, AgentSession, ScriptedModelClient
from agents.kernel.capabilities.tools.registry import ToolRegistry
from agents.kernel.context.workspace import WorkspaceContext
from agents.sdk import (
    AgentSDKClient,
    SDKForkSessionOptions,
    SDKForkSessionResult,
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
    SDKAPIRetryMessage,
    SDKAssistantMessage,
    SDKAuthStatusMessage,
    SDKCompactBoundaryMessage,
    SDKFilesPersistedMessage,
    SDKHookProgressMessage,
    SDKHookResponseMessage,
    SDKHookStartedMessage,
    SDKLocalCommandOutputMessage,
    SDKElicitationCompleteMessage,
    SDKPostTurnSummaryMessage,
    SDKPromptSuggestionMessage,
    SDKRateLimitEventMessage,
    SDKResultMessage,
    SDKSessionStateChangedMessage,
    SDKStatusMessage,
    SDKSystemMessage,
    SDKStreamEventMessage,
    SDKTaskNotificationMessage,
    SDKTaskProgressMessage,
    SDKTaskStartedMessage,
    SDKToolProgressMessage,
    SDKToolUseSummaryMessage,
    SDKUserMessage,
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


async def _retry_session_factory(settings, spec):
    llm = ScriptedModelClient(
        [
            [
                retry_event(
                    {
                        "next_attempt": 2,
                        "max_attempts": 3,
                        "delay_seconds": 0.25,
                        "error": "connect failed",
                    }
                ),
                text_delta("done"),
                message_event(ModelResponse(message=Message.from_text("assistant", "done"))),
            ],
        ]
    )
    runtime = AgentRuntime(
        model_client=llm,
        tools=ToolRegistry(),
        protocol=spec.model.protocol or "scripted",
        model=spec.model.model or "scripted",
        enabled_tools=[],
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


async def _reasoning_session_factory(settings, spec):
    llm = ScriptedModelClient(
        [
            [
                reasoning_delta("checking assumptions"),
                message_event(ModelResponse(message=Message.from_text("assistant", "done"))),
            ],
        ]
    )
    runtime = AgentRuntime(
        model_client=llm,
        tools=ToolRegistry(),
        protocol=spec.model.protocol or "scripted",
        model=spec.model.model or "scripted",
        enabled_tools=[],
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


async def _assistant_message_session_factory(settings, spec):
    assistant_workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=".",
        path=".",
    )

    class AssistantMessageSession:
        runtime = SimpleNamespace(model="scripted", protocol="scripted", enabled_tools=[])
        workspace = assistant_workspace

        async def stream(self, text, run_id=None):
            yield RuntimeEvent(
                type="model_message",
                name="assistant",
                payload={
                    "uuid": "assistant-message-1",
                    "message": {
                        "id": "msg_assistant_1",
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "text", "text": "assistant answer"}],
                        "model": "scripted",
                        "stop_reason": "end_turn",
                        "stop_sequence": None,
                        "usage": {},
                    },
                },
            )
            yield RuntimeEvent(type="done", name="assistant", payload={"content": "assistant answer", "status": "finished"})

    return AssistantMessageSession()


async def _failing_session_factory(settings, spec):
    failing_workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=".",
        path=".",
    )

    class FailingSession:
        runtime = SimpleNamespace(model="scripted", protocol="scripted", enabled_tools=[])
        workspace = failing_workspace

        async def stream(self, text, run_id=None):
            raise RuntimeError("model transport failed")
            yield

    return FailingSession()


async def _compacting_session_factory(settings, spec):
    llm = ScriptedModelClient(
        [
            [
                text_delta("done"),
                message_event(ModelResponse(message=Message.from_text("assistant", "done"))),
            ],
        ]
    )
    runtime = AgentRuntime(
        model_client=llm,
        tools=ToolRegistry(),
        protocol=spec.model.protocol or "scripted",
        model=spec.model.model or "scripted",
        enabled_tools=[],
    )
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=".",
        path=".",
    )
    session = AgentSession(
        runtime,
        system_prompt="",
        max_context_tokens=24,
        compaction_target_tokens=8,
        workspace=workspace,
    )
    session.messages.extend(
        [
            Message.from_text("user", "old user context " * 40),
            Message.from_text("assistant", "old assistant context " * 40),
        ]
    )
    return session


async def _auth_session_factory(settings, spec):
    tools = ToolRegistry()
    tools.register(
        "mcp__docs__authenticate",
        "Authenticate docs MCP server",
        {},
        lambda: {
            "status": "auth_url",
            "server": "docs",
            "transport": "http",
            "authUrl": "https://mcp.example.test/oauth",
            "auth_url": "https://mcp.example.test/oauth",
            "message": "Open the authorization URL.",
        },
        metadata={"auth_tool": True},
    )
    llm = ScriptedModelClient(
        [
            ModelResponse(
                message=Message.from_text(
                    "assistant",
                    "",
                    tool_calls=[ToolCall(id="auth-call", name="mcp__docs__authenticate", arguments={})],
                ),
                stop_reason="tool_calls",
            ),
            [
                text_delta("authenticated"),
                message_event(ModelResponse(message=Message.from_text("assistant", "authenticated"))),
            ],
        ]
    )
    runtime = AgentRuntime(
        model_client=llm,
        tools=tools,
        protocol=spec.model.protocol or "scripted",
        model=spec.model.model or "scripted",
        enabled_tools=["mcp__docs__authenticate"],
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


async def _approval_session_factory(settings, spec):
    approval_workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=".",
        path=".",
    )

    class ApprovalSession:
        runtime = SimpleNamespace(model="scripted", protocol="scripted", enabled_tools=["filesystem.write"])
        workspace = approval_workspace

        async def stream(self, text, run_id=None):
            yield RuntimeEvent(
                type="tool_approval_required",
                name="filesystem.write",
                payload={
                    "tool_call": {
                        "id": "write-call",
                        "name": "filesystem.write",
                        "arguments": {"path": "README.md", "content": "updated"},
                    },
                },
            )

    return ApprovalSession()


async def _task_session_factory(settings, spec):
    task_workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=".",
        path=".",
    )

    class TaskSession:
        runtime = SimpleNamespace(model="scripted", protocol="scripted", enabled_tools=["task.run", "task.update"])
        workspace = task_workspace

        async def stream(self, text, run_id=None):
            task = {
                "task_id": "task_123",
                "title": "Run tracked work",
                "input": "do the work",
                "status": "finished",
                "metadata": {"task_type": "agent"},
            }
            yield RuntimeEvent(
                type="tool_result",
                name="task.run",
                payload={
                    "tool_call_id": "task-run-call",
                    "raw": {
                        "task": task,
                        "step": {"name": "execute", "output": "executed child"},
                        "result": {"content": "executed child", "messages": 1, "tool_results": 2},
                        "run": {"run_id": "run-child", "status": "finished"},
                    },
                },
            )
            yield RuntimeEvent(
                type="tool_result",
                name="task.update",
                payload={
                    "tool_call_id": "task-update-call",
                    "raw": {
                        "task": {**task, "status": "running"},
                        "step": {"name": "review"},
                    },
                },
            )
            yield RuntimeEvent(type="done", name="assistant", payload={"content": "task done", "status": "finished"})

    return TaskSession()


async def _artifact_session_factory(settings, spec):
    artifact_workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=".",
        path=".",
    )

    class ArtifactSession:
        runtime = SimpleNamespace(model="scripted", protocol="scripted", enabled_tools=["browser.open"])
        workspace = artifact_workspace

        async def stream(self, text, run_id=None):
            yield RuntimeEvent(
                type="tool_result",
                name="browser.open",
                payload={
                    "tool_call_id": "browser-call",
                    "raw": {
                        "artifact": {
                            "artifact_id": "artifact_123",
                            "workspace_path": "",
                            "uri": "/tmp/browser-open.html",
                            "created_at": 1_700_000_000.0,
                        }
                    },
                },
            )
            yield RuntimeEvent(type="done", name="assistant", payload={"content": "opened", "status": "finished"})

    return ArtifactSession()


async def _hook_session_factory(settings, spec):
    hook_workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=".",
        path=".",
    )

    class HookSession:
        runtime = SimpleNamespace(model="scripted", protocol="scripted", enabled_tools=["shell.run"])
        workspace = hook_workspace

        async def stream(self, text, run_id=None):
            yield RuntimeEvent(
                type="hook_started",
                name="block-shell",
                payload={
                    "hook_id": "hook_123",
                    "hook_name": "block-shell",
                    "hook_event": "PreToolUse",
                },
            )
            yield RuntimeEvent(
                type="hook_progress",
                name="block-shell",
                payload={
                    "hook_id": "hook_123",
                    "hook_name": "block-shell",
                    "hook_event": "PreToolUse",
                    "stdout": "checking shell",
                    "stderr": "",
                    "output": "checking shell",
                },
            )
            yield RuntimeEvent(
                type="hook_response",
                name="block-shell",
                payload={
                    "hook_id": "hook_123",
                    "hook_name": "block-shell",
                    "hook_event": "PreToolUse",
                    "stdout": "blocked",
                    "stderr": "",
                    "output": "blocked",
                    "exit_code": 0,
                    "outcome": "success",
                },
            )
            yield RuntimeEvent(type="done", name="assistant", payload={"content": "hooked", "status": "finished"})

    return HookSession()


async def _local_command_session_factory(settings, spec):
    local_command_workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=".",
        path=".",
    )

    class LocalCommandSession:
        runtime = SimpleNamespace(model="scripted", protocol="scripted", enabled_tools=[])
        workspace = local_command_workspace

        async def stream(self, text, run_id=None):
            yield RuntimeEvent(
                type="local_command_output",
                name="local_command",
                payload={
                    "uuid": "local-command-1",
                    "content": "<local-command-stdout>Switched to opus</local-command-stdout>",
                },
            )
            yield RuntimeEvent(type="done", name="assistant", payload={"content": "", "status": "finished"})

    return LocalCommandSession()


async def _sdk_extension_event_session_factory(settings, spec):
    extension_workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=".",
        path=".",
    )

    class ExtensionEventSession:
        runtime = SimpleNamespace(model="scripted", protocol="scripted", enabled_tools=[])
        workspace = extension_workspace

        async def stream(self, text, run_id=None):
            yield RuntimeEvent(
                type="rate_limit_event",
                name="rate_limit",
                payload={
                    "uuid": "rate-limit-1",
                    "rate_limit_info": {
                        "isNearLimit": True,
                        "resetsAt": "2026-05-21T10:00:00Z",
                    },
                },
            )
            yield RuntimeEvent(
                type="elicitation_complete",
                name="mcp",
                payload={
                    "uuid": "elicitation-1",
                    "mcp_server_name": "docs",
                    "elicitation_id": "elicit_123",
                },
            )
            yield RuntimeEvent(
                type="prompt_suggestion",
                name="suggestion",
                payload={"uuid": "suggestion-1", "suggestion": "Run the tests"},
            )
            yield RuntimeEvent(
                type="status",
                name="status",
                payload={"uuid": "status-1", "status": "compacting", "permissionMode": "ask"},
            )
            yield RuntimeEvent(
                type="post_turn_summary",
                name="summary",
                payload={
                    "uuid": "summary-1",
                    "summarizes_uuid": "assistant-1",
                    "status_category": "review_ready",
                    "status_detail": "tests passed",
                    "is_noteworthy": True,
                    "title": "Tests passed",
                    "description": "The requested checks completed.",
                    "recent_action": "Ran tests",
                    "needs_action": "Review diff",
                    "artifact_urls": ["artifact://report"],
                },
            )
            yield RuntimeEvent(type="done", name="assistant", payload={"content": "", "status": "finished"})

    return ExtensionEventSession()


def test_sdk_query_hides_store_wiring_and_streams_typed_messages():
    client = AgentSDKClient(session_factory=_session_factory)
    assert client.persistence is not None
    asyncio.run(
        client.persistence.mcp_configs.save(
            MCPServerRecord(
                name="docs",
                command="docs-mcp",
                auth_required=True,
                tenant_id="tenant",
                user_id="user",
                agent_id="agent",
            )
        )
    )

    options = SDKOptions(
        session_id="session-1",
        skills=["review"],
        permission_mode="acceptEdits",
        metadata={
            "apiKeySource": "oauth",
            "agents": ["reviewer"],
            "betas": ["context-1m-2025-08-07"],
            "output_style": "concise",
            "plugins": [{"name": "docs-plugin", "path": "/plugins/docs", "source": "docs@inline"}],
            "fast_mode_state": "off",
        },
    )
    messages = asyncio.run(_collect(client.query("say hi", options)))
    replay = asyncio.run(client.get_session_messages("session-1", {"include_system_messages": False}))
    replay_with_system = asyncio.run(client.get_session_messages("session-1"))

    assert isinstance(messages[0], SDKSystemMessage)
    init = messages[0]
    assert init.session_id == "session-1"
    assert init.apiKeySource == "oauth"
    assert init.permissionMode == "acceptEdits"
    assert init.tools == ["echo"]
    assert init.skills == ["review"]
    assert init.agents == ["reviewer"]
    assert init.betas == ["context-1m-2025-08-07"]
    assert init.output_style == "concise"
    assert init.plugins == [{"name": "docs-plugin", "path": "/plugins/docs", "source": "docs@inline"}]
    assert init.fast_mode_state == "off"
    assert init.mcp_servers == [{"name": "docs", "status": "needs-auth"}]
    assert "/help" in init.slash_commands
    assert init.claude_code_version
    assert "protocol" not in init.model_dump()
    assert "metadata" not in init.model_dump()
    assert validate_sdk_message(init.model_dump()) == init
    replay_init = next(message for message in replay_with_system if isinstance(message, SDKSystemMessage))
    assert replay_init.tools == ["echo"]
    assert replay_init.skills == ["review"]
    assert replay_init.mcp_servers == [{"name": "docs", "status": "needs-auth"}]
    states = [message.state for message in messages if isinstance(message, SDKSessionStateChangedMessage)]
    assert states == ["running", "idle"]
    stream_events = [message for message in messages if isinstance(message, SDKStreamEventMessage)]
    tool_messages = [message for message in messages if isinstance(message, SDKToolProgressMessage)]
    summaries = [message for message in messages if isinstance(message, SDKToolUseSummaryMessage)]
    assert stream_events[0].event["delta"] == {"type": "text_delta", "text": "done"}
    assert len(tool_messages) == 2
    assert tool_messages[0].status == "started"
    assert tool_messages[0].activity == {"kind": "terminal", "title": "Echo text", "target_argument": "text"}
    assert tool_messages[0].target == "hi"
    assert tool_messages[1].status == "completed"
    assert tool_messages[1].activity["kind"] == "terminal"
    assert tool_messages[1].target == "hi"
    assert summaries[0].summary == "Ran echo"
    assert summaries[0].preceding_tool_use_ids == ["call-1"]
    assert any(isinstance(message, SDKToolUseSummaryMessage) for message in replay)
    result = next(message for message in messages if isinstance(message, SDKResultMessage))
    assert result.content == "done"
    assert result.result == "done"
    assert result.status == "finished"
    assert result.is_error is False
    assert "content" not in result.model_dump()
    assert "status" not in result.model_dump()
    assert [validate_sdk_message(message.model_dump()) for message in messages] == messages


def test_sdk_query_emits_requires_action_state_for_approval_pause():
    client = AgentSDKClient(session_factory=_approval_session_factory)

    messages = asyncio.run(_collect(client.query("write", SDKOptions(session_id="session-approval"))))
    replay = asyncio.run(client.get_session_messages("session-approval"))

    states = [message.state for message in messages if isinstance(message, SDKSessionStateChangedMessage)]
    assert states == ["running", "requires_action"]
    assert any(
        isinstance(message, SDKToolProgressMessage) and message.status == "awaiting_approval"
        for message in messages
    )
    assert [message.state for message in replay if isinstance(message, SDKSessionStateChangedMessage)] == states


def test_sdk_query_projects_model_retry_as_system_api_retry_message():
    client = AgentSDKClient(session_factory=_retry_session_factory)

    messages = asyncio.run(_collect(client.query("retry please", SDKOptions(session_id="session-1"))))

    retry = next(message for message in messages if isinstance(message, SDKAPIRetryMessage))
    assert retry.type == "system"
    assert retry.subtype == "api_retry"
    assert retry.attempt == 2
    assert retry.max_retries == 3
    assert retry.retry_delay_ms == 250
    assert retry.error_status is None
    assert retry.error["message"] == "connect failed"
    assert validate_sdk_message(retry.model_dump()) == retry


def test_sdk_query_projects_reasoning_delta_as_stream_event_message():
    client = AgentSDKClient(session_factory=_reasoning_session_factory)

    messages = asyncio.run(_collect(client.query("think", SDKOptions(session_id="session-reasoning"))))

    stream = next(message for message in messages if isinstance(message, SDKStreamEventMessage))
    assert stream.type == "stream_event"
    assert stream.event == {
        "type": "content_block_delta",
        "delta": {"type": "thinking_delta", "thinking": "checking assumptions"},
    }
    assert stream.parent_tool_use_id is None
    assert validate_sdk_message(stream.model_dump()) == stream


def test_sdk_query_projects_assistant_message_shape():
    client = AgentSDKClient(session_factory=_assistant_message_session_factory)

    messages = asyncio.run(_collect(client.query("answer", SDKOptions(session_id="session-assistant"))))
    replay = asyncio.run(client.get_session_messages("session-assistant", {"include_system_messages": False}))

    assistant = next(message for message in messages if isinstance(message, SDKAssistantMessage))
    assert assistant.type == "assistant"
    assert assistant.uuid == "assistant-message-1"
    assert assistant.parent_tool_use_id is None
    assert assistant.message["role"] == "assistant"
    assert assistant.message["content"][0]["text"] == "assistant answer"
    assert assistant.content == "assistant answer"
    assert "content" not in assistant.model_dump()
    assert validate_sdk_message(assistant.model_dump()) == assistant
    assert any(isinstance(message, SDKAssistantMessage) for message in replay)


def test_sdk_query_projects_context_fit_as_compact_boundary_message():
    client = AgentSDKClient(session_factory=_compacting_session_factory)

    messages = asyncio.run(_collect(client.query("new prompt", SDKOptions(session_id="session-compact"))))
    replay = asyncio.run(client.get_session_messages("session-compact"))

    boundary = next(message for message in messages if isinstance(message, SDKCompactBoundaryMessage))
    assert boundary.type == "system"
    assert boundary.subtype == "compact_boundary"
    assert boundary.compact_metadata["trigger"] == "auto"
    assert boundary.compact_metadata["pre_tokens"] > boundary.compact_metadata["post_tokens"]
    assert boundary.compact_metadata["before_messages"] >= boundary.compact_metadata["after_messages"]
    assert validate_sdk_message(boundary.model_dump()) == boundary
    assert isinstance(replay[1], SDKUserMessage)
    assert any(isinstance(message, SDKCompactBoundaryMessage) for message in replay)


def test_sdk_query_emits_auth_status_for_mcp_auth_tool_results():
    client = AgentSDKClient(session_factory=_auth_session_factory)

    messages = asyncio.run(_collect(client.query("auth", SDKOptions(session_id="session-auth"))))
    replay = asyncio.run(client.get_session_messages("session-auth", {"include_system_messages": False}))

    auth = next(message for message in messages if isinstance(message, SDKAuthStatusMessage))
    assert auth.type == "auth_status"
    assert auth.is_authenticating is True
    assert auth.output == ["Open the authorization URL.", "https://mcp.example.test/oauth"]
    assert auth.error == ""
    assert auth.metadata["server"] == "docs"
    assert validate_sdk_message(auth.model_dump()) == auth
    assert any(isinstance(message, SDKToolProgressMessage) and message.status == "completed" for message in messages)
    assert any(isinstance(message, SDKAuthStatusMessage) for message in replay)


def test_sdk_query_emits_task_messages_from_task_tool_results():
    client = AgentSDKClient(session_factory=_task_session_factory)

    messages = asyncio.run(_collect(client.query("run task", SDKOptions(session_id="session-task"))))
    replay = asyncio.run(client.get_session_messages("session-task", {"include_system_messages": False}))

    started = next(message for message in messages if isinstance(message, SDKTaskStartedMessage))
    progress = next(message for message in messages if isinstance(message, SDKTaskProgressMessage))
    notification = next(message for message in messages if isinstance(message, SDKTaskNotificationMessage))

    assert started.task_id == "task_123"
    assert started.tool_use_id == "task-run-call"
    assert started.description == "Run tracked work"
    assert started.task_type == "agent"
    assert started.prompt == "do the work"
    assert progress.task_id == "task_123"
    assert progress.tool_use_id == "task-update-call"
    assert progress.last_tool_name == "review"
    assert notification.status == "completed"
    assert notification.summary == "executed child"
    assert notification.usage == {"total_tokens": 0, "tool_uses": 2, "duration_ms": 0}
    assert validate_sdk_message(started.model_dump()) == started
    assert any(isinstance(message, SDKTaskStartedMessage) for message in replay)
    assert any(isinstance(message, SDKTaskNotificationMessage) for message in replay)


def test_sdk_query_emits_files_persisted_from_artifact_results():
    client = AgentSDKClient(session_factory=_artifact_session_factory)

    messages = asyncio.run(_collect(client.query("open page", SDKOptions(session_id="session-artifact"))))
    replay = asyncio.run(client.get_session_messages("session-artifact", {"include_system_messages": False}))

    persisted = next(message for message in messages if isinstance(message, SDKFilesPersistedMessage))
    assert persisted.type == "system"
    assert persisted.subtype == "files_persisted"
    assert persisted.files == [{"filename": "browser-open.html", "file_id": "artifact_123"}]
    assert persisted.failed == []
    assert persisted.processed_at.startswith("2023-11-14T")
    assert validate_sdk_message(persisted.model_dump()) == persisted
    assert any(isinstance(message, SDKFilesPersistedMessage) for message in replay)


def test_sdk_query_projects_hook_lifecycle_system_messages():
    client = AgentSDKClient(session_factory=_hook_session_factory)

    messages = asyncio.run(_collect(client.query("run hook", SDKOptions(session_id="session-hooks"))))
    replay = asyncio.run(client.get_session_messages("session-hooks", {"include_system_messages": False}))

    started = next(message for message in messages if isinstance(message, SDKHookStartedMessage))
    progress = next(message for message in messages if isinstance(message, SDKHookProgressMessage))
    response = next(message for message in messages if isinstance(message, SDKHookResponseMessage))

    assert started.type == "system"
    assert started.subtype == "hook_started"
    assert started.hook_id == "hook_123"
    assert started.hook_name == "block-shell"
    assert started.hook_event == "PreToolUse"
    assert progress.stdout == "checking shell"
    assert progress.output == "checking shell"
    assert response.output == "blocked"
    assert response.exit_code == 0
    assert response.outcome == "success"
    assert [
        type(message)
        for message in replay
        if isinstance(message, (SDKHookStartedMessage, SDKHookProgressMessage, SDKHookResponseMessage))
    ] == [
        SDKHookStartedMessage,
        SDKHookProgressMessage,
        SDKHookResponseMessage,
    ]
    assert validate_sdk_message(response.model_dump()) == response


def test_sdk_query_projects_local_command_output_system_message():
    client = AgentSDKClient(session_factory=_local_command_session_factory)

    messages = asyncio.run(_collect(client.query("/model opus", SDKOptions(session_id="session-local-command"))))
    replay = asyncio.run(client.get_session_messages("session-local-command", {"include_system_messages": False}))

    output = next(message for message in messages if isinstance(message, SDKLocalCommandOutputMessage))
    assert output.type == "system"
    assert output.subtype == "local_command_output"
    assert output.content == "Switched to opus"
    assert output.uuid == "local-command-1"
    assert validate_sdk_message(output.model_dump()) == output
    assert any(isinstance(message, SDKLocalCommandOutputMessage) for message in replay)


def test_sdk_query_projects_extension_system_messages():
    client = AgentSDKClient(session_factory=_sdk_extension_event_session_factory)

    messages = asyncio.run(_collect(client.query("extensions", SDKOptions(session_id="session-extensions"))))
    replay = asyncio.run(client.get_session_messages("session-extensions", {"include_system_messages": False}))

    rate_limit = next(message for message in messages if isinstance(message, SDKRateLimitEventMessage))
    elicitation = next(message for message in messages if isinstance(message, SDKElicitationCompleteMessage))
    suggestion = next(message for message in messages if isinstance(message, SDKPromptSuggestionMessage))
    status = next(message for message in messages if isinstance(message, SDKStatusMessage))
    summary = next(message for message in messages if isinstance(message, SDKPostTurnSummaryMessage))

    assert rate_limit.type == "rate_limit_event"
    assert rate_limit.rate_limit_info["isNearLimit"] is True
    assert elicitation.subtype == "elicitation_complete"
    assert elicitation.mcp_server_name == "docs"
    assert elicitation.elicitation_id == "elicit_123"
    assert suggestion.type == "prompt_suggestion"
    assert suggestion.suggestion == "Run the tests"
    assert status.type == "system"
    assert status.subtype == "status"
    assert status.status == "compacting"
    assert status.permissionMode == "ask"
    assert summary.subtype == "post_turn_summary"
    assert summary.summarizes_uuid == "assistant-1"
    assert summary.status_category == "review_ready"
    assert summary.artifact_urls == ["artifact://report"]
    assert validate_sdk_message(rate_limit.model_dump()) == rate_limit
    assert validate_sdk_message(status.model_dump()) == status
    assert validate_sdk_message(summary.model_dump()) == summary
    assert any(isinstance(message, SDKPromptSuggestionMessage) for message in replay)
    assert any(isinstance(message, SDKPostTurnSummaryMessage) for message in replay)


def test_sdk_prompt_returns_final_result():
    client = AgentSDKClient(session_factory=_session_factory)

    result = asyncio.run(client.prompt("say hi"))

    assert result.type == "result"
    assert result.content == "done"
    assert result.result == "done"
    assert result.subtype == "success"


def test_sdk_query_projects_execution_errors_as_src_origin_result_shape():
    client = AgentSDKClient(session_factory=_failing_session_factory)

    messages = asyncio.run(_collect(client.query("fail", SDKOptions(session_id="session-error"))))

    result = next(message for message in messages if isinstance(message, SDKResultMessage))
    assert result.type == "result"
    assert result.subtype == "error_during_execution"
    assert result.is_error is True
    assert result.status == "error"
    assert result.error == "model transport failed"
    assert result.errors == ["model transport failed"]
    assert result.result == ""
    assert "error" not in result.model_dump()
    assert validate_sdk_message(result.model_dump()) == result


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
    assert isinstance(messages[1], SDKUserMessage)
    assert messages[1].content == "first meaningful prompt"
    assert messages[1].message["content"][0]["text"] == "first meaningful prompt"
    assert any(isinstance(message, SDKToolProgressMessage) and message.status == "started" for message in messages)
    assert any(isinstance(message, SDKResultMessage) and message.content == "done" for message in messages)
    stored_result = next(message for message in messages if isinstance(message, SDKResultMessage))
    assert stored_result.result == "done"

    asyncio.run(client.rename_session("session-1", "Pinned title"))
    asyncio.run(client.tag_session("session-1", "review"))
    renamed = asyncio.run(client.get_session_info("session-1"))
    paged = asyncio.run(client.list_sessions(SDKListSessionsOptions(limit=1, offset=0)))
    replay_without_system = asyncio.run(
        client.get_session_messages("session-1", {"include_system_messages": False, "limit": 1})
    )

    assert renamed.summary == "Pinned title"
    assert renamed.custom_title == "Pinned title"
    assert renamed.tag == "review"
    assert paged[0].summary == "Pinned title"
    assert all(message.type != "system" for message in replay_without_system)
    assert len(replay_without_system) == 1
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


def test_sdk_fork_session_copies_stored_runs_into_new_session():
    client = AgentSDKClient(session_factory=_session_factory)
    session = client.create_sdk_session(SDKOptions(session_id="source-session"))

    first = asyncio.run(session.prompt("source turn one"))
    second = asyncio.run(session.prompt("source turn two"))
    result = asyncio.run(
        client.fork_session("source-session", SDKForkSessionOptions(title="Forked copy"))
    )
    forked = asyncio.run(client.resume_session(result.session_id))
    forked_info = asyncio.run(forked.info())
    forked_messages = asyncio.run(forked.messages({"include_system_messages": False}))

    assert isinstance(result, SDKForkSessionResult)
    assert result.session_id != "source-session"
    assert len(result.run_ids) == 2
    assert forked_info.summary == "Forked copy"
    assert forked_info.first_prompt == "source turn one"
    assert forked_info.metadata["sdk_forked_from_session_id"] == "source-session"
    forked_result_run_ids = [
        message.run_id for message in forked_messages if message.type == "result"
    ]
    assert forked_result_run_ids == result.run_ids

    source_info = asyncio.run(session.info())
    assert source_info.run_ids == [first.run_id, second.run_id]
    source_messages = asyncio.run(session.messages({"include_system_messages": False}))
    first_user_message = next(message for message in source_messages if isinstance(message, SDKUserMessage))
    partial = asyncio.run(
        client.fork_session(
            "source-session",
            SDKForkSessionOptions(title="Partial fork", up_to_message_id=first_user_message.uuid),
        )
    )
    partial_messages = asyncio.run(
        client.get_session_messages(partial.session_id, {"include_system_messages": False})
    )
    assert len(partial.run_ids) == 1
    assert [message.type for message in partial_messages] == ["user"]
    assert partial_messages[0].content == "source turn one"


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
    assistant_schema = message_schema["$defs"]["SDKAssistantMessage"]["properties"]
    user_schema = message_schema["$defs"]["SDKUserMessage"]["properties"]
    system_schema = message_schema["$defs"]["SDKSystemMessage"]["properties"]
    assert "message" in assistant_schema
    assert "parent_tool_use_id" in assistant_schema
    assert "content" not in assistant_schema
    assert "raw" not in assistant_schema
    assert "isSynthetic" in user_schema
    assert "is_synthetic" not in user_schema
    assert "apiKeySource" in system_schema
    assert "claude_code_version" in system_schema
    assert "mcp_servers" in system_schema
    assert "permissionMode" in system_schema
    assert "slash_commands" in system_schema
    assert "output_style" in system_schema
    assert "skills" in system_schema
    assert "plugins" in system_schema
    assert "uuid" in system_schema
    assert "protocol" not in system_schema
    assert "metadata" not in system_schema
    assert "SDKSystemMessage" in message_schema["$defs"]
    assert "SDKAPIRetryMessage" in message_schema["$defs"]
    assert "SDKAuthStatusMessage" in message_schema["$defs"]
    assert "SDKCompactBoundaryMessage" in message_schema["$defs"]
    assert "SDKFilesPersistedMessage" in message_schema["$defs"]
    assert "SDKHookStartedMessage" in message_schema["$defs"]
    assert "SDKHookProgressMessage" in message_schema["$defs"]
    assert "SDKHookResponseMessage" in message_schema["$defs"]
    assert "SDKLocalCommandOutputMessage" in message_schema["$defs"]
    assert "SDKRateLimitEventMessage" in message_schema["$defs"]
    assert "SDKElicitationCompleteMessage" in message_schema["$defs"]
    assert "SDKPromptSuggestionMessage" in message_schema["$defs"]
    assert "SDKPostTurnSummaryMessage" in message_schema["$defs"]
    assert "SDKSessionStateChangedMessage" in message_schema["$defs"]
    assert "SDKStreamEventMessage" in message_schema["$defs"]
    assert "SDKTaskStartedMessage" in message_schema["$defs"]
    assert "SDKTaskProgressMessage" in message_schema["$defs"]
    assert "SDKTaskNotificationMessage" in message_schema["$defs"]
    assert "SDKToolUseSummaryMessage" in message_schema["$defs"]
    assert "SDKUserMessage" in message_schema["$defs"]
    assert "SDKToolProgressMessage" in message_schema["$defs"]
    assert result_schema["properties"]["type"]["const"] == "result"
    assert "result" in result_schema["properties"]
    assert "is_error" in result_schema["properties"]
    assert "duration_api_ms" in result_schema["properties"]
    assert "total_cost_usd" in result_schema["properties"]
    assert "modelUsage" in result_schema["properties"]
    assert "permission_denials" in result_schema["properties"]
    assert "content" not in result_schema["properties"]
    assert "status" not in result_schema["properties"]
    assert session_schema["properties"]["session_id"]["title"] == "Session Id"

    valid = validate_sdk_message(
        {
            "type": "result",
            "subtype": "success",
            "session_id": "session-1",
            "run_id": "run-1",
            "result": "done",
            "is_error": False,
            "duration_ms": 10,
            "duration_api_ms": 8,
            "num_turns": 1,
            "stop_reason": "finished",
            "total_cost_usd": 0.0,
            "usage": {},
            "modelUsage": {},
            "permission_denials": [],
            "uuid": "result-1",
        }
    )
    assert isinstance(valid, SDKResultMessage)
    assert valid.status == "finished"
    assert valid.content == "done"

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
