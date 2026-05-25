import asyncio
import base64
import json
import os
import shlex
import shutil
import sys
import tempfile
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from agents.kernel.mcp_config import InMemoryMCPConfigStore, MCPServerRecord
from agents.kernel.schema import Message, ModelResponse, RuntimeEvent, ToolCall
from agents.kernel.models.protocol import message_event, reasoning_delta, retry_event, text_delta
from agents.kernel.runtime import AgentRuntime, AgentSession, ScriptedModelClient
from agents.kernel.capabilities.sandbox.local import LocalSandboxProvider
from agents.kernel.capabilities.tools.context import ToolRuntimeContext
from agents.kernel.capabilities.tools.builtin import register_builtin_tools
from agents.kernel.capabilities.tools.builtin.file_safety import write_text_safely
from agents.kernel.capabilities.tools.builtin.sleep import sleep_wait
from agents.kernel.capabilities.tools.mcp import MCPServerConfig, MCPToolDefinition, MCPToolProvider
from agents.kernel.capabilities.tools.registry import ToolRegistry
from agents.kernel.context.workspace import WorkspaceContext
from agents.kernel.governance import SandboxPolicy
from agents.kernel.specs import AgentSpec
from agents.kernel.tasks import TaskStatus
from agents.sdk import (
    AgentSDKClient,
    SDKControlApplyFlagSettingsRequest,
    SDKControlCancelAsyncMessageRequest,
    SDKControlCancelRequest,
    SDKControlElicitationRequest,
    SDKControlErrorResponse,
    SDKControlGetSettingsRequest,
    SDKControlInitializeRequest,
    SDKControlInterruptRequest,
    SDKControlMcpMessageRequest,
    SDKControlMcpReconnectRequest,
    SDKControlMcpSetServersRequest,
    SDKControlMcpStatusRequest,
    SDKControlMcpToggleRequest,
    SDKControlPermissionRequest,
    SDKControlRequest,
    SDKControlRequestCancelledError,
    SDKControlResponse,
    SDKControlRewindFilesRequest,
    SDKControlSeedReadStateRequest,
    SDKControlSetModelRequest,
    SDKControlSetPermissionModeRequest,
    SDKControlStopTaskRequest,
    SDKControlStreamClosedError,
    SDKControlSuccessResponse,
    SDKCCRAuthFailureError,
    SDKCCRClient,
    SDKCCRRequestResult,
    SDKCCREpochMismatchError,
    SDKWorkerStateUploader,
    SDKHookCallbackRequest,
    SDKKeepAliveMessage,
    SDKForkSessionOptions,
    SDKForkSessionResult,
    SDKHybridJsonlTransport,
    SDKListSessionsOptions,
    SDKOptions,
    SDKQueueJsonlTransport,
    SDKSSEJsonlTransport,
    SDKSessionInfo,
    SDKSession,
    SDKStructuredIO,
    SDKStdinDecodeError,
    SDKUpdateEnvironmentVariablesMessage,
    SDKWebSocketConnectOptions,
    SDKWebSocketJsonlTransport,
    encode_stdout_message,
    derive_hybrid_post_url,
    derive_sse_post_url,
    derive_sse_stream_url,
    handle_control_request,
    iter_stdin_jsonl,
    ndjson_safe_dumps,
    normalize_sdk_control_message_keys,
    parse_sse_frames,
    run_jsonl_transport,
    sdk_control_request_json_schema,
    sdk_control_response_json_schema,
    sdk_message_json_schema,
    sdk_options_json_schema,
    sdk_result_json_schema,
    sdk_session_info_json_schema,
    sdk_stdin_message_json_schema,
    sdk_stdout_message_json_schema,
    validate_sdk_control_request,
    validate_sdk_control_response,
    validate_sdk_message,
    validate_sdk_stdin_message,
    validate_sdk_stdout_message,
    run_stdin,
    run_stdin_jsonl,
)
from agents.sdk.client import _project_runtime_event_messages, _spec_from_options
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


class _AnsweringMCPClient:
    def __init__(self, prefix: str, server=None):
        self.prefix = prefix
        self.server = server
        self.called = []
        self.closed = False

    async def list_tools(self):
        return [
            MCPToolDefinition(
                name="search",
                description="Search docs",
                parameters={"type": "object", "properties": {"query": {"type": "string"}}},
            )
        ]

    async def call_tool(self, name, arguments):
        self.called.append((name, arguments))
        return {"answer": "%s:%s" % (self.prefix, arguments["query"])}

    async def list_resources(self):
        return []

    async def read_resource(self, uri):
        raise RuntimeError("resources unavailable")

    async def list_prompts(self):
        return []

    async def get_prompt(self, name, arguments=None):
        raise RuntimeError("prompts unavailable")

    async def close(self):
        self.closed = True


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


async def _shell_task_session_factory(settings, spec):
    shell_workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=".",
        path=".",
    )

    class ShellTaskSession:
        runtime = SimpleNamespace(model="scripted", protocol="scripted", enabled_tools=["shell.run", "shell.output"])
        workspace = shell_workspace

        async def stream(self, text, run_id=None):
            yield RuntimeEvent(
                type="task_started",
                name="shell.run",
                payload={
                    "task_id": "shell_123",
                    "tool_call_id": "shell-run-call",
                    "description": "Run background shell",
                    "task_type": "shell",
                    "prompt": "python -m pytest",
                },
            )
            yield RuntimeEvent(
                type="task_notification",
                name="shell.output",
                payload={
                    "task_id": "shell_123",
                    "tool_call_id": "shell-output-call",
                    "status": "completed",
                    "output_file": ".agents/task-output/shell_123.log",
                    "summary": "tests passed",
                    "usage": {"total_tokens": 0, "tool_uses": 0, "duration_ms": 42},
                },
            )
            yield RuntimeEvent(type="done", name="assistant", payload={"content": "shell done", "status": "finished"})

    return ShellTaskSession()


async def _shell_background_notification_session_factory(settings, spec):
    workspace_dir = tempfile.TemporaryDirectory()
    workspace_path = Path(workspace_dir.name)
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=workspace_path,
        path=workspace_path,
    )
    policy = SandboxPolicy.for_workspace(
        workspace.path,
        allow_process=True,
        allowed_commands=(Path(sys.executable).name,),
    )
    context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=policy,
        sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
    )
    registry = ToolRegistry()
    register_builtin_tools(registry, context)

    class ShellBackgroundNotificationSession:
        runtime = SimpleNamespace(model="scripted", protocol="scripted", enabled_tools=["shell.run"])
        tool_context = context

        def __init__(self):
            self.workspace = workspace

        async def stream(self, text, run_id=None):
            if "<task_notification>" in str(text):
                yield RuntimeEvent(
                    type="done",
                    name="assistant",
                    payload={"content": "notification drained", "status": "finished"},
                )
                return

            script = "import time; print('start', flush=True); time.sleep(0.05); print('done', flush=True)"
            result = await registry.execute(
                "shell.run",
                {
                    "command": "%s -c %s" % (shlex.quote(sys.executable), shlex.quote(script)),
                    "run_in_background": True,
                    "timeout_seconds": 2,
                    "description": "Run SDK notification script",
                },
                run_id=run_id or "",
                tool_call_id="call-shell-bg",
            )
            yield RuntimeEvent(
                type="tool_result",
                name="shell.run",
                payload={"tool_call_id": "call-shell-bg", "raw": result.raw},
            )
            handle = context.background_commands[result.raw["task_id"]]
            await handle._task
            await asyncio.sleep(0)
            yield RuntimeEvent(
                type="done",
                name="assistant",
                payload={"content": "started background", "status": "finished"},
            )

        async def aclose(self):
            workspace_dir.cleanup()

    return ShellBackgroundNotificationSession()


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


async def _rewind_patch_session_factory(settings, spec):
    workspace_path = str(spec.workspace.path or spec.workspace.root or ".")
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=workspace_path,
        path=workspace_path,
    )

    class RewindPatchSession:
        runtime = SimpleNamespace(model="scripted", protocol="scripted", enabled_tools=["patch.apply"])

        def __init__(self):
            self.workspace = workspace

        async def stream(self, text, run_id=None):
            notes = Path(workspace_path) / "notes.txt"
            notes.write_text("new\n", encoding="utf-8")
            yield RuntimeEvent(
                type="tool_result",
                name="patch.apply",
                payload={
                    "tool_call_id": "patch-edit",
                    "raw": {
                        "changed": True,
                        "files": [{"path": "notes.txt", "action": "edit", "edits": 1, "bytes": 4}],
                        "filePath": "notes.txt",
                        "oldString": "old",
                        "newString": "new",
                        "originalFile": "old\n",
                        "structuredPatch": [
                            {
                                "oldStart": 1,
                                "oldLines": 1,
                                "newStart": 1,
                                "newLines": 1,
                                "lines": ["-old", "+new"],
                            }
                        ],
                    },
                },
            )
            created = Path(workspace_path) / "created.txt"
            created.write_text("created\n", encoding="utf-8")
            yield RuntimeEvent(
                type="tool_result",
                name="patch.apply",
                payload={
                    "tool_call_id": "patch-create",
                    "raw": {
                        "changed": True,
                        "files": [{"path": "created.txt", "action": "create", "edits": 0, "bytes": 8}],
                        "structuredPatches": [
                            {
                                "filePath": "created.txt",
                                "hunks": [
                                    {
                                        "oldStart": 1,
                                        "oldLines": 0,
                                        "newStart": 1,
                                        "newLines": 1,
                                        "lines": ["+created"],
                                    }
                                ],
                            }
                        ],
                    },
                },
            )
            write_note = Path(workspace_path) / "write.txt"
            yield RuntimeEvent(
                type="tool_result",
                name="filesystem.read",
                payload={
                    "tool_call_id": "read-write-note",
                    "raw": {
                        "path": "write.txt",
                        "content": "old write\n",
                        "file": {"filePath": "write.txt", "content": "old write\n"},
                        "truncated": False,
                        "isPartialView": False,
                    },
                },
            )
            write_note.write_text("new write\n", encoding="utf-8")
            yield RuntimeEvent(
                type="tool_result",
                name="filesystem.write",
                payload={
                    "tool_call_id": "write-note",
                    "raw": {
                        "path": "write.txt",
                        "bytes": 10,
                        "encoding": "utf-8",
                        "safety": {"required_prior_read": True, "encoding": "utf-8"},
                    },
                },
            )
            original_notebook = json.dumps({"cells": [{"cell_type": "code", "source": "print(1)\n"}]})
            updated_notebook = json.dumps({"cells": [{"cell_type": "code", "source": "print(2)\n"}]})
            notebook = Path(workspace_path) / "analysis.ipynb"
            notebook.write_text(updated_notebook, encoding="utf-8")
            yield RuntimeEvent(
                type="tool_result",
                name="notebook.edit",
                payload={
                    "tool_call_id": "notebook-edit",
                    "raw": {
                        "notebook_path": "analysis.ipynb",
                        "original_file": original_notebook,
                        "updated_file": updated_notebook,
                        "structuredPatch": [
                            {
                                "oldStart": 1,
                                "oldLines": 1,
                                "newStart": 1,
                                "newLines": 1,
                                "lines": ["-print(1)", "+print(2)"],
                            }
                        ],
                    },
                },
            )
            yield RuntimeEvent(type="done", name="assistant", payload={"content": "edited", "status": "finished"})

    return RewindPatchSession()


async def _rewind_multi_turn_session_factory(settings, spec):
    workspace_path = str(spec.workspace.path or spec.workspace.root or ".")
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=workspace_path,
        path=workspace_path,
    )

    class RewindMultiTurnSession:
        runtime = SimpleNamespace(model="scripted", protocol="scripted", enabled_tools=["patch.apply"])

        def __init__(self):
            self.workspace = workspace

        async def stream(self, text, run_id=None):
            note = Path(workspace_path) / "turn-note.txt"
            if text == "first edit":
                note.write_text("v1\n", encoding="utf-8")
                yield RuntimeEvent(
                    type="tool_result",
                    name="patch.apply",
                    payload={
                        "tool_call_id": "patch-first-edit",
                        "raw": {
                            "changed": True,
                            "files": [{"path": "turn-note.txt", "action": "edit", "edits": 1, "bytes": 3}],
                            "filePath": "turn-note.txt",
                            "oldString": "v0",
                            "newString": "v1",
                            "originalFile": "v0\n",
                            "structuredPatch": [
                                {
                                    "oldStart": 1,
                                    "oldLines": 1,
                                    "newStart": 1,
                                    "newLines": 1,
                                    "lines": ["-v0", "+v1"],
                                }
                            ],
                        },
                    },
                )
            elif text == "second edit":
                note.write_text("v2\n", encoding="utf-8")
                yield RuntimeEvent(
                    type="tool_result",
                    name="patch.apply",
                    payload={
                        "tool_call_id": "patch-second-edit",
                        "raw": {
                            "changed": True,
                            "files": [{"path": "turn-note.txt", "action": "edit", "edits": 1, "bytes": 3}],
                            "filePath": "turn-note.txt",
                            "oldString": "v1",
                            "newString": "v2",
                            "originalFile": "v1\n",
                            "structuredPatch": [
                                {
                                    "oldStart": 1,
                                    "oldLines": 1,
                                    "newStart": 1,
                                    "newLines": 1,
                                    "lines": ["-v1", "+v2"],
                                }
                            ],
                        },
                    },
                )
            yield RuntimeEvent(type="done", name="assistant", payload={"content": "ok", "status": "finished"})

    return RewindMultiTurnSession()


async def _src_origin_write_rewind_session_factory(settings, spec):
    workspace_path = str(spec.workspace.path or spec.workspace.root or ".")
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=workspace_path,
        path=workspace_path,
    )

    class SrcOriginWriteRewindSession:
        runtime = SimpleNamespace(model="scripted", protocol="scripted", enabled_tools=["Write"])

        def __init__(self):
            self.workspace = workspace

        async def stream(self, text, run_id=None):
            note = Path(workspace_path) / "origin-write.txt"
            note.write_text("after\nextra\n", encoding="utf-8")
            yield RuntimeEvent(
                type="tool_result",
                name="Write",
                payload={
                    "tool_call_id": "write-update",
                    "raw": {
                        "data": {
                            "type": "update",
                            "filePath": "origin-write.txt",
                            "content": "after\nextra\n",
                            "originalFile": "before\n",
                            "structuredPatch": [
                                {
                                    "oldStart": 1,
                                    "oldLines": 1,
                                    "newStart": 1,
                                    "newLines": 2,
                                    "lines": ["-before", "+after", "+extra"],
                                }
                            ],
                        }
                    },
                },
            )
            created = Path(workspace_path) / "origin-created.txt"
            created.write_text("new file\n", encoding="utf-8")
            yield RuntimeEvent(
                type="tool_result",
                name="Write",
                payload={
                    "tool_call_id": "write-create",
                    "raw": {
                        "data": {
                            "type": "create",
                            "filePath": "origin-created.txt",
                            "content": "new file\n",
                            "structuredPatch": [],
                            "originalFile": None,
                        }
                    },
                },
            )
            yield RuntimeEvent(type="done", name="assistant", payload={"content": "edited", "status": "finished"})

    return SrcOriginWriteRewindSession()


