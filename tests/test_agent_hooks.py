# !/usr/bin/env python
# -*- coding: utf-8 -*-
# =====================================================
# @File   ：test_agent_hooks.py
# @Date   ：2026/04/27 00:00
# @Author ：Zegen
#
# 2026/04/27   Create
# =====================================================

import asyncio

import pytest

from agents.kernel.hooks import (
    AgentHooks,
    ApprovalHooks,
    CompositeHooks,
    IntentGuide,
    IntentGuidanceHooks,
    SessionHookRegistry,
    SessionStateHooks,
    SystemPromptGuidanceHooks,
    ThinkingHooks,
    ToolApprovalError,
    ToolHookDenied,
    hooks_from_settings,
)
from agents.kernel.context.workspace import WorkspaceContext
from agents.kernel.hooks import InMemoryHookStore
from agents.kernel.capabilities.tools.registry import ToolRegistry
from agents.kernel.runtime.turns.tools import ToolOrchestrator
from agents.kernel.schema import Message, ModelResponse, ToolCall


class TestHooksFactory:
    def test_returns_default_hooks_when_no_config(self):
        settings = _MockSettings(GUIDED_TOOLS="")
        hooks = hooks_from_settings(settings)
        assert isinstance(hooks, AgentHooks)
        assert not isinstance(hooks, CompositeHooks)

    def test_creates_intent_guidance_from_config(self):
        settings = _MockSettings(GUIDED_TOOLS="weather:天气,温度")
        hooks = hooks_from_settings(settings)

        assert isinstance(hooks, IntentGuidanceHooks)
        messages = [Message.from_text("user", "今天天气怎么样？")]
        result = asyncio.run(hooks.before_request(messages))
        assert len(result) == 2
        assert "weather" in result[1].content_text()

    def test_single_guidance_hooks_for_multiple_tools(self):
        settings = _MockSettings(GUIDED_TOOLS="weather:天气;search:搜索")
        hooks = hooks_from_settings(settings)

        assert isinstance(hooks, IntentGuidanceHooks)
        # 验证两个工具规则都解析成功
        messages = [Message.from_text("user", "搜索一下")]
        result = asyncio.run(hooks.before_request(messages))
        assert len(result) == 2
        assert "search" in result[1].content_text()


class _MockSettings:
    def __init__(self, GUIDED_TOOLS: str = ""):
        self.agent = _MockAgentSettings(GUIDED_TOOLS=GUIDED_TOOLS)


class _MockAgentSettings:
    def __init__(self, GUIDED_TOOLS: str = ""):
        self.GUIDED_TOOLS = GUIDED_TOOLS


class TestIntentGuidanceHooks:
    def test_inserts_guidance_when_keyword_matches(self):
        hooks = IntentGuidanceHooks([
            IntentGuide(keywords=["天气"], tool_name="weather", prompt="你可以使用 weather 工具。"),
        ])
        messages = [Message.from_text("user", "今天天气怎么样？")]

        result = asyncio.run(hooks.before_request(messages))

        assert len(result) == 2
        assert result[1].content_text() == "你可以使用 weather 工具。"

    def test_no_insert_when_no_match(self):
        hooks = IntentGuidanceHooks([
            IntentGuide(keywords=["天气"], tool_name="weather", prompt="你可以使用 weather 工具。"),
        ])
        messages = [Message.from_text("user", "你好")]

        result = asyncio.run(hooks.before_request(messages))

        assert len(result) == 1

    def test_no_duplicate_guidance(self):
        hooks = IntentGuidanceHooks([
            IntentGuide(keywords=["天气"], tool_name="weather", prompt="你可以使用 weather 工具。"),
        ])
        messages = [
            Message.from_text("user", "今天天气怎么样？"),
            Message.from_text("user", "你可以使用 weather 工具。"),
        ]

        result = asyncio.run(hooks.before_request(messages))

        assert len(result) == 2


class TestSystemPromptGuidanceHooks:
    def test_appends_guidance_after_existing_system(self):
        async def provider(messages):
            return "请使用中文回答。"

        hooks = SystemPromptGuidanceHooks(provider)
        messages = [
            Message.from_text("system", "You are a helpful assistant."),
            Message.from_text("user", "hi"),
        ]

        result = asyncio.run(hooks.before_request(messages))

        assert len(result) == 3
        assert result[1].role == "system"
        assert result[1].content_text() == "请使用中文回答。"

    def test_inserts_system_at_front_when_none_exists(self):
        async def provider(messages):
            return "Be concise."

        hooks = SystemPromptGuidanceHooks(provider)
        messages = [Message.from_text("user", "hi")]

        result = asyncio.run(hooks.before_request(messages))

        assert result[0].role == "system"
        assert result[0].content_text() == "Be concise."

    def test_skips_duplicate_guidance(self):
        async def provider(messages):
            return "Same guidance."

        hooks = SystemPromptGuidanceHooks(provider)
        messages = [Message.from_text("user", "hi")]

        result1 = asyncio.run(hooks.before_request(messages))
        result2 = asyncio.run(hooks.before_request(result1))

        assert len(result2) == len(result1)


