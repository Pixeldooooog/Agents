from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from agents.kernel.hooks.base import AgentHooks, ToolHookDenied
from agents.kernel.governance.tool_rules import tool_rule_matches_call
from agents.kernel.schema import Message, ModelResponse, ToolCall, ToolResult


HOOK_EVENTS = ["before_request", "after_response", "pre_tool_use", "post_tool_use"]
HOOK_ACTIONS = ["append_system", "append_user", "record", "deny_tool"]


@dataclass
class HookRecord:
    hook_id: str
    event: str
    name: str
    action: str
    content: str = ""
    enabled: bool = True
    metadata: dict[str, str] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    last_run_at: float = 0.0
    run_count: int = 0

    @property
    def short_id(self) -> str:
        return self.hook_id.replace("hook_", "", 1)[:12]

    def to_dict(self) -> dict[str, Any]:
        return {
            "hook_id": self.hook_id,
            "short_id": self.short_id,
            "event": self.event,
            "name": self.name,
            "action": self.action,
            "content": self.content,
            "enabled": self.enabled,
            "tool": str(self.metadata.get("tool") or self.metadata.get("tool_name") or ""),
            "metadata": dict(self.metadata),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_run_at": self.last_run_at,
            "run_count": self.run_count,
        }


class SessionHookRegistry:
    def __init__(self):
        self._hooks: dict[str, HookRecord] = {}

    def add(
        self,
        *,
        event: str,
        name: str,
        action: str,
        content: str = "",
        enabled: bool = True,
        tool: str = "",
        metadata: dict[str, str] | None = None,
    ) -> HookRecord:
        hook_metadata = _string_metadata(metadata)
        tool_pattern = str(tool or "").strip()
        if tool_pattern:
            hook_metadata["tool"] = tool_pattern
        record = HookRecord(
            hook_id="hook_%s" % uuid4().hex[:12],
            event=_event(event),
            name=_required_text(name, "name"),
            action=_action(action),
            content=str(content or ""),
            enabled=bool(enabled),
            metadata=hook_metadata,
        )
        self._hooks[record.hook_id] = record
        return record

    def replace_all(self, records: list[HookRecord]) -> None:
        self._hooks = {record.hook_id: record for record in records}

    def list(self, event: str = "", enabled: bool | None = None, limit: int = 50) -> list[HookRecord]:
        records = sorted(self._hooks.values(), key=lambda item: item.updated_at, reverse=True)
        if event:
            wanted = _event(event)
            records = [record for record in records if record.event == wanted]
        if enabled is not None:
            records = [record for record in records if record.enabled is bool(enabled)]
        limit = max(1, min(int(limit or 50), 100))
        return records[:limit]

    def delete(self, hook_id: str) -> HookRecord:
        record = self.resolve(hook_id)
        return self._hooks.pop(record.hook_id)

    def resolve(self, hook_id: str) -> HookRecord:
        target = _required_text(hook_id, "hook_id")
        if target in self._hooks:
            return self._hooks[target]
        matches = [record for record in self._hooks.values() if record.short_id.startswith(target)]
        if not matches:
            raise KeyError("hook not found: %s" % target)
        if len(matches) > 1:
            raise ValueError("hook id is ambiguous: %s" % target)
        return matches[0]

    def mark_ran(self, record: HookRecord) -> None:
        record.last_run_at = time.time()
        record.run_count += 1
        record.updated_at = time.time()


class SessionStateHooks(AgentHooks):
    def __init__(self, registry: SessionHookRegistry, store: Any | None = None, workspace: Any | None = None):
        self.registry = registry
        self.store = store
        self.workspace = workspace

    async def before_request(self, messages: list[Message]) -> list[Message]:
        working = list(messages)
        for record in self.registry.list(event="before_request", enabled=True, limit=100):
            if record.action == "append_system":
                working = _append_once_after_system(working, "system", record.content)
                await self._mark_ran(record)
            elif record.action == "append_user":
                working.append(Message.from_text("user", record.content))
                await self._mark_ran(record)
        return working

    async def after_response(self, response: ModelResponse) -> ModelResponse:
        for record in self.registry.list(event="after_response", enabled=True, limit=100):
            if record.action == "record":
                await self._mark_ran(record)
        return response

    async def before_tool_use(self, call: ToolCall) -> ToolCall:
        for record in self.registry.list(event="pre_tool_use", enabled=True, limit=100):
            if not _hook_matches_tool(record, call):
                continue
            if record.action == "record":
                await self._mark_ran(record)
            elif record.action == "deny_tool":
                await self._mark_ran(record)
                raise ToolHookDenied(call.name, record.content or "tool denied by hook: %s" % record.name)
        return call

    async def after_tool_use(self, call: ToolCall, result: ToolResult) -> ToolResult:
        for record in self.registry.list(event="post_tool_use", enabled=True, limit=100):
            if record.action == "record" and _hook_matches_tool(record, call):
                await self._mark_ran(record)
        return result

    async def _mark_ran(self, record: HookRecord) -> None:
        self.registry.mark_ran(record)
        if self.store is not None and self.workspace is not None:
            await self.store.save(
                record,
                self.workspace.tenant_id,
                user_id=self.workspace.user_id,
                agent_id=self.workspace.agent_id,
                workspace_id=self.workspace.workspace_id,
            )


def _append_once_after_system(messages: list[Message], role: str, text: str) -> list[Message]:
    content = str(text or "").strip()
    if not content:
        return messages
    if any(message.role == role and message.content_text() == content for message in messages):
        return messages
    working: list[Message] = []
    inserted = False
    for message in messages:
        working.append(message)
        if not inserted and message.role == "system":
            working.append(Message.from_text(role, content))
            inserted = True
    if not inserted:
        working.insert(0, Message.from_text(role, content))
    return working


def _hook_matches_tool(record: HookRecord, call: ToolCall) -> bool:
    pattern = str(record.metadata.get("tool") or record.metadata.get("tool_name") or "*").strip()
    return tool_rule_matches_call(pattern or "*", call, shell_parse_error_matches=True)


def _event(value: str) -> str:
    normalized = str(value or "").strip().replace("-", "_").lower()
    aliases = {
        "beforerequest": "before_request",
        "before_request": "before_request",
        "afterresponse": "after_response",
        "after_response": "after_response",
        "pretooluse": "pre_tool_use",
        "pre_tool_use": "pre_tool_use",
        "pretool": "pre_tool_use",
        "posttooluse": "post_tool_use",
        "post_tool_use": "post_tool_use",
        "posttool": "post_tool_use",
    }
    event = aliases.get(normalized, normalized)
    if event not in HOOK_EVENTS:
        raise ValueError("unknown hook event: %s" % value)
    return event


def _action(value: str) -> str:
    action = str(value or "").strip().replace("-", "_").lower()
    if action not in HOOK_ACTIONS:
        raise ValueError("unknown hook action: %s" % value)
    return action


def _required_text(value: Any, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError("%s is required" % name)
    return text


def _string_metadata(metadata: dict[str, Any] | None) -> dict[str, str]:
    return {str(key): str(value) for key, value in dict(metadata or {}).items()}