async def _file_history_snapshot_rewind_session_factory(settings, spec):
    workspace_path = str(spec.workspace.path or spec.workspace.root or ".")
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=workspace_path,
        path=workspace_path,
    )

    class FileHistorySnapshotRewindSession:
        runtime = SimpleNamespace(model="scripted", protocol="scripted", enabled_tools=["Write"])

        def __init__(self):
            self.workspace = workspace

        async def stream(self, text, run_id=None):
            note = Path(workspace_path) / "snapshot-note.txt"
            created = Path(workspace_path) / "snapshot-created.txt"
            note.write_text("after\nextra\n", encoding="utf-8")
            created.write_text("created\n", encoding="utf-8")
            yield RuntimeEvent(
                type="file-history-snapshot",
                name="file-history",
                payload={
                    "type": "file-history-snapshot",
                    "messageId": "msg-snapshot-rewind",
                    "snapshot": {
                        "messageId": "msg-snapshot-rewind",
                        "trackedFileBackups": {},
                        "timestamp": "2026-05-21T00:00:00.000Z",
                    },
                    "isSnapshotUpdate": False,
                },
            )
            yield RuntimeEvent(
                type="file-history-snapshot",
                name="file-history",
                payload={
                    "type": "file-history-snapshot",
                    "messageId": "msg-snapshot-rewind",
                    "snapshot": {
                        "messageId": "msg-snapshot-rewind",
                        "trackedFileBackups": {
                            "snapshot-note.txt": {
                                "backupFileName": "snapshot-note@v1",
                                "version": 1,
                                "backupTime": "2026-05-21T00:00:00.000Z",
                            },
                            "snapshot-created.txt": {
                                "backupFileName": None,
                                "version": 1,
                                "backupTime": "2026-05-21T00:00:00.000Z",
                            },
                        },
                        "timestamp": "2026-05-21T00:00:01.000Z",
                    },
                    "isSnapshotUpdate": True,
                },
            )
            yield RuntimeEvent(type="done", name="assistant", payload={"content": "edited", "status": "finished"})

    return FileHistorySnapshotRewindSession()


async def _read_state_seed_session_factory(settings, spec):
    workspace_path = str(spec.workspace.path or spec.workspace.root or ".")
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=workspace_path,
        path=workspace_path,
    )
    tool_context = ToolRuntimeContext(
        workspace=workspace,
        sandbox=SandboxPolicy.for_workspace(workspace.path, allow_file_write=True),
    )

    class ReadStateSeedSession:
        runtime = SimpleNamespace(model="scripted", protocol="scripted", enabled_tools=["filesystem.write"])

        def __init__(self):
            self.workspace = workspace
            self.tool_context = tool_context

        async def stream(self, text, run_id=None):
            try:
                write_text_safely(self.tool_context, "notes.txt", "updated\n")
                content = "seeded write"
            except Exception as exc:
                content = "error: %s" % exc
            yield RuntimeEvent(type="done", name="assistant", payload={"content": content, "status": "finished"})

    return ReadStateSeedSession()


async def _echo_prompt_session_factory(settings, spec):
    echo_workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=".",
        path=".",
    )

    class EchoPromptSession:
        runtime = SimpleNamespace(model="scripted", protocol="scripted", enabled_tools=[])
        workspace = echo_workspace

        async def stream(self, text, run_id=None):
            yield RuntimeEvent(type="done", name="assistant", payload={"content": str(text), "status": "finished"})

    return EchoPromptSession()


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
    assert "run_id" not in init.model_dump()
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
    assert "run_id" not in result.model_dump()
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


def test_sdk_projects_runtime_tool_progress_details():
    [message] = _project_runtime_event_messages(
        RuntimeEvent(
            type="tool_progress",
            name="shell.run",
            payload={
                "tool_call_id": "call-shell",
                "tool_name": "shell.run",
                "status": "stalled",
                "input": {"command": "pytest -q"},
                "output": "still running",
                "full_output": "still running\n",
                "elapsed_time_seconds": 12,
                "total_lines": 1,
                "total_bytes": 14,
                "task_id": "shell_123",
                "timeout_ms": 20000,
                "metadata": {"progress_type": "bash_progress", "stalled": True},
            },
        ),
        session_id="session-1",
        run_id="run-1",
        duration_ms=0,
        num_turns=1,
    )

    assert isinstance(message, SDKToolProgressMessage)
    assert message.status == "stalled"
    assert message.tool_call_id == "call-shell"
    assert message.output == "still running"
    assert message.full_output == "still running\n"
    assert message.elapsed_time_seconds == 12
    assert message.total_lines == 1
    assert message.total_bytes == 14
    assert message.task_id == "shell_123"
    assert message.timeout_ms == 20000
    assert message.metadata["progress_type"] == "bash_progress"
    assert validate_sdk_message(message.model_dump()) == message


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
    assert "run_id" not in assistant.model_dump()
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


def test_sdk_query_emits_task_messages_from_shell_lifecycle_events():
    client = AgentSDKClient(session_factory=_shell_task_session_factory)

    messages = asyncio.run(_collect(client.query("run shell", SDKOptions(session_id="session-shell-task"))))
    replay = asyncio.run(client.get_session_messages("session-shell-task", {"include_system_messages": False}))

    started = next(message for message in messages if isinstance(message, SDKTaskStartedMessage))
    notification = next(message for message in messages if isinstance(message, SDKTaskNotificationMessage))

    assert started.task_id == "shell_123"
    assert started.tool_use_id == "shell-run-call"
    assert started.description == "Run background shell"
    assert started.task_type == "shell"
    assert started.prompt == "python -m pytest"
    assert notification.task_id == "shell_123"
    assert notification.tool_use_id == "shell-output-call"
    assert notification.status == "completed"
    assert notification.output_file == ".agents/task-output/shell_123.log"
    assert notification.summary == "tests passed"
    assert notification.usage == {"total_tokens": 0, "tool_uses": 0, "duration_ms": 42}
    assert any(isinstance(message, SDKTaskStartedMessage) for message in replay)
    assert any(isinstance(message, SDKTaskNotificationMessage) for message in replay)


def test_sdk_session_drains_shell_background_completion_notification():
    client = AgentSDKClient(session_factory=_shell_background_notification_session_factory)
    session = client.create_sdk_session(SDKOptions(session_id="shell-background-drain"))

    async def execute():
        messages = await _collect(session.query("start shell background"))
        replay = await client.get_session_messages("shell-background-drain", {"include_system_messages": False})
        return messages, replay

    messages, replay = asyncio.run(execute())

    results = [message for message in messages if isinstance(message, SDKResultMessage)]
    user_messages = [message for message in replay if isinstance(message, SDKUserMessage)]
    notification_user = next(message for message in user_messages if "<task_notification>" in message.content)

    assert [message.result for message in results] == ["started background", "notification drained"]
    assert notification_user.priority == "later"
    assert notification_user.isSynthetic is True
    assert "<status>completed</status>" in notification_user.content
    assert "<output_file>.agents/task-output/shell_" in notification_user.content
    assert "Background Bash command &quot;Run SDK notification script&quot; completed" in notification_user.content


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
    assert sessions[0].sessionId == "session-1"
    assert sessions[0].summary == "first meaningful prompt"
    assert sessions[0].first_prompt == "first meaningful prompt"
    assert sessions[0].firstPrompt == "first meaningful prompt"
    assert sessions[0].run_ids == [result.run_id]
    session_payload = sessions[0].model_dump()
    assert session_payload["sessionId"] == "session-1"
    assert session_payload["lastModified"] >= session_payload["createdAt"]
    assert "session_id" not in session_payload
    assert "run_ids" not in session_payload
    assert "metadata" not in session_payload
    assert "latest_run_id" not in session_payload
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
    assert renamed.customTitle == "Pinned title"
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
    result_message_schema = result_schema["properties"]
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
    for definition in message_schema["$defs"].values():
        properties = definition.get("properties", {})
        assert "run_id" not in properties
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
    assert result_message_schema["type"]["const"] == "result"
    assert "result" in result_message_schema
    assert "is_error" in result_message_schema
    assert "duration_api_ms" in result_message_schema
    assert "total_cost_usd" in result_message_schema
    assert "modelUsage" in result_message_schema
    assert "permission_denials" in result_message_schema
    assert "content" not in result_message_schema
    assert "status" not in result_message_schema
    assert "run_id" not in result_message_schema
    assert "sessionId" in session_schema["properties"]
    assert "lastModified" in session_schema["properties"]
    assert "customTitle" in session_schema["properties"]
    assert "firstPrompt" in session_schema["properties"]
    assert "createdAt" in session_schema["properties"]
    assert "session_id" not in session_schema["properties"]
    assert "last_modified" not in session_schema["properties"]
    assert "run_ids" not in session_schema["properties"]
    assert "metadata" not in session_schema["properties"]

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
    assert valid.run_id == "run-1"
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


def test_sdk_exports_control_protocol_schemas_and_validators():
    request_schema = sdk_control_request_json_schema()
    response_schema = sdk_control_response_json_schema()
    stdin_schema = sdk_stdin_message_json_schema()
    stdout_schema = sdk_stdout_message_json_schema()

    assert request_schema["properties"]["type"]["const"] == "control_request"
    assert response_schema["properties"]["type"]["const"] == "control_response"
    assert "SDKControlPermissionRequest" in request_schema["$defs"]
    assert "SDKControlInitializeRequest" in request_schema["$defs"]
    assert "SDKControlMcpSetServersRequest" in request_schema["$defs"]
    assert "SDKControlCancelRequest" in stdout_schema["$defs"]
    assert "SDKUpdateEnvironmentVariablesMessage" in stdin_schema["$defs"]

    permission = validate_sdk_control_request(
        {
            "type": "control_request",
            "request_id": "perm-1",
            "request": {
                "subtype": "can_use_tool",
                "tool_name": "Read",
                "input": {"file_path": "README.md"},
                "tool_use_id": "toolu_1",
                "decision_reason": "path requires approval",
            },
        }
    )
    assert isinstance(permission, SDKControlRequest)
    assert isinstance(permission.request, SDKControlPermissionRequest)
    assert permission.request.tool_name == "Read"
    assert permission.request.tool_use_id == "toolu_1"

    initialize = SDKControlRequest(
        request_id="init-1",
        request=SDKControlInitializeRequest(
            sdkMcpServers=["docs"],
            systemPrompt="Be concise.",
            promptSuggestions=True,
        ),
    )
    assert validate_sdk_stdout_message(initialize.model_dump()) == initialize

    response = validate_sdk_control_response(
        {
            "type": "control_response",
            "response": {
                "subtype": "success",
                "request_id": "init-1",
                "response": {"output_style": "default"},
            },
        }
    )
    assert isinstance(response, SDKControlResponse)
    assert isinstance(response.response, SDKControlSuccessResponse)
    assert response.response.response == {"output_style": "default"}

    keep_alive = validate_sdk_stdout_message({"type": "keep_alive"})
    env_update = validate_sdk_stdin_message(
        {"type": "update_environment_variables", "variables": {"NEXUS_ENV": "test"}}
    )
    assert isinstance(keep_alive, SDKKeepAliveMessage)
    assert isinstance(env_update, SDKUpdateEnvironmentVariablesMessage)

    with pytest.raises(ValidationError):
        validate_sdk_control_request(
            {
                "type": "control_request",
                "request_id": "bad-1",
                "request": {"subtype": "can_use_tool", "tool_name": "Read"},
                "unexpected": True,
            }
        )


def test_sdk_control_validators_accept_camel_case_request_ids():
    request = validate_sdk_control_request(
        {
            "type": "control_request",
            "requestId": "camel-request",
            "request": {"subtype": "set_model", "model": "claude-sonnet"},
        }
    )
    response = validate_sdk_stdin_message(
        {
            "type": "control_response",
            "response": {
                "subtype": "success",
                "requestId": "camel-response",
                "response": {"ok": True},
            },
        }
    )

    assert request.request_id == "camel-request"
    assert isinstance(response, SDKControlResponse)
    assert response.response.request_id == "camel-response"
    assert normalize_sdk_control_message_keys({"requestId": "legacy"}) == {"request_id": "legacy"}


def test_sdk_structured_io_parses_and_encodes_jsonl_frames():
    async def source():
        yield b'{"type":"keep_alive"}\n'
        yield '{"type":"control_request","requestId":"jsonl-request",'
        yield '"request":{"subtype":"set_model","model":"claude-sonnet"}}\n\n'
        yield '{"type":"update_environment_variables","variables":{"NEXUS_JSONL":"yes"}}'

    messages = asyncio.run(_collect(iter_stdin_jsonl(source())))
    encoded = encode_stdout_message(
        SDKControlRequest(
            request_id="jsonl-out",
            request=SDKControlSetModelRequest(model="line\u2028separator\u2029test"),
        )
    )

    assert isinstance(messages[0], SDKKeepAliveMessage)
    assert isinstance(messages[1], SDKControlRequest)
    assert messages[1].request_id == "jsonl-request"
    assert isinstance(messages[2], SDKUpdateEnvironmentVariablesMessage)
    assert "\\u2028" in encoded
    assert "\\u2029" in encoded
    assert "\u2028" not in encoded
    assert "\u2029" not in encoded
    assert encoded.endswith("\n")
    assert json.loads(encoded)["request"]["model"] == "line\u2028separator\u2029test"
    assert ndjson_safe_dumps({"text": "a\u2028b\u2029c"}) == '{"text":"a\\u2028b\\u2029c"}'


def test_sdk_structured_io_reports_invalid_jsonl_frames():
    async def execute():
        return [message async for message in iter_stdin_jsonl(['{"type":"keep_alive"}\n', "{bad}\n"])]

    with pytest.raises(SDKStdinDecodeError):
        asyncio.run(execute())