class TestSessionStateHooks:
    def test_session_hook_registry_appends_request_guidance(self):
        registry = SessionHookRegistry()
        hook = registry.add(
            event="before_request",
            name="coding-style",
            action="append_system",
            content="Prefer concise diffs.",
        )
        hooks = SessionStateHooks(registry)
        messages = [
            Message.from_text("system", "Base prompt."),
            Message.from_text("user", "edit code"),
        ]

        result = asyncio.run(hooks.before_request(messages))

        assert [message.role for message in result] == ["system", "system", "user"]
        assert result[1].content_text() == "Prefer concise diffs."
        assert hook.run_count == 1
        assert registry.list()[0].short_id == hook.short_id

        deleted = registry.delete(hook.short_id)
        assert deleted.hook_id == hook.hook_id
        assert registry.list() == []

    def test_pre_tool_hook_can_block_matching_tool(self):
        registry = SessionHookRegistry()
        hook = registry.add(
            event="pre_tool_use",
            name="block-echo",
            action="deny_tool",
            content="echo blocked",
            tool="echo",
        )
        hooks = SessionStateHooks(registry)

        with pytest.raises(ToolHookDenied) as exc_info:
            asyncio.run(hooks.before_tool_use(ToolCall(id="1", name="echo", arguments={})))

        assert exc_info.value.reason == "echo blocked"
        assert hook.run_count == 1

    def test_tool_orchestrator_runs_pre_and_post_tool_hooks(self):
        hook_registry = SessionHookRegistry()
        pre = hook_registry.add(event="pre_tool_use", name="pre", action="record", tool="echo")
        post = hook_registry.add(event="post_tool_use", name="post", action="record", tool="echo")
        tools = ToolRegistry()
        tools.register("echo", "Echo", {}, lambda text="": text)
        orchestrator = ToolOrchestrator(tools, SessionStateHooks(hook_registry))

        batch = asyncio.run(orchestrator.execute([ToolCall(id="1", name="echo", arguments={"text": "hi"})]))

        assert batch.results[0].content == "hi"
        assert pre.run_count == 1
        assert post.run_count == 1

    def test_session_state_hooks_persist_run_counts_to_store(self, tmp_path):
        workspace = WorkspaceContext(
            tenant_id="tenant",
            user_id="user",
            agent_id="agent",
            workspace_id="workspace",
            root=tmp_path,
            path=tmp_path,
        )
        store = InMemoryHookStore()
        registry = SessionHookRegistry()
        hook = registry.add(event="before_request", name="style", action="append_system", content="Prefer small patches.")
        hooks = SessionStateHooks(registry, store=store, workspace=workspace)

        asyncio.run(hooks.before_request([Message.from_text("user", "edit")]))
        stored = asyncio.run(store.list_for_scope("tenant", user_id="user", agent_id="agent", workspace_id="workspace"))

        assert hook.run_count == 1
        assert stored[0].hook_id == hook.hook_id
        assert stored[0].run_count == 1


class TestThinkingHooks:
    def test_extracts_thinking_from_raw(self):
        captured = []
        hooks = ThinkingHooks(on_thinking=captured.append)
        response = ModelResponse(
            message=Message.from_text("assistant", "answer"),
            raw={"reasoning_content": "Let me think..."},
        )

        result = asyncio.run(hooks.after_response(response))

        assert captured == ["Let me think..."]
        assert result.message.content_text() == "answer"

    def test_no_thinking_when_raw_empty(self):
        captured = []
        hooks = ThinkingHooks(on_thinking=captured.append)
        response = ModelResponse(message=Message.from_text("assistant", "answer"))

        asyncio.run(hooks.after_response(response))

        assert captured == []


class TestApprovalHooks:
    def test_allows_approved_tools(self):
        hooks = ApprovalHooks(should_approve=lambda name, args: name != "dangerous")
        response = ModelResponse(
            message=Message.from_text(
                "assistant",
                "",
                tool_calls=[ToolCall(id="1", name="safe", arguments={})],
            )
        )

        result = asyncio.run(hooks.after_response(response))

        assert result.message.tool_calls[0].name == "safe"

    def test_rejects_unapproved_tools(self):
        hooks = ApprovalHooks(should_approve=lambda name, args: name != "dangerous")
        response = ModelResponse(
            message=Message.from_text(
                "assistant",
                "",
                tool_calls=[ToolCall(id="1", name="dangerous", arguments={})],
            )
        )

        with pytest.raises(ToolApprovalError) as exc_info:
            asyncio.run(hooks.after_response(response))

        assert exc_info.value.tool_name == "dangerous"


class TestCompositeHooks:
    def test_chains_before_request(self):
        class AddSystemHook(AgentHooks):
            async def before_request(self, messages):
                return [Message.from_text("system", "sys")] + messages

        class AddUserHook(AgentHooks):
            async def before_request(self, messages):
                return messages + [Message.from_text("user", "extra")]

        composite = CompositeHooks([AddSystemHook(), AddUserHook()])
        messages = [Message.from_text("user", "hi")]

        result = asyncio.run(composite.before_request(messages))

        assert [m.role for m in result] == ["system", "user", "user"]

    def test_uses_last_hook_for_format_tool_result(self):
        class UppercaseHook(AgentHooks):
            def format_tool_result(self, result):
                return Message.from_text("tool", result.content.upper())

        composite = CompositeHooks([AgentHooks(), UppercaseHook()])
        from agents.kernel.schema import ToolResult

        result = composite.format_tool_result(ToolResult(tool_call_id="1", name="echo", content="hi"))

        assert result.content_text() == "HI"

    def test_first_on_error_recovery_wins(self):
        class RecoveryHook(AgentHooks):
            async def on_error(self, error, messages):
                from agents.kernel.runtime import AgentResult
                return AgentResult(content="recovered", messages=messages)

        composite = CompositeHooks([AgentHooks(), RecoveryHook()])

        result = asyncio.run(composite.on_error(ValueError("boom"), []))

        assert result is not None
        assert result.content == "recovered"