def test_sdk_structured_io_tracks_pending_control_requests():
    async def execute():
        structured_io = SDKStructuredIO()
        sent: list[str] = []
        resolved: list[str] = []
        structured_io.set_on_control_request_sent(lambda request: sent.append(request.request_id))
        structured_io.set_on_control_request_resolved(lambda request_id: resolved.append(request_id))

        request_task = asyncio.create_task(
            structured_io.send_request(
                SDKControlPermissionRequest(
                    tool_name="Read",
                    input={"file_path": "README.md"},
                    tool_use_id="toolu_structured",
                ),
                response_validator=lambda payload: payload["behavior"],
                request_id="permission-structured",
            )
        )
        outbound = await structured_io.next_stdout_message()
        pending = structured_io.get_pending_permission_requests()
        replay = await structured_io.receive(
            {
                "type": "control_response",
                "response": {
                    "subtype": "success",
                    "request_id": "permission-structured",
                    "response": {"behavior": "allow", "toolUseID": "toolu_structured"},
                },
            }
        )
        result = await request_task
        duplicate = await structured_io.receive(
            {
                "type": "control_response",
                "response": {
                    "subtype": "success",
                    "request_id": "permission-structured",
                    "response": {"behavior": "allow", "toolUseID": "toolu_structured"},
                },
            }
        )
        return outbound, pending, replay, result, duplicate, structured_io.pending_count, sent, resolved

    outbound, pending, replay, result, duplicate, pending_count, sent, resolved = asyncio.run(execute())

    assert isinstance(outbound, SDKControlRequest)
    assert outbound.request_id == "permission-structured"
    assert isinstance(outbound.request, SDKControlPermissionRequest)
    assert pending == [outbound]
    assert replay is None
    assert result == "allow"
    assert duplicate is None
    assert pending_count == 0
    assert sent == ["permission-structured"]
    assert resolved == ["permission-structured"]


def test_sdk_structured_io_cancels_and_closes_pending_requests():
    async def execute_cancel():
        structured_io = SDKStructuredIO()
        request_task = asyncio.create_task(
            structured_io.send_request(
                SDKControlSetModelRequest(model="claude-sonnet"),
                request_id="cancel-structured",
            )
        )
        outbound = await structured_io.next_stdout_message()
        await structured_io.cancel_request("cancel-structured")
        cancel = await structured_io.next_stdout_message()
        with pytest.raises(SDKControlRequestCancelledError):
            await request_task
        return outbound, cancel

    async def execute_close():
        structured_io = SDKStructuredIO()
        request_task = asyncio.create_task(
            structured_io.send_request(
                SDKControlSetModelRequest(model="claude-opus"),
                request_id="close-structured",
            )
        )
        outbound = await structured_io.next_stdout_message()
        structured_io.close()
        closed = await structured_io.next_stdout_message()
        with pytest.raises(SDKControlStreamClosedError):
            await request_task
        return outbound, closed

    outbound, cancel = asyncio.run(execute_cancel())
    close_outbound, closed = asyncio.run(execute_close())

    assert isinstance(outbound, SDKControlRequest)
    assert isinstance(cancel, SDKControlCancelRequest)
    assert cancel.request_id == "cancel-structured"
    assert isinstance(close_outbound, SDKControlRequest)
    assert closed is None


def test_sdk_control_request_handler_answers_initialize_and_permissions():
    initialize = asyncio.run(
        handle_control_request(
            SDKControlRequest(
                request_id="init-handler",
                request=SDKControlInitializeRequest(
                    agents={"reviewer": {"description": "Review code", "model": "claude-sonnet"}},
                ),
            ),
            SDKOptions(
                model="claude-sonnet",
                permission_mode="acceptEdits",
                metadata={"apiKeySource": "oauth", "output_style": "concise", "fast_mode_state": "off"},
            ),
        )
    )

    assert isinstance(initialize.response, SDKControlSuccessResponse)
    assert validate_sdk_control_response(initialize.model_dump()) == initialize
    init_payload = initialize.response.response
    assert init_payload["output_style"] == "concise"
    assert init_payload["fast_mode_state"] == "off"
    assert init_payload["account"] == {"apiKeySource": "oauth"}
    assert init_payload["models"] == [
        {"value": "claude-sonnet", "displayName": "claude-sonnet", "description": "Configured SDK model"}
    ]
    assert init_payload["agents"] == [
        {"name": "reviewer", "description": "Review code", "model": "claude-sonnet"}
    ]
    assert any(command["name"] == "help" for command in init_payload["commands"])

    permission = asyncio.run(
        handle_control_request(
            {
                "type": "control_request",
                "request_id": "perm-handler",
                "request": {
                    "subtype": "can_use_tool",
                    "tool_name": "Read",
                    "input": {"file_path": "README.md"},
                    "tool_use_id": "toolu_handler",
                },
            },
            {"permission_mode": "deny"},
        )
    )

    assert isinstance(permission.response, SDKControlSuccessResponse)
    assert permission.response.response["behavior"] == "deny"
    assert permission.response.response["allowed"] is False
    assert permission.response.response["requires_approval"] is False
    assert "tool execution disabled" in permission.response.response["reason"]


def test_sdk_control_request_handler_applies_session_options_and_mcp_state():
    client = AgentSDKClient(session_factory=_session_factory)
    session = client.create_sdk_session(
        SDKOptions(
            session_id="control-session",
            tenant_id="tenant",
            user_id="user",
            agent_id="agent",
        )
    )

    set_model = asyncio.run(
        session.handle_control_request(
            SDKControlRequest(
                request_id="set-model",
                request=SDKControlSetModelRequest(model="claude-sonnet"),
            )
        )
    )
    set_permission = asyncio.run(
        session.handle_control_request(
            SDKControlRequest(
                request_id="set-permission",
                request=SDKControlSetPermissionModeRequest(mode="acceptEdits", ultraplan=True),
            )
        )
    )
    apply_settings = asyncio.run(
        session.handle_control_request(
            SDKControlRequest(
                request_id="apply-settings",
                request=SDKControlApplyFlagSettingsRequest(
                    settings={
                        "model": "claude-opus",
                        "permissionMode": "dontAsk",
                        "systemPrompt": "Be precise.",
                    }
                ),
            )
        )
    )
    settings = asyncio.run(
        session.handle_control_request(
            SDKControlRequest(request_id="settings", request=SDKControlGetSettingsRequest())
        )
    )

    assert set_model.response.response == {"model": "claude-sonnet"}
    assert set_permission.response.response == {"mode": "acceptEdits", "ultraplan": True}
    assert apply_settings.response.response["effective"]["model"] == "claude-opus"
    assert session.options.model == "claude-opus"
    assert session.options.permission_mode == "dontAsk"
    assert session.options.system_prompt == "Be precise."
    assert settings.response.response["effective"]["model"] == "claude-opus"
    assert settings.response.response["effective"]["permissionMode"] == "dontAsk"
    assert settings.response.response["effective"]["systemPrompt"] == "Be precise."

    mcp_set = asyncio.run(
        session.handle_control_request(
            SDKControlRequest(
                request_id="mcp-set",
                request=SDKControlMcpSetServersRequest(
                    servers={"docs": {"type": "stdio", "command": "docs-mcp", "args": ["--serve"]}}
                ),
            )
        )
    )
    mcp_status = asyncio.run(
        session.handle_control_request(
            SDKControlRequest(request_id="mcp-status", request=SDKControlMcpStatusRequest())
        )
    )
    mcp_reconnect = asyncio.run(
        session.handle_control_request(
            SDKControlRequest(
                request_id="mcp-reconnect",
                request=SDKControlMcpReconnectRequest(serverName="docs"),
            )
        )
    )
    mcp_toggle = asyncio.run(
        session.handle_control_request(
            SDKControlRequest(
                request_id="mcp-toggle",
                request=SDKControlMcpToggleRequest(serverName="docs", enabled=False),
            )
        )
    )
    mcp_status_after_toggle = asyncio.run(
        session.handle_control_request(
            SDKControlRequest(request_id="mcp-status-disabled", request=SDKControlMcpStatusRequest())
        )
    )

    assert mcp_set.response.response == {"added": ["docs"], "removed": [], "errors": {}}
    assert {"name": "docs", "status": "connected"} in mcp_status.response.response["mcpServers"]
    assert mcp_reconnect.response.response == {
        "serverName": "docs",
        "status": "connected",
        "reconnected": False,
        "reason": "no active SDK turn is attached to this control handler",
    }
    assert mcp_toggle.response.response == {"serverName": "docs", "enabled": False}
    assert {"name": "docs", "status": "disabled"} in mcp_status_after_toggle.response.response["mcpServers"]


def test_sdk_control_mcp_reconnect_reloads_active_session_handlers(monkeypatch, tmp_path):
    workspace = WorkspaceContext(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
        root=tmp_path,
        path=tmp_path,
    )
    policy = SandboxPolicy.for_workspace(workspace.path)
    store = InMemoryMCPConfigStore()
    old_client = _AnsweringMCPClient("old")
    new_clients = []

    class FakeStdioMCPClient(_AnsweringMCPClient):
        def __init__(self, server):
            super().__init__("new", server=server)
            new_clients.append(self)

    async def execute():
        await store.save(
            MCPServerRecord(
                name="docs",
                command="python docs.py",
                tenant_id="tenant",
                user_id="user",
                agent_id="agent",
                workspace_id="workspace",
            )
        )
        monkeypatch.setattr("agents.kernel.capabilities.mcp_loading.MCPStdioClient", FakeStdioMCPClient)
        context = ToolRuntimeContext(
            workspace=workspace,
            sandbox=policy,
            sandbox_client=LocalSandboxProvider().acquire(workspace, policy),
            settings=SimpleNamespace(mcp=SimpleNamespace(CLIENT_TIMEOUT=30.0, SSE_READ_TIMEOUT=120.0)),
            mcp_config_store=store,
        )
        registry = ToolRegistry()
        register_builtin_tools(registry, context)
        old_provider = MCPToolProvider(client=old_client, server=MCPServerConfig(name="docs"))
        await old_provider.load_tools(registry)
        context.mcp_providers = [old_provider]
        runtime = AgentRuntime(
            model_client=ScriptedModelClient([]),
            tools=registry,
            protocol="scripted",
            model="scripted",
            enabled_tools=["mcp__docs__search"],
        )
        agent_session = AgentSession(runtime, system_prompt="", workspace=workspace, tool_context=context)
        client = AgentSDKClient(session_factory=_session_factory)
        client.active_turn_sessions["sdk-session"] = agent_session
        before = await registry.execute("mcp__docs__search", {"query": "before"})
        response = await client.handle_control_request(
            SDKControlRequest(
                request_id="mcp-reconnect-active",
                request=SDKControlMcpReconnectRequest(serverName="docs"),
            ),
            SDKOptions(session_id="sdk-session"),
        )
        after = await registry.execute("mcp__docs__search", {"query": "after"})
        return before, response, after, runtime

    before, response, after, runtime = asyncio.run(execute())

    assert json.loads(before.content)["answer"] == "old:before"
    assert json.loads(after.content)["answer"] == "new:after"
    assert old_client.closed is True
    assert new_clients and new_clients[0].called == [("search", {"query": "after"})]
    assert response.response.response == {
        "serverName": "docs",
        "status": "connected",
        "reconnected": True,
        "loadedTools": ["mcp__docs__search"],
        "removedTools": ["mcp__docs__search", "mcp_docs_search"],
    }
    assert runtime.config.enabled_tools == ["mcp__docs__search"]


def test_sdk_control_request_handler_routes_sdk_mcp_messages():
    client = AgentSDKClient(session_factory=_session_factory)

    async def sdk_mcp_handler(message):
        return {
            "jsonrpc": "2.0",
            "id": message["id"],
            "result": {"echoed_method": message["method"]},
        }

    client.register_sdk_mcp_server("sdk-tools", sdk_mcp_handler)
    session = client.create_sdk_session(
        SDKOptions(
            session_id="control-mcp-session",
            tenant_id="tenant",
            user_id="user",
            agent_id="agent",
        )
    )

    status = asyncio.run(
        session.handle_control_request(
            SDKControlRequest(request_id="mcp-status", request=SDKControlMcpStatusRequest())
        )
    )
    message = asyncio.run(
        session.handle_control_request(
            SDKControlRequest(
                request_id="mcp-message",
                request=SDKControlMcpMessageRequest(
                    server_name="sdk-tools",
                    message={"jsonrpc": "2.0", "id": 7, "method": "tools/list"},
                ),
            )
        )
    )
    disabled = asyncio.run(
        session.handle_control_request(
            SDKControlRequest(
                request_id="disable-sdk-mcp",
                request=SDKControlMcpToggleRequest(serverName="sdk-tools", enabled=False),
            )
        )
    )
    disabled_status = asyncio.run(
        session.handle_control_request(
            SDKControlRequest(request_id="mcp-status-disabled", request=SDKControlMcpStatusRequest())
        )
    )
    blocked = asyncio.run(
        session.handle_control_request(
            SDKControlRequest(
                request_id="mcp-message-disabled",
                request=SDKControlMcpMessageRequest(
                    server_name="sdk-tools",
                    message={"jsonrpc": "2.0", "id": 8, "method": "tools/list"},
                ),
            )
        )
    )

    assert {"name": "sdk-tools", "status": "connected"} in status.response.response["mcpServers"]
    assert message.response.response == {
        "mcp_response": {"jsonrpc": "2.0", "id": 7, "result": {"echoed_method": "tools/list"}}
    }
    assert disabled.response.response == {"serverName": "sdk-tools", "enabled": False}
    assert {"name": "sdk-tools", "status": "disabled"} in disabled_status.response.response["mcpServers"]
    assert isinstance(blocked.response, SDKControlErrorResponse)
    assert "disabled" in blocked.response.error


def test_sdk_control_request_handler_routes_hook_callbacks_and_elicitations():
    client = AgentSDKClient(session_factory=_session_factory)

    async def hook_handler(request):
        return {
            "decision": "approve",
            "hookEventName": request.input["hookEventName"],
            "toolUseID": request.tool_use_id,
        }

    def elicitation_handler(request):
        assert request.mode == "form"
        return {"action": "accept", "content": {"channel": "#ops", "server": request.mcp_server_name}}

    client.register_hook_callback("hook-1", hook_handler)
    client.set_elicitation_handler(elicitation_handler)

    hook = asyncio.run(
        client.handle_control_request(
            SDKControlRequest(
                request_id="hook-callback",
                request=SDKHookCallbackRequest(
                    callback_id="hook-1",
                    input={"hookEventName": "PreToolUse"},
                    tool_use_id="toolu_hook",
                ),
            )
        )
    )
    missing_hook = asyncio.run(
        client.handle_control_request(
            SDKControlRequest(
                request_id="missing-hook-callback",
                request=SDKHookCallbackRequest(callback_id="missing", input={"hookEventName": "PreToolUse"}),
            )
        )
    )
    elicitation = asyncio.run(
        client.handle_control_request(
            SDKControlRequest(
                request_id="elicitation",
                request=SDKControlElicitationRequest(
                    mcp_server_name="slack",
                    message="Choose a channel",
                    mode="form",
                    requested_schema={"type": "object"},
                ),
            )
        )
    )
    client.set_elicitation_handler(None)
    default_elicitation = asyncio.run(
        client.handle_control_request(
            SDKControlRequest(
                request_id="default-elicitation",
                request=SDKControlElicitationRequest(mcp_server_name="docs", message="Need input"),
            )
        )
    )

    assert hook.response.response == {
        "decision": "approve",
        "hookEventName": "PreToolUse",
        "toolUseID": "toolu_hook",
    }
    assert missing_hook.response.response == {}
    assert elicitation.response.response == {
        "action": "accept",
        "content": {"channel": "#ops", "server": "slack"},
    }
    assert default_elicitation.response.response == {"action": "cancel"}


def test_sdk_control_request_interrupt_cancels_active_session_query():
    async def execute():
        started = asyncio.Event()

        async def interruptible_session_factory(settings, spec):
            interrupt_workspace = WorkspaceContext(
                tenant_id="tenant",
                user_id="user",
                agent_id="agent",
                workspace_id="workspace",
                root=".",
                path=".",
            )

            class InterruptibleSession:
                runtime = SimpleNamespace(model="scripted", protocol="scripted", enabled_tools=[])
                workspace = interrupt_workspace

                async def stream(self, text, run_id=None):
                    started.set()
                    await asyncio.sleep(60)
                    yield RuntimeEvent(type="done", name="assistant", payload={"content": "late", "status": "finished"})

            return InterruptibleSession()

        client = AgentSDKClient(session_factory=interruptible_session_factory)
        session = client.create_sdk_session(
            SDKOptions(
                session_id="interrupt-session",
                tenant_id="tenant",
                user_id="user",
                agent_id="agent",
            )
        )

        async def collect():
            return [message async for message in session.query("wait")]

        collector = asyncio.create_task(collect())
        await started.wait()
        response = await session.handle_control_request(
            SDKControlRequest(request_id="interrupt", request=SDKControlInterruptRequest())
        )
        messages = await collector
        replay = await session.messages()
        return response, messages, replay

    response, messages, replay = asyncio.run(execute())
    result = next(message for message in messages if isinstance(message, SDKResultMessage))
    states = [message.state for message in messages if isinstance(message, SDKSessionStateChangedMessage)]

    assert response.response.response["interrupted"] is True
    assert response.response.response["run_id"]
    assert result.is_error is False
    assert result.result == "run canceled"
    assert result.stop_reason == "canceled"
    assert states == ["running", "idle"]
    assert any(isinstance(message, SDKResultMessage) and message.stop_reason == "canceled" for message in replay)


def test_sdk_control_request_rewinds_files_from_run_store(tmp_path):
    async def execute():
        notes = tmp_path / "notes.txt"
        created = tmp_path / "created.txt"
        write_note = tmp_path / "write.txt"
        notebook = tmp_path / "analysis.ipynb"
        notes.write_text("old\n", encoding="utf-8")
        write_note.write_text("old write\n", encoding="utf-8")
        client = AgentSDKClient(session_factory=_rewind_patch_session_factory)
        session = client.create_sdk_session(
            SDKOptions(
                session_id="rewind-session",
                tenant_id="tenant",
                user_id="user",
                agent_id="agent",
                cwd=str(tmp_path),
                metadata={"file_history_enabled": False},
            )
        )
        await _collect(session.query("edit files"))
        replay = await session.messages({"include_system_messages": False})
        user_message = next(message for message in replay if isinstance(message, SDKUserMessage))
        dry_run = await session.handle_control_request(
            SDKControlRequest(
                request_id="rewind-dry-run",
                request=SDKControlRewindFilesRequest(user_message_id=user_message.uuid, dry_run=True),
            )
        )
        actual = await session.handle_control_request(
            SDKControlRequest(
                request_id="rewind",
                request=SDKControlRewindFilesRequest(user_message_id=user_message.uuid),
            )
        )
        return (
            dry_run,
            actual,
            notes.read_text(encoding="utf-8"),
            write_note.read_text(encoding="utf-8"),
            notebook.read_text(encoding="utf-8"),
            created.exists(),
        )

    dry_run, actual, notes_content, write_content, notebook_content, created_exists = asyncio.run(execute())

    assert isinstance(dry_run.response, SDKControlSuccessResponse)
    assert dry_run.response.response == {
        "canRewind": True,
        "filesChanged": ["analysis.ipynb", "created.txt", "notes.txt", "write.txt"],
        "insertions": 3,
        "deletions": 2,
    }
    assert actual.response.response == {"canRewind": True}
    assert notes_content == "old\n"
    assert write_content == "old write\n"
    expected_notebook = json.dumps({"cells": [{"cell_type": "code", "source": "print(1)\n"}]})
    assert notebook_content == expected_notebook
    assert created_exists is False


def test_sdk_records_file_history_snapshots_for_rewind(tmp_path):
    async def execute():
        config_dir = tmp_path / "claude-config"
        notes = tmp_path / "notes.txt"
        created = tmp_path / "created.txt"
        write_note = tmp_path / "write.txt"
        notes.write_text("old\n", encoding="utf-8")
        write_note.write_text("old write\n", encoding="utf-8")
        client = AgentSDKClient(session_factory=_rewind_patch_session_factory)
        session = client.create_sdk_session(
            SDKOptions(
                session_id="auto-history-session",
                tenant_id="tenant",
                user_id="user",
                agent_id="agent",
                cwd=str(tmp_path),
                metadata={"claude_config_dir": str(config_dir)},
            )
        )
        await _collect(session.query("edit files"))
        records = await client._runs_for_session("auto-history-session")
        snapshots = [
            event.payload
            for record in records
            for event in record.events
            if event.type == "file-history-snapshot"
        ]
        replay = await session.messages({"include_system_messages": False})
        user_message = next(message for message in replay if isinstance(message, SDKUserMessage))
        dry_run = await session.handle_control_request(
            SDKControlRequest(
                request_id="rewind-auto-file-history-dry-run",
                request=SDKControlRewindFilesRequest(user_message_id=user_message.uuid, dry_run=True),
            )
        )
        actual = await session.handle_control_request(
            SDKControlRequest(
                request_id="rewind-auto-file-history",
                request=SDKControlRewindFilesRequest(user_message_id=user_message.uuid),
            )
        )
        return (
            snapshots,
            dry_run,
            actual,
            notes.read_text(encoding="utf-8"),
            write_note.read_text(encoding="utf-8"),
            created.exists(),
        )

    snapshots, dry_run, actual, notes_content, write_content, created_exists = asyncio.run(execute())

    assert len(snapshots) == 5
    assert snapshots[0]["isSnapshotUpdate"] is False
    assert all(snapshot["isSnapshotUpdate"] is True for snapshot in snapshots[1:])
    message_ids = {snapshot["messageId"] for snapshot in snapshots}
    assert len(message_ids) == 1
    final_snapshot = snapshots[-1]
    backup_root = Path(final_snapshot["backupRoot"])
    assert backup_root == tmp_path / "claude-config" / "file-history" / "auto-history-session"
    backups = final_snapshot["snapshot"]["trackedFileBackups"]
    assert sorted(backups) == ["analysis.ipynb", "created.txt", "notes.txt", "write.txt"]
    notebook_backup = backup_root / backups["analysis.ipynb"]["backupFileName"]
    assert backups["created.txt"]["backupFileName"] is None
    assert backups["created.txt"]["version"] == 1
    note_backup = backup_root / backups["notes.txt"]["backupFileName"]
    write_backup = backup_root / backups["write.txt"]["backupFileName"]
    assert notebook_backup.name.endswith("@v1")
    assert note_backup.name.endswith("@v1")
    assert write_backup.name.endswith("@v1")
    expected_notebook = json.dumps({"cells": [{"cell_type": "code", "source": "print(1)\n"}]})
    assert notebook_backup.read_text(encoding="utf-8") == expected_notebook
    assert note_backup.read_text(encoding="utf-8") == "old\n"
    assert write_backup.read_text(encoding="utf-8") == "old write\n"
    assert isinstance(dry_run.response, SDKControlSuccessResponse)
    assert dry_run.response.response == {
        "canRewind": True,
        "filesChanged": ["analysis.ipynb", "created.txt", "notes.txt", "write.txt"],
        "insertions": 3,
        "deletions": 4,
    }
    assert actual.response.response == {"canRewind": True}
    assert notes_content == "old\n"
    assert write_content == "old write\n"
    assert created_exists is False


def test_sdk_fork_session_migrates_file_history_backups_for_rewind(tmp_path):
    async def execute():
        config_dir = tmp_path / "claude-config"
        notes = tmp_path / "notes.txt"
        created = tmp_path / "created.txt"
        write_note = tmp_path / "write.txt"
        notes.write_text("old\n", encoding="utf-8")
        write_note.write_text("old write\n", encoding="utf-8")
        client = AgentSDKClient(session_factory=_rewind_patch_session_factory)
        source = client.create_sdk_session(
            SDKOptions(
                session_id="fork-history-source",
                tenant_id="tenant",
                user_id="user",
                agent_id="agent",
                cwd=str(tmp_path),
                metadata={"claude_config_dir": str(config_dir)},
            )
        )
        await _collect(source.query("edit files"))
        fork = await client.fork_session("fork-history-source", SDKForkSessionOptions(title="Fork history"))
        forked = await client.resume_session(fork.session_id)
        records = await client._runs_for_session(fork.session_id)
        snapshots = [
            event.payload
            for record in records
            for event in record.events
            if event.type == "file-history-snapshot"
        ]
        backup_root = config_dir / "file-history" / fork.session_id
        shutil.rmtree(config_dir / "file-history" / "fork-history-source")
        replay = await forked.messages({"include_system_messages": False})
        user_message = next(message for message in replay if isinstance(message, SDKUserMessage))
        actual = await forked.handle_control_request(
            SDKControlRequest(
                request_id="rewind-fork-file-history",
                request=SDKControlRewindFilesRequest(user_message_id=user_message.uuid),
            )
        )
        return (
            fork,
            snapshots,
            backup_root,
            actual,
            notes.read_text(encoding="utf-8"),
            write_note.read_text(encoding="utf-8"),
            created.exists(),
        )

    fork, snapshots, backup_root, actual, notes_content, write_content, created_exists = asyncio.run(execute())

    assert fork.session_id != "fork-history-source"
    assert backup_root.exists()
    assert snapshots
    assert {snapshot["sessionId"] for snapshot in snapshots} == {fork.session_id}
    assert {Path(snapshot["backupRoot"]) for snapshot in snapshots} == {backup_root}
    final_backups = snapshots[-1]["snapshot"]["trackedFileBackups"]
    assert (backup_root / final_backups["notes.txt"]["backupFileName"]).read_text(encoding="utf-8") == "old\n"
    assert (backup_root / final_backups["write.txt"]["backupFileName"]).read_text(encoding="utf-8") == "old write\n"
    assert actual.response.response == {"canRewind": True}
    assert notes_content == "old\n"
    assert write_content == "old write\n"
    assert created_exists is False


def test_sdk_rewind_file_history_snapshot_seeds_previous_tracked_files(tmp_path):
    async def execute():
        config_dir = tmp_path / "claude-config"
        note = tmp_path / "turn-note.txt"
        note.write_text("v0\n", encoding="utf-8")
        client = AgentSDKClient(session_factory=_rewind_multi_turn_session_factory)
        session = client.create_sdk_session(
            SDKOptions(
                session_id="multi-turn-history-session",
                tenant_id="tenant",
                user_id="user",
                agent_id="agent",
                cwd=str(tmp_path),
                metadata={"claude_config_dir": str(config_dir)},
            )
        )
        await _collect(session.query("first edit"))
        await _collect(session.query("no edits"))
        await _collect(session.query("second edit"))
        records = await client._runs_for_session("multi-turn-history-session")
        replay = await session.messages({"include_system_messages": False})
        user_messages = [message for message in replay if isinstance(message, SDKUserMessage)]
        no_edit_message_id = user_messages[1].uuid
        snapshots = [
            event.payload
            for record in records
            for event in record.events
            if event.type == "file-history-snapshot" and event.payload["messageId"] == no_edit_message_id
        ]
        dry_run = await session.handle_control_request(
            SDKControlRequest(
                request_id="rewind-no-edit-file-history-dry-run",
                request=SDKControlRewindFilesRequest(user_message_id=no_edit_message_id, dry_run=True),
            )
        )
        actual = await session.handle_control_request(
            SDKControlRequest(
                request_id="rewind-no-edit-file-history",
                request=SDKControlRewindFilesRequest(user_message_id=no_edit_message_id),
            )
        )
        return snapshots, dry_run, actual, note.read_text(encoding="utf-8")

    snapshots, dry_run, actual, note_content = asyncio.run(execute())

    assert len(snapshots) == 1
    backups = snapshots[0]["snapshot"]["trackedFileBackups"]
    assert backups["turn-note.txt"]["version"] == 2
    assert backups["turn-note.txt"]["backupFileName"].endswith("@v2")
    assert isinstance(dry_run.response, SDKControlSuccessResponse)
    assert dry_run.response.response == {
        "canRewind": True,
        "filesChanged": ["turn-note.txt"],
        "insertions": 1,
        "deletions": 1,
    }
    assert actual.response.response == {"canRewind": True}
    assert note_content == "v1\n"


def test_sdk_control_request_rewinds_src_origin_wrapped_write_results(tmp_path):
    async def execute():
        note = tmp_path / "origin-write.txt"
        created = tmp_path / "origin-created.txt"
        note.write_text("before\n", encoding="utf-8")
        client = AgentSDKClient(session_factory=_src_origin_write_rewind_session_factory)
        session = client.create_sdk_session(
            SDKOptions(
                session_id="src-origin-write-rewind-session",
                tenant_id="tenant",
                user_id="user",
                agent_id="agent",
                cwd=str(tmp_path),
                metadata={"file_history_enabled": False},
            )
        )
        await _collect(session.query("write files"))
        replay = await session.messages({"include_system_messages": False})
        user_message = next(message for message in replay if isinstance(message, SDKUserMessage))
        dry_run = await session.handle_control_request(
            SDKControlRequest(
                request_id="rewind-src-origin-write-dry-run",
                request=SDKControlRewindFilesRequest(user_message_id=user_message.uuid, dry_run=True),
            )
        )
        actual = await session.handle_control_request(
            SDKControlRequest(
                request_id="rewind-src-origin-write",
                request=SDKControlRewindFilesRequest(user_message_id=user_message.uuid),
            )
        )
        return dry_run, actual, note.read_text(encoding="utf-8"), created.exists()

    dry_run, actual, note_content, created_exists = asyncio.run(execute())

    assert isinstance(dry_run.response, SDKControlSuccessResponse)
    assert dry_run.response.response == {
        "canRewind": True,
        "filesChanged": ["origin-created.txt", "origin-write.txt"],
        "insertions": 3,
        "deletions": 1,
    }
    assert actual.response.response == {"canRewind": True}
    assert note_content == "before\n"
    assert created_exists is False


def test_sdk_control_request_rewinds_file_history_snapshot_chain(tmp_path):
    async def execute():
        config_dir = tmp_path / "claude-config"
        backup_dir = config_dir / "file-history" / "snapshot-session"
        backup_dir.mkdir(parents=True)
        (backup_dir / "snapshot-note@v1").write_text("before\n", encoding="utf-8")
        note = tmp_path / "snapshot-note.txt"
        created = tmp_path / "snapshot-created.txt"
        note.write_text("before\n", encoding="utf-8")
        client = AgentSDKClient(session_factory=_file_history_snapshot_rewind_session_factory)
        session = client.create_sdk_session(
            SDKOptions(
                session_id="snapshot-session",
                tenant_id="tenant",
                user_id="user",
                agent_id="agent",
                cwd=str(tmp_path),
                metadata={"claude_config_dir": str(config_dir), "file_history_enabled": False},
            )
        )
        user_message = {
            "type": "user",
            "session_id": "snapshot-session",
            "uuid": "msg-snapshot-rewind",
            "message": {"role": "user", "content": [{"type": "text", "text": "edit from snapshot"}]},
        }
        await _collect(client.query_user_message(user_message, session.options))
        dry_run = await session.handle_control_request(
            SDKControlRequest(
                request_id="rewind-file-history-snapshot-dry-run",
                request=SDKControlRewindFilesRequest(user_message_id="msg-snapshot-rewind", dry_run=True),
            )
        )
        actual = await session.handle_control_request(
            SDKControlRequest(
                request_id="rewind-file-history-snapshot",
                request=SDKControlRewindFilesRequest(user_message_id="msg-snapshot-rewind"),
            )
        )
        return dry_run, actual, note.read_text(encoding="utf-8"), created.exists()

    dry_run, actual, note_content, created_exists = asyncio.run(execute())

    assert isinstance(dry_run.response, SDKControlSuccessResponse)
    assert dry_run.response.response == {
        "canRewind": True,
        "filesChanged": ["snapshot-created.txt", "snapshot-note.txt"],
        "insertions": 1,
        "deletions": 3,
    }
    assert actual.response.response == {"canRewind": True}
    assert note_content == "before\n"
    assert created_exists is False


def test_sdk_control_request_rewinds_non_sdk_file_history_session(tmp_path):
    async def execute():
        config_dir = tmp_path / "claude-config"
        note = tmp_path / "non-sdk-note.txt"
        note.write_text("v0\n", encoding="utf-8")
        client = AgentSDKClient()
        service = client.run_service

        def spec_for(message_id: str) -> AgentSpec:
            return replace(
                AgentSpec.from_overrides(agent_id="agent-1", workspace_path=str(tmp_path)),
                metadata={
                    "claude_config_dir": str(config_dir),
                    "file_history_session_id": "non-sdk-history-session",
                    "file_history_message_id": message_id,
                },
            )

        first = await service.start(spec_for("msg-non-sdk-1"))
        await service.record_event(
            first.run_id,
            RuntimeEvent(
                type="tool_result",
                name="Write",
                payload={
                    "tool_call_id": "call-1",
                    "raw": {"filePath": "non-sdk-note.txt", "type": "update", "originalFile": "v0\n"},
                },
            ),
        )
        note.write_text("v1\n", encoding="utf-8")
        second = await service.start(spec_for("msg-non-sdk-2"))
        await service.record_event(
            second.run_id,
            RuntimeEvent(
                type="tool_result",
                name="Write",
                payload={
                    "tool_call_id": "call-2",
                    "raw": {
                        "filePath": "non-sdk-note.txt",
                        "type": "update",
                        "originalFile": "v1\n",
                        "content": "v2\n",
                    },
                },
            ),
        )
        note.write_text("v2\n", encoding="utf-8")
        options = SDKOptions(
            session_id="non-sdk-history-session",
            cwd=str(tmp_path),
            metadata={"claude_config_dir": str(config_dir)},
        )
        dry_run = await client.handle_control_request(
            SDKControlRequest(
                request_id="rewind-non-sdk-file-history-dry-run",
                request=SDKControlRewindFilesRequest(user_message_id="msg-non-sdk-2", dry_run=True),
            ),
            options,
        )
        actual = await client.handle_control_request(
            SDKControlRequest(
                request_id="rewind-non-sdk-file-history",
                request=SDKControlRewindFilesRequest(user_message_id="msg-non-sdk-2"),
            ),
            options,
        )
        return dry_run, actual, note.read_text(encoding="utf-8")

    dry_run, actual, note_content = asyncio.run(execute())

    assert isinstance(dry_run.response, SDKControlSuccessResponse)
    assert dry_run.response.response == {
        "canRewind": True,
        "filesChanged": ["non-sdk-note.txt"],
        "insertions": 1,
        "deletions": 1,
    }
    assert actual.response.response == {"canRewind": True}
    assert note_content == "v1\n"


def test_sdk_control_request_cancels_pending_async_messages():
    client = AgentSDKClient(session_factory=_session_factory)
    session = client.create_sdk_session(
        SDKOptions(
            session_id="async-message-session",
            tenant_id="tenant",
            user_id="user",
            agent_id="agent",
        )
    )
    later = session.enqueue_async_message("run later", priority="later")
    next_message = session.enqueue_async_message("run next", priority="next")

    response = asyncio.run(
        session.handle_control_request(
            SDKControlRequest(
                request_id="cancel-async",
                request=SDKControlCancelAsyncMessageRequest(message_uuid=later.uuid),
            )
        )
    )
    missing = asyncio.run(
        session.handle_control_request(
            SDKControlRequest(
                request_id="cancel-missing",
                request=SDKControlCancelAsyncMessageRequest(message_uuid=later.uuid),
            )
        )
    )

    assert response.response.response == {"cancelled": True}
    assert missing.response.response == {"cancelled": False}
    assert [message.uuid for message in session.list_async_messages()] == [next_message.uuid]
    assert session.dequeue_async_message().uuid == next_message.uuid
    assert session.dequeue_async_message() is None


def test_sdk_session_drains_queued_async_messages_between_turns():
    async def execute():
        client = AgentSDKClient(session_factory=_echo_prompt_session_factory)
        session = client.create_sdk_session(SDKOptions(session_id="drain-session"))
        later = session.enqueue_async_message("queued later", priority="later")
        next_message = session.enqueue_async_message(
            {
                "type": "user",
                "session_id": "drain-session",
                "uuid": "queued-next",
                "message": {"role": "user", "content": [{"type": "text", "text": "queued next"}]},
                "priority": "next",
                "isReplay": False,
            }
        )
        messages = await _collect(session.query("initial"))
        replay = await session.messages({"include_system_messages": False})
        return messages, replay, session.list_async_messages(), later.uuid, next_message.uuid

    messages, replay, queued, later_uuid, next_uuid = asyncio.run(execute())
    results = [message.result for message in messages if isinstance(message, SDKResultMessage)]
    replay_users = [message for message in replay if isinstance(message, SDKUserMessage)]

    assert results == ["initial", "queued next", "queued later"]
    assert queued == []
    assert [message.content for message in replay_users] == ["initial", "queued next", "queued later"]
    assert [message.uuid for message in replay_users[1:]] == [next_uuid, later_uuid]


def test_sdk_now_priority_async_message_interrupts_and_drains():
    async def execute():
        started = asyncio.Event()
        workspace = WorkspaceContext(
            tenant_id="tenant",
            user_id="user",
            agent_id="agent",
            workspace_id="workspace",
            root=".",
            path=".",
        )

        async def session_factory(settings, spec):
            class InterruptThenEchoSession:
                runtime = SimpleNamespace(model="scripted", protocol="scripted", enabled_tools=[])

                def __init__(self):
                    self.workspace = workspace

                async def stream(self, text, run_id=None):
                    if text == "wait":
                        started.set()
                        await asyncio.sleep(60)
                    yield RuntimeEvent(
                        type="done",
                        name="assistant",
                        payload={"content": str(text), "status": "finished"},
                    )

            return InterruptThenEchoSession()

        client = AgentSDKClient(session_factory=session_factory)
        session = client.create_sdk_session(SDKOptions(session_id="now-drain-session"))

        async def collect():
            return [message async for message in session.query("wait")]

        collector = asyncio.create_task(collect())
        await started.wait()
        urgent = session.enqueue_async_message("urgent", priority="now")
        messages = await asyncio.wait_for(collector, timeout=2)
        return messages, urgent.uuid

    messages, urgent_uuid = asyncio.run(execute())
    results = [message.result for message in messages if isinstance(message, SDKResultMessage)]
    replay_users = [message for message in messages if isinstance(message, SDKUserMessage)]

    assert results == ["run canceled", "urgent"]
    assert replay_users == []
    assert urgent_uuid


def test_sdk_async_message_wakes_sleep_wait_and_drains():
    async def execute():
        started = asyncio.Event()
        workspace = WorkspaceContext(
            tenant_id="tenant",
            user_id="user",
            agent_id="agent",
            workspace_id="workspace",
            root=".",
            path=".",
        )

        async def session_factory(settings, spec):
            context = ToolRuntimeContext(
                workspace=workspace,
                sandbox=SandboxPolicy.for_workspace(workspace.path),
            )

            class SleepThenEchoSession:
                runtime = SimpleNamespace(model="scripted", protocol="scripted", enabled_tools=["sleep.wait"])

                def __init__(self):
                    self.tool_context = context
                    self.workspace = workspace

                async def stream(self, text, run_id=None):
                    if text == "sleep":
                        started.set()
                        result = await sleep_wait(
                            self.tool_context,
                            duration_seconds=60,
                            reason="wait for notifications",
                        )
                        yield RuntimeEvent(
                            type="done",
                            name="assistant",
                            payload={
                                "content": "sleep woke notification=%s" % result["woke_for_notification"],
                                "status": "finished",
                            },
                        )
                        return
                    yield RuntimeEvent(
                        type="done",
                        name="assistant",
                        payload={"content": str(text), "status": "finished"},
                    )

            return SleepThenEchoSession()

        client = AgentSDKClient(session_factory=session_factory)
        session = client.create_sdk_session(SDKOptions(session_id="sleep-drain-session"))

        async def collect():
            return [message async for message in session.query("sleep")]

        collector = asyncio.create_task(collect())
        await asyncio.wait_for(started.wait(), timeout=2)
        queued = session.enqueue_async_message("queued later", priority="later")
        messages = await asyncio.wait_for(collector, timeout=2)
        return messages, queued.uuid

    messages, queued_uuid = asyncio.run(execute())
    results = [message.result for message in messages if isinstance(message, SDKResultMessage)]

    assert results == ["sleep woke notification=True", "queued later"]
    assert queued_uuid


def test_sdk_run_stdin_processes_user_and_control_messages():
    async def execute():
        client = AgentSDKClient(session_factory=_echo_prompt_session_factory)
        messages = [
            {"type": "update_environment_variables", "variables": {"NEXUS_ENV": "test"}},
            {
                "type": "user",
                "session_id": "stdin-session",
                "uuid": "stdin-user-1",
                "message": {"role": "user", "content": [{"type": "text", "text": "first"}]},
                "isReplay": False,
            },
            {
                "type": "control_request",
                "request_id": "stdin-set-model",
                "request": {"subtype": "set_model", "model": "claude-sonnet"},
            },
            {"type": "keep_alive"},
            {
                "type": "control_response",
                "response": {
                    "subtype": "success",
                    "request_id": "host-response",
                    "response": {"ignored": True},
                },
            },
            {
                "type": "user",
                "session_id": "stdin-session",
                "uuid": "stdin-user-2",
                "message": {"role": "user", "content": [{"type": "text", "text": "second"}]},
                "priority": "later",
                "isReplay": False,
            },
        ]

        outputs = [message async for message in client.run_stdin(messages, SDKOptions(session_id="stdin-session"))]
        replay = await client.get_session_messages("stdin-session", {"include_system_messages": False})
        return outputs, replay

    outputs, replay = asyncio.run(execute())
    results = [message.result for message in outputs if isinstance(message, SDKResultMessage)]
    controls = [message for message in outputs if isinstance(message, SDKControlResponse)]
    replay_users = [message for message in replay if isinstance(message, SDKUserMessage)]

    assert callable(run_stdin)
    assert results == ["first", "second"]
    assert controls[0].response.response == {"model": "claude-sonnet"}
    assert [message.uuid for message in replay_users] == ["stdin-user-1", "stdin-user-2"]


def test_sdk_run_stdin_replays_acknowledgements_and_skips_runtime_duplicates(monkeypatch):
    monkeypatch.delenv("NEXUS_SDK_ENV", raising=False)

    async def execute():
        client = AgentSDKClient(session_factory=_echo_prompt_session_factory)
        messages = [
            {"type": "update_environment_variables", "variables": {"NEXUS_SDK_ENV": "test"}},
            {
                "type": "user",
                "session_id": "replay-session",
                "uuid": "replay-user-1",
                "message": {"role": "user", "content": [{"type": "text", "text": "first"}]},
                "isReplay": False,
            },
            {
                "type": "control_response",
                "response": {
                    "subtype": "success",
                    "requestId": "host-camel-response",
                    "response": {"ignored": True},
                },
            },
            {
                "type": "user",
                "session_id": "replay-session",
                "uuid": "replay-user-1",
                "message": {"role": "user", "content": [{"type": "text", "text": "duplicate"}]},
                "isReplay": False,
            },
        ]

        outputs = [
            message
            async for message in client.run_stdin(
                messages,
                {"session_id": "replay-session", "replayUserMessages": True},
            )
        ]
        replay = await client.get_session_messages("replay-session", {"include_system_messages": False})
        return outputs, replay

    outputs, replay = asyncio.run(execute())
    acks = [message for message in outputs if isinstance(message, SDKUserMessage)]
    results = [message.result for message in outputs if isinstance(message, SDKResultMessage)]
    controls = [message for message in outputs if isinstance(message, SDKControlResponse)]
    replay_users = [message for message in replay if isinstance(message, SDKUserMessage)]

    assert os.environ["NEXUS_SDK_ENV"] == "test"
    assert [message.uuid for message in acks] == ["replay-user-1", "replay-user-1"]
    assert all(message.isReplay for message in acks)
    assert results == ["first"]
    assert controls[0].response.request_id == "host-camel-response"
    assert [message.content for message in replay_users] == ["first"]


def test_sdk_run_stdin_drains_structured_io_outbound_and_resolves_responses():
    async def execute():
        client = AgentSDKClient(session_factory=_echo_prompt_session_factory)
        structured_io = SDKStructuredIO(replay_user_messages=True)
        inbound = asyncio.Queue()
        outputs = []

        async def source():
            while True:
                item = await inbound.get()
                if item is None:
                    return
                yield item

        async def collect():
            async for message in client.run_stdin(
                source(),
                SDKOptions(session_id="structured-stdin", replay_user_messages=True),
                structured_io=structured_io,
            ):
                outputs.append(message)

        collector = asyncio.create_task(collect())
        request_task = asyncio.create_task(
            structured_io.send_request(
                SDKControlMcpMessageRequest(
                    server_name="sdk-tools",
                    message={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                ),
                response_validator=lambda payload: payload["mcp_response"],
                request_id="mcp-structured",
            )
        )
        for _ in range(50):
            if outputs:
                break
            await asyncio.sleep(0.01)
        await inbound.put(
            {
                "type": "control_response",
                "response": {
                    "subtype": "success",
                    "request_id": "mcp-structured",
                    "response": {
                        "mcp_response": {"jsonrpc": "2.0", "id": 1, "result": {"tools": []}},
                    },
                },
            }
        )
        response = await asyncio.wait_for(request_task, timeout=1)
        for _ in range(50):
            if len(outputs) >= 2:
                break
            await asyncio.sleep(0.01)
        await inbound.put(None)
        await asyncio.wait_for(collector, timeout=1)
        return outputs, response

    outputs, response = asyncio.run(execute())

    assert isinstance(outputs[0], SDKControlRequest)
    assert outputs[0].request_id == "mcp-structured"
    assert isinstance(outputs[0].request, SDKControlMcpMessageRequest)
    assert isinstance(outputs[1], SDKControlResponse)
    assert outputs[1].response.request_id == "mcp-structured"
    assert response == {"jsonrpc": "2.0", "id": 1, "result": {"tools": []}}


def test_sdk_run_stdin_jsonl_uses_structured_frame_codec():
    async def execute():
        client = AgentSDKClient(session_factory=_echo_prompt_session_factory)
        chunks = [
            '{"type":"user","session_id":"jsonl-session","uuid":"jsonl-user",',
            '"message":{"role":"user","content":[{"type":"text","text":"hello jsonl"}]},',
            '"isReplay":false}\n',
        ]
        return [line async for line in client.run_stdin_jsonl(chunks, SDKOptions(session_id="jsonl-session"))]

    lines = asyncio.run(execute())
    payloads = [json.loads(line) for line in lines]
    results = [payload for payload in payloads if payload["type"] == "result"]

    assert callable(run_stdin_jsonl)
    assert all(line.endswith("\n") for line in lines)
    assert results[0]["result"] == "hello jsonl"
    assert results[0]["session_id"] == "jsonl-session"


def test_sdk_sse_frame_parser_handles_comments_partial_and_multiline_data():
    frames, remaining = parse_sse_frames(
        ":keepalive\n\n"
        'id: 7\nevent: client_event\ndata: {"a":1}\ndata: {"b":2}\n\n'
        'id: 8\nevent: client_event\ndata: {"partial":true}'
    )

    assert len(frames) == 2
    assert frames[0].event is None
    assert frames[0].id is None
    assert frames[0].data is None
    assert frames[1].id == "7"
    assert frames[1].event == "client_event"
    assert frames[1].data == '{"a":1}\n{"b":2}'
    assert remaining == 'id: 8\nevent: client_event\ndata: {"partial":true}'


def test_sdk_sse_url_helpers_match_src_origin_remote_io_shape():
    stream_url = derive_sse_stream_url("wss://api.example.com/session/abc?token=1")

    assert stream_url == "https://api.example.com/session/abc/worker/events/stream?token=1"
    assert derive_sse_post_url(stream_url) == "https://api.example.com/session/abc/worker/events"


def test_sdk_hybrid_url_helper_matches_src_origin_shape():
    assert derive_hybrid_post_url("wss://api.example.com/v2/session_ingress/ws/abc?token=1") == (
        "https://api.example.com/v2/session_ingress/session/abc/events?token=1"
    )


class _FakeWebSocketClosed(Exception):
    def __init__(self, code):
        super().__init__(f"closed {code}")
        self.code = code


class _FakeWebSocket:
    def __init__(self, *, recv_items=None, response_headers=None, ping_error=None):
        self.recv_items = list(recv_items or [])
        self.response_headers = dict(response_headers or {})
        self.ping_error = ping_error
        self.sent = []
        self.pings = 0
        self.closed = False

    async def recv(self):
        if self.recv_items:
            item = self.recv_items.pop(0)
            if isinstance(item, Exception):
                raise item
            return item
        await asyncio.Event().wait()

    async def send(self, data):
        self.sent.append(data)

    async def ping(self):
        self.pings += 1
        if self.ping_error is not None:
            raise self.ping_error

    async def close(self):
        self.closed = True


def test_sdk_websocket_transport_resolves_proxy_and_tls_options():
    async def execute():
        captured = []
        tls_context = object()

        async def connector(url, headers, options):
            captured.append((url, dict(headers), options))
            return _FakeWebSocket()

        transport = SDKWebSocketJsonlTransport(
            "wss://api.example.com/v2/session_ingress/ws/abc",
            headers={"Authorization": "Bearer token"},
            connector=connector,
            ssl_context=tls_context,
            env={"https_proxy": "http://proxy.local:8080", "no_proxy": "localhost"},
            ping_interval_seconds=None,
            keepalive_interval_seconds=None,
        )
        await transport.connect()
        await transport.close()
        return captured, tls_context

    captured, tls_context = asyncio.run(execute())
    options = captured[0][2]

    assert isinstance(options, SDKWebSocketConnectOptions)
    assert captured[0][1]["Authorization"] == "Bearer token"
    assert options.proxy == "http://proxy.local:8080"
    assert options.ssl_context is tls_context


def test_sdk_websocket_transport_honors_no_proxy_rules():
    async def execute():
        captured = []

        async def connector(url, headers, options):
            captured.append(options.proxy)
            return _FakeWebSocket()

        transport = SDKWebSocketJsonlTransport(
            "wss://api.example.com/v2/session_ingress/ws/abc",
            connector=connector,
            env={
                "HTTPS_PROXY": "http://proxy.local:8080",
                "NO_PROXY": ".example.com",
            },
            ping_interval_seconds=None,
            keepalive_interval_seconds=None,
        )
        await transport.connect()
        await transport.close()
        return captured

    captured = asyncio.run(execute())

    assert captured == [None]


def test_sdk_websocket_transport_reconnects_and_replays_unconfirmed_messages():
    async def execute():
        sockets = [
            _FakeWebSocket(recv_items=[_FakeWebSocketClosed(1006)]),
            _FakeWebSocket(
                recv_items=['{"type":"keep_alive"}\n'],
                response_headers={"x-last-request-id": "uuid-1"},
            ),
        ]
        calls = []

        async def connector(url, headers):
            calls.append((url, dict(headers)))
            return sockets[len(calls) - 1]

        async def sleep(delay):
            return None

        transport = SDKWebSocketJsonlTransport(
            "wss://api.example.com/v2/session_ingress/ws/abc",
            headers={"Authorization": "Bearer token"},
            connector=connector,
            reconnect_base_delay_seconds=0,
            sleep=sleep,
        )
        await transport.write('{"type":"result","uuid":"uuid-1","result":"one"}\n')
        await transport.write('{"type":"result","uuid":"uuid-2","result":"two"}\n')
        inbound = await asyncio.wait_for(transport.read(), timeout=1)
        await transport.close()
        return inbound, sockets, calls

    inbound, sockets, calls = asyncio.run(execute())

    assert inbound == '{"type":"keep_alive"}\n'
    assert calls[0][1]["Authorization"] == "Bearer token"
    assert calls[1][1]["X-Last-Request-Id"] == "uuid-2"
    assert json.loads(sockets[0].sent[0])["uuid"] == "uuid-1"
    assert json.loads(sockets[0].sent[1])["uuid"] == "uuid-2"
    assert [json.loads(line)["uuid"] for line in sockets[1].sent] == ["uuid-2"]


def test_sdk_websocket_transport_stops_on_permanent_close_code():
    async def execute():
        socket = _FakeWebSocket(recv_items=[_FakeWebSocketClosed(4001)])
        closed = []

        async def connector(url, headers):
            return socket

        transport = SDKWebSocketJsonlTransport(
            "wss://api.example.com/v2/session_ingress/ws/abc",
            connector=connector,
        )
        transport.set_on_close(lambda close_code: closed.append(close_code))
        line = await asyncio.wait_for(transport.read(), timeout=1)
        return line, closed, transport.is_closed_status()

    line, closed, is_closed = asyncio.run(execute())

    assert line is None
    assert closed == [4001]
    assert is_closed is True


def test_sdk_websocket_transport_refreshes_headers_for_unauthorized_close():
    async def execute():
        sockets = [
            _FakeWebSocket(recv_items=[_FakeWebSocketClosed(4003)]),
            _FakeWebSocket(recv_items=['{"type":"keep_alive"}\n']),
        ]
        calls = []

        async def connector(url, headers):
            calls.append((url, dict(headers)))
            return sockets[len(calls) - 1]

        async def sleep(delay):
            return None

        transport = SDKWebSocketJsonlTransport(
            "wss://api.example.com/v2/session_ingress/ws/abc",
            headers={"Authorization": "Bearer old"},
            refresh_headers=lambda: {"Authorization": "Bearer new"},
            connector=connector,
            reconnect_base_delay_seconds=0,
            sleep=sleep,
        )
        line = await asyncio.wait_for(transport.read(), timeout=1)
        await transport.close()
        return line, calls

    line, calls = asyncio.run(execute())

    assert line == '{"type":"keep_alive"}\n'
    assert calls[0][1]["Authorization"] == "Bearer old"
    assert calls[1][1]["Authorization"] == "Bearer new"


def test_sdk_websocket_transport_sends_periodic_keepalive_frame():
    async def execute():
        socket = _FakeWebSocket()

        async def connector(url, headers):
            return socket

        transport = SDKWebSocketJsonlTransport(
            "wss://api.example.com/v2/session_ingress/ws/abc",
            connector=connector,
            ping_interval_seconds=None,
            keepalive_interval_seconds=0.01,
        )
        await transport.connect()
        for _ in range(20):
            if socket.sent:
                break
            await asyncio.sleep(0.01)
        await transport.close()
        return socket.sent

    sent = asyncio.run(execute())

    assert sent == ['{"type":"keep_alive"}\n']


def test_sdk_websocket_transport_reconnects_after_ping_failure():
    async def execute():
        sockets = [
            _FakeWebSocket(ping_error=RuntimeError("no pong")),
            _FakeWebSocket(),
        ]
        calls = []

        async def connector(url, headers):
            calls.append((url, dict(headers)))
            return sockets[len(calls) - 1]

        async def sleep(delay):
            return None

        transport = SDKWebSocketJsonlTransport(
            "wss://api.example.com/v2/session_ingress/ws/abc",
            connector=connector,
            reconnect_base_delay_seconds=0,
            ping_interval_seconds=0.01,
            keepalive_interval_seconds=None,
            sleep=sleep,
        )
        await transport.connect()
        for _ in range(20):
            if len(calls) >= 2:
                break
            await asyncio.sleep(0.01)
        await transport.close()
        return calls, sockets

    calls, sockets = asyncio.run(execute())

    assert len(calls) == 2
    assert sockets[0].pings == 1
    assert sockets[0].closed is True


def test_sdk_websocket_transport_reconnects_after_sleep_gap_detection():
    async def execute():
        sockets = [_FakeWebSocket(), _FakeWebSocket()]
        calls = []
        ticks = [0.0, 61.0]

        async def connector(url, headers):
            calls.append((url, dict(headers)))
            return sockets[len(calls) - 1]

        async def sleep(delay):
            return None

        transport = SDKWebSocketJsonlTransport(
            "wss://api.example.com/v2/session_ingress/ws/abc",
            connector=connector,
            reconnect_base_delay_seconds=0,
            ping_interval_seconds=0.01,
            keepalive_interval_seconds=None,
            sleep_detection_threshold_seconds=60,
            monotonic=lambda: ticks.pop(0) if ticks else 61.0,
            sleep=sleep,
        )
        await transport.connect()
        for _ in range(20):
            if len(calls) >= 2:
                break
            await asyncio.sleep(0.01)
        await transport.close()
        return calls, sockets

    calls, sockets = asyncio.run(execute())

    assert len(calls) == 2
    assert sockets[0].pings == 0
    assert sockets[0].closed is True


class _FakeCCRTransport:
    def __init__(self):
        self.on_event = None

    def set_on_event(self, handler):
        self.on_event = handler


def _jwt_with_expiry(expiry: int) -> str:
    def segment(payload):
        encoded = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8"))
        return encoded.decode("ascii").rstrip("=")

    return f"{segment({'alg': 'none'})}.{segment({'exp': expiry})}."


def test_sdk_ccr_client_initializes_and_acks_transport_events():
    async def execute():
        requests = []
        transport = _FakeCCRTransport()

        async def request(method, path, headers, body):
            requests.append((method, path, dict(headers), body))
            if method == "get" and path == "/worker":
                return SDKCCRRequestResult(
                    True,
                    data={"worker": {"external_metadata": {"pending_action": "approve"}}},
                )
            return SDKCCRRequestResult(True)

        client = SDKCCRClient(
            "https://api.example.com/v1/code/sessions/session-1",
            transport=transport,
            request=request,
            get_auth_headers=lambda: {"Authorization": "Bearer token"},
            heartbeat_interval_seconds=None,
        )
        restored = await client.initialize(epoch=7)
        transport.on_event({"event_id": "evt-1"})
        await client.flush_delivery()
        await client.close()
        return restored, requests

    restored, requests = asyncio.run(execute())

    assert restored == {"pending_action": "approve"}
    assert requests[0] == (
        "put",
        "/worker",
        {"Authorization": "Bearer token"},
        {
            "worker_status": "idle",
            "worker_epoch": 7,
            "external_metadata": {"pending_action": None, "task_summary": None},
        },
    )
    assert requests[1][0:2] == ("get", "/worker")
    assert requests[1][3] is None
    assert requests[2][0:2] == ("post", "/worker/events/delivery")
    assert requests[2][3] == {
        "worker_epoch": 7,
        "updates": [{"event_id": "evt-1", "status": "received"}],
    }


def test_sdk_ccr_client_writes_client_and_internal_events():
    async def execute():
        requests = []

        async def request(method, path, headers, body):
            requests.append((method, path, body))
            return SDKCCRRequestResult(True)

        client = SDKCCRClient(
            "https://api.example.com/v1/code/sessions/session-2",
            request=request,
            get_auth_headers=lambda: {"Authorization": "Bearer token"},
            heartbeat_interval_seconds=None,
        )
        await client.initialize(epoch=9)
        await client.write_event({"type": "result", "uuid": "result-1", "result": "ok"})
        await client.flush()
        await client.write_internal_event(
            "transcript",
            {"uuid": "internal-1", "message": {"role": "assistant"}},
            is_compaction=True,
            agent_id="agent-1",
        )
        await client.flush_internal_events()
        await client.close()
        return requests

    requests = asyncio.run(execute())
    client_events = next(request for request in requests if request[1] == "/worker/events")
    internal_events = next(
        request for request in requests if request[1] == "/worker/internal-events"
    )

    assert client_events[0:2] == ("post", "/worker/events")
    assert client_events[2] == {
        "worker_epoch": 9,
        "events": [
            {"payload": {"type": "result", "uuid": "result-1", "result": "ok"}}
        ],
    }
    assert internal_events[0:2] == ("post", "/worker/internal-events")
    assert internal_events[2] == {
        "worker_epoch": 9,
        "events": [
            {
                "payload": {
                    "type": "transcript",
                    "uuid": "internal-1",
                    "message": {"role": "assistant"},
                },
                "is_compaction": True,
                "agent_id": "agent-1",
            }
        ],
    }


def test_sdk_ccr_client_coalesces_stream_event_text_deltas():
    async def execute():
        requests = []

        async def request(method, path, headers, body):
            requests.append((method, path, body))
            return SDKCCRRequestResult(True)

        client = SDKCCRClient(
            "https://api.example.com/v1/code/sessions/session-3",
            request=request,
            get_auth_headers=lambda: {"Authorization": "Bearer token"},
            heartbeat_interval_seconds=None,
            stream_event_flush_interval_seconds=60,
        )
        await client.initialize(epoch=11)
        await client.write_event(
            {
                "type": "stream_event",
                "uuid": "start-1",
                "session_id": "session-3",
                "parent_tool_use_id": None,
                "event": {
                    "type": "message_start",
                    "message": {"id": "msg-1"},
                },
            }
        )
        await client.write_event(
            {
                "type": "stream_event",
                "uuid": "delta-1",
                "session_id": "session-3",
                "parent_tool_use_id": None,
                "event": {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": "he"},
                },
            }
        )
        await client.flush()
        await client.write_event(
            {
                "type": "stream_event",
                "uuid": "delta-2",
                "session_id": "session-3",
                "parent_tool_use_id": None,
                "event": {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": "llo"},
                },
            }
        )
        await client.flush()
        await client.close()
        return requests

    requests = asyncio.run(execute())
    event_posts = [request for request in requests if request[1] == "/worker/events"]
    first_batch = event_posts[0][2]["events"]
    second_batch = event_posts[1][2]["events"]

    assert first_batch == [
        {
            "payload": {
                "type": "stream_event",
                "uuid": "start-1",
                "session_id": "session-3",
                "parent_tool_use_id": None,
                "event": {"type": "message_start", "message": {"id": "msg-1"}},
            },
            "ephemeral": True,
        },
        {
            "payload": {
                "type": "stream_event",
                "uuid": "delta-1",
                "session_id": "session-3",
                "parent_tool_use_id": None,
                "event": {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": "he"},
                },
            },
            "ephemeral": True,
        },
    ]
    assert second_batch == [
        {
            "payload": {
                "type": "stream_event",
                "uuid": "delta-2",
                "session_id": "session-3",
                "parent_tool_use_id": None,
                "event": {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": "hello"},
                },
            },
            "ephemeral": True,
        }
    ]


def test_sdk_ccr_client_reads_restored_internal_events_with_pagination():
    async def execute():
        requests = []

        async def request(method, path, headers, body):
            requests.append((method, path, body))
            if path == "/worker/internal-events":
                return SDKCCRRequestResult(
                    True,
                    data={
                        "data": [{"event_id": "foreground-1"}],
                        "next_cursor": "cursor-1",
                    },
                )
            if path == "/worker/internal-events?cursor=cursor-1":
                return SDKCCRRequestResult(
                    True,
                    data={"data": [{"event_id": "foreground-2"}]},
                )
            if path == "/worker/internal-events?subagents=true":
                return SDKCCRRequestResult(
                    True,
                    data={"data": [{"event_id": "subagent-1"}]},
                )
            return SDKCCRRequestResult(False, status=404)

        client = SDKCCRClient(
            "https://api.example.com/v1/code/sessions/session-4",
            request=request,
            get_auth_headers=lambda: {"Authorization": "Bearer token"},
            heartbeat_interval_seconds=None,
            get_base_delay_seconds=0,
        )
        foreground = await client.read_internal_events()
        subagents = await client.read_subagent_internal_events()
        await client.close()
        return foreground, subagents, requests

    foreground, subagents, requests = asyncio.run(execute())

    assert foreground == [{"event_id": "foreground-1"}, {"event_id": "foreground-2"}]
    assert subagents == [{"event_id": "subagent-1"}]
    assert requests == [
        ("get", "/worker/internal-events", None),
        ("get", "/worker/internal-events?cursor=cursor-1", None),
        ("get", "/worker/internal-events?subagents=true", None),
    ]


def test_sdk_ccr_client_retries_internal_event_reads():
    async def execute():
        attempts = 0
        sleeps = []

        async def request(method, path, headers, body):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                return SDKCCRRequestResult(False, status=500)
            return SDKCCRRequestResult(True, data={"data": [{"event_id": "evt-1"}]})

        async def sleep(delay):
            sleeps.append(delay)

        client = SDKCCRClient(
            "https://api.example.com/v1/code/sessions/session-5",
            request=request,
            get_auth_headers=lambda: {"Authorization": "Bearer token"},
            heartbeat_interval_seconds=None,
            get_base_delay_seconds=0.25,
            sleep=sleep,
        )
        events = await client.read_internal_events()
        await client.close()
        return attempts, sleeps, events

    attempts, sleeps, events = asyncio.run(execute())

    assert attempts == 2
    assert sleeps == [0.25]
    assert events == [{"event_id": "evt-1"}]


def test_sdk_ccr_client_triggers_shutdown_on_epoch_mismatch():
    async def execute():
        shutdowns = []

        async def request(method, path, headers, body):
            return SDKCCRRequestResult(False, status=409)

        client = SDKCCRClient(
            "https://api.example.com/v1/code/sessions/session-6",
            request=request,
            get_auth_headers=lambda: {"Authorization": "Bearer token"},
            on_shutdown=shutdowns.append,
            heartbeat_interval_seconds=None,
            get_base_delay_seconds=0,
        )
        with pytest.raises(SDKCCREpochMismatchError) as exc_info:
            await client.read_internal_events()
        await client.close()
        return exc_info.value.reason, shutdowns, client.shutdown_reason

    reason, shutdowns, shutdown_reason = asyncio.run(execute())

    assert reason == "epoch_mismatch"
    assert shutdowns == ["epoch_mismatch"]
    assert shutdown_reason == "epoch_mismatch"


def test_sdk_ccr_client_shutdowns_immediately_for_expired_jwt():
    async def execute():
        shutdowns = []
        attempts = 0

        async def request(method, path, headers, body):
            nonlocal attempts
            attempts += 1
            return SDKCCRRequestResult(False, status=401)

        client = SDKCCRClient(
            "https://api.example.com/v1/code/sessions/session-7",
            request=request,
            get_auth_headers=lambda: {
                "Authorization": f"Bearer {_jwt_with_expiry(100)}"
            },
            on_shutdown=shutdowns.append,
            heartbeat_interval_seconds=None,
            get_base_delay_seconds=0,
            now=lambda: 200.0,
        )
        with pytest.raises(SDKCCRAuthFailureError) as exc_info:
            await client.read_internal_events()
        await client.close()
        return exc_info.value.reason, shutdowns, attempts

    reason, shutdowns, attempts = asyncio.run(execute())

    assert reason == "auth_expired"
    assert shutdowns == ["auth_expired"]
    assert attempts == 1


def test_sdk_ccr_client_shutdowns_after_consecutive_auth_failures():
    async def execute():
        shutdowns = []
        attempts = 0
        sleeps = []

        async def request(method, path, headers, body):
            nonlocal attempts
            attempts += 1
            return SDKCCRRequestResult(False, status=403)

        async def sleep(delay):
            sleeps.append(delay)

        client = SDKCCRClient(
            "https://api.example.com/v1/code/sessions/session-8",
            request=request,
            get_auth_headers=lambda: {
                "Authorization": f"Bearer {_jwt_with_expiry(1000)}"
            },
            on_shutdown=shutdowns.append,
            max_consecutive_auth_failures=2,
            heartbeat_interval_seconds=None,
            get_base_delay_seconds=0.25,
            sleep=sleep,
            now=lambda: 200.0,
        )
        with pytest.raises(SDKCCRAuthFailureError) as exc_info:
            await client.read_internal_events()
        await client.close()
        return exc_info.value.reason, shutdowns, attempts, sleeps

    reason, shutdowns, attempts, sleeps = asyncio.run(execute())

    assert reason == "auth_failures_exhausted"
    assert shutdowns == ["auth_failures_exhausted"]
    assert attempts == 2
    assert sleeps == [0.25]


def test_sdk_worker_state_uploader_coalesces_metadata_patches():
    async def execute():
        sent = []

        async def send(body):
            sent.append(body)
            return True

        uploader = SDKWorkerStateUploader(send)
        uploader.enqueue({"external_metadata": {"a": 1}, "worker_status": "running"})
        uploader.enqueue({"external_metadata": {"b": 2}, "worker_status": "idle"})
        await uploader.flush()
        return sent

    sent = asyncio.run(execute())

    assert sent == [
        {"external_metadata": {"a": 1, "b": 2}, "worker_status": "idle"}
    ]


def test_sdk_sse_transport_unwraps_client_events_and_posts_stdout():
    async def chunks():
        yield ":keepalive\n\n"
        yield (
            "id: 41\n"
            "event: client_event\n"
            "data: "
            + json.dumps(
                {
                    "event_id": "evt-41",
                    "sequence_num": 41,
                    "event_type": "sdk",
                    "source": "worker",
                    "payload": {
                        "type": "user",
                        "session_id": "sse-session",
                        "uuid": "sse-user",
                        "message": {
                            "role": "user",
                            "content": [{"type": "text", "text": "hello sse"}],
                        },
                        "isReplay": False,
                    },
                    "created_at": "2026-05-21T00:00:00Z",
                },
                separators=(",", ":"),
            )
            + "\n\n"
        )

    async def execute():
        posted = []

        async def post_message(url, headers, message):
            posted.append((url, dict(headers), message))
            return 201

        transport = SDKSSEJsonlTransport(
            "https://api.example.com/session/abc/worker/events/stream",
            headers={"Authorization": "Bearer token"},
            read_chunks=chunks(),
            post_message=post_message,
        )
        line = await asyncio.wait_for(transport.read(), timeout=1)
        closed = await asyncio.wait_for(transport.read(), timeout=1)
        await transport.write('{"type":"keep_alive"}\n')
        await transport.close()
        return line, closed, posted, transport.get_last_sequence_num()

    line, closed, posted, last_sequence_num = asyncio.run(execute())
    payload = json.loads(line)

    assert payload["type"] == "user"
    assert payload["session_id"] == "sse-session"
    assert payload["message"]["content"][0]["text"] == "hello sse"
    assert closed is None
    assert last_sequence_num == 41
    assert posted[0][0] == "https://api.example.com/session/abc/worker/events"
    assert posted[0][1]["Content-Type"] == "application/json"
    assert posted[0][1]["Authorization"] == "Bearer token"
    assert posted[0][2] == {"type": "keep_alive"}


def test_sdk_sse_transport_reconnects_with_sequence_resume_and_refreshed_headers():
    def event(seq, text):
        return (
            f"id: {seq}\n"
            "event: client_event\n"
            "data: "
            + json.dumps(
                {
                    "event_id": f"evt-{seq}",
                    "sequence_num": seq,
                    "event_type": "sdk",
                    "source": "worker",
                    "payload": {
                        "type": "user",
                        "session_id": "sse-reconnect",
                        "uuid": f"sse-reconnect-{seq}",
                        "message": {
                            "role": "user",
                            "content": [{"type": "text", "text": text}],
                        },
                        "isReplay": False,
                    },
                    "created_at": "2026-05-21T00:00:00Z",
                },
                separators=(",", ":"),
            )
            + "\n\n"
        )

    async def execute():
        calls = []
        refreshes = []

        def refresh_headers():
            token = f"Bearer token-{len(refreshes) + 1}"
            refreshes.append(token)
            return {"Authorization": token}

        def read_chunks_factory(url, headers):
            calls.append((url, dict(headers)))
            seq = len(calls)

            async def chunks():
                yield event(seq, f"message {seq}")
                if seq >= 2:
                    await asyncio.Event().wait()

            return chunks()

        transport = SDKSSEJsonlTransport(
            "https://api.example.com/session/abc/worker/events/stream",
            headers={"Authorization": "Bearer seed"},
            refresh_headers=refresh_headers,
            read_chunks_factory=read_chunks_factory,
            reconnect_base_delay_seconds=0,
            liveness_timeout_seconds=None,
        )
        first = await asyncio.wait_for(transport.read(), timeout=1)
        second = await asyncio.wait_for(transport.read(), timeout=1)
        await transport.close()
        return json.loads(first), json.loads(second), calls, refreshes, transport.last_sequence_num

    first, second, calls, refreshes, last_sequence_num = asyncio.run(execute())

    assert first["message"]["content"][0]["text"] == "message 1"
    assert second["message"]["content"][0]["text"] == "message 2"
    assert calls[0][0] == "https://api.example.com/session/abc/worker/events/stream"
    assert calls[1][0] == (
        "https://api.example.com/session/abc/worker/events/stream?from_sequence_num=1"
    )
    assert "Last-Event-ID" not in calls[0][1]
    assert calls[1][1]["Last-Event-ID"] == "1"
    assert calls[0][1]["Authorization"] != calls[1][1]["Authorization"]
    assert len(refreshes) >= 2
    assert last_sequence_num == 2


def test_sdk_sse_transport_liveness_timeout_reconnects():
    def event(seq, text):
        return (
            f"id: {seq}\n"
            "event: client_event\n"
            "data: "
            + json.dumps(
                {
                    "event_id": f"evt-{seq}",
                    "sequence_num": seq,
                    "event_type": "sdk",
                    "source": "worker",
                    "payload": {
                        "type": "user",
                        "session_id": "sse-liveness",
                        "uuid": f"sse-liveness-{seq}",
                        "message": {
                            "role": "user",
                            "content": [{"type": "text", "text": text}],
                        },
                        "isReplay": False,
                    },
                    "created_at": "2026-05-21T00:00:00Z",
                },
                separators=(",", ":"),
            )
            + "\n\n"
        )

    async def execute():
        calls = []

        def read_chunks_factory(url, headers):
            calls.append((url, dict(headers)))
            seq = len(calls)

            async def chunks():
                if seq == 1:
                    await asyncio.sleep(0.05)
                    yield event(seq, "stale")
                else:
                    yield event(seq, "after timeout")
                    await asyncio.Event().wait()

            return chunks()

        transport = SDKSSEJsonlTransport(
            "https://api.example.com/session/abc/worker/events/stream",
            read_chunks_factory=read_chunks_factory,
            reconnect_base_delay_seconds=0,
            liveness_timeout_seconds=0.01,
        )
        line = await asyncio.wait_for(transport.read(), timeout=1)
        await transport.close()
        return json.loads(line), calls, transport.last_sequence_num

    payload, calls, last_sequence_num = asyncio.run(execute())

    assert payload["message"]["content"][0]["text"] == "after timeout"
    assert len(calls) == 2
    assert last_sequence_num == 2


def test_sdk_sse_transport_closes_after_reconnect_budget_exhaustion():
    async def execute():
        calls = []
        closed = []
        ticks = iter([0.0, 601.0])

        def read_chunks_factory(url, headers):
            calls.append((url, dict(headers)))
            raise RuntimeError("connection failed")

        async def sleep(delay):
            return None

        transport = SDKSSEJsonlTransport(
            "https://api.example.com/session/abc/worker/events/stream",
            read_chunks_factory=read_chunks_factory,
            reconnect_base_delay_seconds=0,
            reconnect_give_up_seconds=600,
            monotonic=lambda: next(ticks),
            sleep=sleep,
        )
        transport.set_on_close(lambda close_code: closed.append(close_code))
        line = await asyncio.wait_for(transport.read(), timeout=1)
        return line, calls, closed, transport.is_closed_status()

    line, calls, closed, is_closed = asyncio.run(execute())

    assert line is None
    assert len(calls) == 2
    assert closed == [None]
    assert is_closed is True


def test_sdk_hybrid_transport_reads_from_reader_and_batches_ordered_posts():
    async def execute():
        reader = SDKQueueJsonlTransport()
        posted = []

        async def post_message(url, headers, body):
            posted.append((url, dict(headers), body))
            return 200

        transport = SDKHybridJsonlTransport(
            "wss://api.example.com/v2/session_ingress/ws/abc?token=1",
            headers={"Authorization": "Bearer token"},
            reader=reader,
            post_message=post_message,
            stream_event_flush_interval_seconds=60,
        )
        await reader.send('{"type":"keep_alive"}\n')
        inbound = await asyncio.wait_for(transport.read(), timeout=1)
        await transport.write('{"type":"stream_event","delta":"a"}\n')
        await transport.write('{"type":"result","result":"done"}\n')
        await transport.close()
        return inbound, posted

    inbound, posted = asyncio.run(execute())

    assert inbound == '{"type":"keep_alive"}\n'
    assert posted[0][0] == "https://api.example.com/v2/session_ingress/session/abc/events?token=1"
    assert posted[0][1]["Authorization"] == "Bearer token"
    assert posted[0][1]["Content-Type"] == "application/json"
    assert posted[0][2] == {
        "events": [
            {"type": "stream_event", "delta": "a"},
            {"type": "result", "result": "done"},
        ]
    }


def test_sdk_hybrid_transport_retries_retryable_posts_and_tracks_drops():
    async def execute():
        statuses = [500, 500]
        dropped = []
        posted = []

        async def post_message(url, headers, body):
            posted.append(body)
            return statuses.pop(0)

        async def sleep(delay):
            return None

        transport = SDKHybridJsonlTransport(
            "wss://api.example.com/v2/session_ingress/ws/abc",
            reader=SDKQueueJsonlTransport(),
            post_message=post_message,
            max_consecutive_failures=2,
            on_batch_dropped=lambda batch_size, failures: dropped.append((batch_size, failures)),
            post_base_delay_seconds=0,
            sleep=sleep,
        )
        await transport.write('{"type":"result","result":"dropped"}\n')
        await transport.close()
        return posted, dropped, transport.dropped_batch_count

    posted, dropped, dropped_batch_count = asyncio.run(execute())

    assert posted == [
        {"events": [{"type": "result", "result": "dropped"}]},
        {"events": [{"type": "result", "result": "dropped"}]},
    ]
    assert dropped == [(1, 2)]
    assert dropped_batch_count == 1


def test_sdk_run_jsonl_transport_pumps_queue_transport():
    async def execute():
        client = AgentSDKClient(session_factory=_echo_prompt_session_factory)
        transport = SDKQueueJsonlTransport()
        runner = asyncio.create_task(
            client.run_jsonl_transport(transport, SDKOptions(session_id="transport-session"))
        )
        await transport.send(
            '{"type":"user","session_id":"transport-session","uuid":"transport-user",'
            '"message":{"role":"user","content":[{"type":"text","text":"hello transport"}]},'
            '"isReplay":false}\n'
        )
        await transport.close_input()
        await asyncio.wait_for(runner, timeout=1)
        return transport.drain_output(), transport.closed

    lines, closed = asyncio.run(execute())
    payloads = [json.loads(line) for line in lines]
    results = [payload for payload in payloads if payload["type"] == "result"]

    assert callable(run_jsonl_transport)
    assert closed is True
    assert results[0]["result"] == "hello transport"
    assert results[0]["session_id"] == "transport-session"


def test_sdk_run_jsonl_transport_pumps_hybrid_transport():
    async def execute():
        client = AgentSDKClient(session_factory=_echo_prompt_session_factory)
        reader = SDKQueueJsonlTransport()
        posted = []

        async def post_message(url, headers, body):
            posted.append(body)
            return 200

        transport = SDKHybridJsonlTransport(
            "wss://api.example.com/v2/session_ingress/ws/abc",
            reader=reader,
            post_message=post_message,
            stream_event_flush_interval_seconds=0,
        )
        runner = asyncio.create_task(
            client.run_jsonl_transport(transport, SDKOptions(session_id="hybrid-runner"))
        )
        await reader.send(
            '{"type":"user","session_id":"hybrid-runner","uuid":"hybrid-user",'
            '"message":{"role":"user","content":[{"type":"text","text":"hello hybrid"}]},'
            '"isReplay":false}\n'
        )
        await reader.close_input()
        await asyncio.wait_for(runner, timeout=1)
        return posted, transport.closed

    posted, closed = asyncio.run(execute())
    result_events = [
        event
        for body in posted
        for event in body["events"]
        if event["type"] == "result"
    ]

    assert closed is True
    assert result_events[0]["result"] == "hello hybrid"
    assert result_events[0]["session_id"] == "hybrid-runner"


def test_sdk_run_jsonl_transport_pumps_sse_transport():
    async def chunks():
        yield (
            "id: 9\n"
            "event: client_event\n"
            "data: "
            + json.dumps(
                {
                    "event_id": "evt-9",
                    "sequence_num": 9,
                    "event_type": "sdk",
                    "source": "worker",
                    "payload": {
                        "type": "user",
                        "session_id": "sse-runner",
                        "uuid": "sse-runner-user",
                        "message": {
                            "role": "user",
                            "content": [{"type": "text", "text": "hello runner"}],
                        },
                        "isReplay": False,
                    },
                    "created_at": "2026-05-21T00:00:00Z",
                },
                separators=(",", ":"),
            )
            + "\n\n"
        )

    async def execute():
        client = AgentSDKClient(session_factory=_echo_prompt_session_factory)
        posted = []

        async def post_message(url, headers, message):
            posted.append(message)
            return 200

        transport = SDKSSEJsonlTransport(
            "https://api.example.com/session/abc/worker/events/stream",
            read_chunks=chunks(),
            post_message=post_message,
            post_base_delay_seconds=0,
        )
        await client.run_jsonl_transport(transport, SDKOptions(session_id="sse-runner"))
        return posted, transport.closed, transport.last_sequence_num

    posted, closed, last_sequence_num = asyncio.run(execute())
    results = [message for message in posted if message["type"] == "result"]

    assert closed is True
    assert last_sequence_num == 9
    assert results[0]["result"] == "hello runner"
    assert results[0]["session_id"] == "sse-runner"


def test_sdk_jsonl_transport_drains_structured_io_outbound_and_responses():
    async def execute():
        client = AgentSDKClient(session_factory=_echo_prompt_session_factory)
        transport = SDKQueueJsonlTransport()
        structured_io = SDKStructuredIO(replay_user_messages=True)
        runner = asyncio.create_task(
            client.run_jsonl_transport(
                transport,
                SDKOptions(session_id="transport-control", replay_user_messages=True),
                structured_io=structured_io,
            )
        )
        request_task = asyncio.create_task(
            structured_io.send_request(
                SDKControlMcpMessageRequest(
                    server_name="sdk-tools",
                    message={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                ),
                response_validator=lambda payload: payload["mcp_response"],
                request_id="transport-mcp",
            )
        )
        first_line = await asyncio.wait_for(transport.receive(), timeout=1)
        await transport.send(
            '{"type":"control_response","response":{"subtype":"success",'
            '"request_id":"transport-mcp",'
            '"response":{"mcp_response":{"jsonrpc":"2.0","id":2,"result":{"tools":[]}}}}}\n'
        )
        response = await asyncio.wait_for(request_task, timeout=1)
        second_line = await asyncio.wait_for(transport.receive(), timeout=1)
        await transport.close_input()
        await asyncio.wait_for(runner, timeout=1)
        return json.loads(first_line), json.loads(second_line), response

    first, second, response = asyncio.run(execute())

    assert first["type"] == "control_request"
    assert first["request_id"] == "transport-mcp"
    assert first["request"]["subtype"] == "mcp_message"
    assert second["type"] == "control_response"
    assert second["response"]["request_id"] == "transport-mcp"
    assert response == {"jsonrpc": "2.0", "id": 2, "result": {"tools": []}}


def test_sdk_control_request_seeds_read_state_for_next_session(tmp_path):
    async def execute():
        notes = tmp_path / "notes.txt"
        notes.write_text("observed\n", encoding="utf-8")
        client = AgentSDKClient(session_factory=_read_state_seed_session_factory)
        session = client.create_sdk_session(
            SDKOptions(
                session_id="read-state-session",
                tenant_id="tenant",
                user_id="user",
                agent_id="agent",
                cwd=str(tmp_path),
            )
        )
        seed = await session.handle_control_request(
            SDKControlRequest(
                request_id="seed-read-state",
                request=SDKControlSeedReadStateRequest(
                    path="notes.txt",
                    mtime=int(notes.stat().st_mtime * 1000),
                ),
            )
        )
        messages = await _collect(session.query("write with seeded read state"))
        result = next(message for message in messages if isinstance(message, SDKResultMessage))
        return seed, result, notes.read_text(encoding="utf-8")

    seed, result, content = asyncio.run(execute())

    assert seed.response.response["seeded"] is True
    assert seed.response.response["path"] == "notes.txt"
    assert result.result == "seeded write"
    assert content == "updated\n"


def test_sdk_control_request_skips_stale_read_state_seed(tmp_path):
    async def execute():
        notes = tmp_path / "notes.txt"
        notes.write_text("observed\n", encoding="utf-8")
        client = AgentSDKClient(session_factory=_read_state_seed_session_factory)
        session = client.create_sdk_session(SDKOptions(session_id="stale-seed-session", cwd=str(tmp_path)))
        seed = await session.handle_control_request(
            SDKControlRequest(
                request_id="stale-seed",
                request=SDKControlSeedReadStateRequest(path="notes.txt", mtime=0),
            )
        )
        messages = await _collect(session.query("write without valid seed"))
        result = next(message for message in messages if isinstance(message, SDKResultMessage))
        return seed, result, notes.read_text(encoding="utf-8")

    seed, result, content = asyncio.run(execute())

    assert seed.response.response["seeded"] is False
    assert "File has not been read yet" in result.result
    assert content == "observed\n"


def test_sdk_control_request_handler_stops_tasks_from_store():
    client = AgentSDKClient(session_factory=_session_factory)
    spec = AgentSpec.from_overrides(
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
    )
    task = asyncio.run(client.persistence.tasks.create_task(spec, title="Long task", input="work"))
    task = asyncio.run(client.persistence.tasks.set_task_status(task.task_id, TaskStatus.RUNNING))
    session = client.create_sdk_session(
        SDKOptions(
            session_id="control-task-session",
            tenant_id="tenant",
            user_id="user",
            agent_id="agent",
        )
    )

    response = asyncio.run(
        session.handle_control_request(
            SDKControlRequest(
                request_id="stop-task",
                request=SDKControlStopTaskRequest(task_id=task.task_id.replace("task_", "", 1)[:12]),
            )
        )
    )
    stored = asyncio.run(client.persistence.tasks.load_task(task.task_id))

    assert isinstance(response.response, SDKControlSuccessResponse)
    assert response.response.response["stopped"] is True
    assert response.response.response["task"]["task_id"] == task.task_id
    assert response.response.response["task"]["status"] == "canceled"
    assert stored.status == TaskStatus.CANCELED


async def _collect(messages):
    return [message async for message in messages]
