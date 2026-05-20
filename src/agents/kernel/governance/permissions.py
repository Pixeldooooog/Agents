from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Iterable, Protocol, Union

from agents.kernel.schema import ToolCall
from agents.kernel.governance.tool_rules import find_matching_tool_rule, normalize_tool_name


@dataclass(frozen=True)
class ToolPermissionDecision:
    allowed: bool
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    requires_approval: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "allowed": self.allowed,
            "requires_approval": self.requires_approval,
        }
        if self.reason:
            payload["reason"] = self.reason
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return payload


class ToolPermissionPolicy(Protocol):
    async def authorize(self, call: ToolCall) -> ToolPermissionDecision:
        raise NotImplementedError()


class AllowAllToolPermissionPolicy:
    async def authorize(self, call: ToolCall) -> ToolPermissionDecision:
        return ToolPermissionDecision(allowed=True)


class DenyAllToolPermissionPolicy:
    async def authorize(self, call: ToolCall) -> ToolPermissionDecision:
        return ToolPermissionDecision(allowed=False, reason="tool execution disabled by policy")


class StaticToolPermissionPolicy:
    def __init__(
        self,
        allowed_tools: Iterable[str] | None = None,
        denied_tools: Iterable[str] | None = None,
        approval_required_tools: Iterable[str] | None = None,
        require_approval_for_all: bool = False,
    ):
        self.restrict_allowed_tools = allowed_tools is not None
        self.allowed_tools = _unique(allowed_tools or [])
        self.denied_tools = _unique(denied_tools or [])
        self.approval_required_tools = _unique(approval_required_tools or [])
        self.require_approval_for_all = require_approval_for_all

    async def authorize(self, call: ToolCall) -> ToolPermissionDecision:
        name = normalize_tool_name(call.name)
        config_read = name == "config.manage" and "value" not in dict(call.arguments or {})
        user_question = name == "user.ask"
        denied_rule = find_matching_tool_rule(self.denied_tools, call, shell_parse_error_matches=True)
        if denied_rule is not None:
            return ToolPermissionDecision(
                allowed=False,
                reason="tool denied by policy",
                metadata={"source": "agent_spec", "rule": "deny", "tool": call.name, "matched_rule": denied_rule},
            )
        if config_read:
            return ToolPermissionDecision(
                allowed=True,
                metadata={"source": "tool_policy", "rule": "allow", "tool": call.name, "operation": "config_read"},
            )
        allowed_rule = find_matching_tool_rule(self.allowed_tools, call, shell_parse_error_matches=False)
        if self.restrict_allowed_tools and allowed_rule is None:
            return ToolPermissionDecision(
                allowed=False,
                reason="tool is not in the allowed tool set",
                metadata={"source": "agent_spec", "rule": "allowlist", "tool": call.name},
            )
        approval_rule = find_matching_tool_rule(self.approval_required_tools, call, shell_parse_error_matches=True)
        config_write_requires_approval = name == "config.manage" and "value" in dict(call.arguments or {}) and allowed_rule is None
        user_question_requires_approval = user_question and allowed_rule is None
        worktree_remove_requires_approval = (
            name == "worktree.exit" and str(dict(call.arguments or {}).get("action") or "").strip() == "remove" and allowed_rule is None
        )
        if (
            self.require_approval_for_all
            or approval_rule is not None
            or config_write_requires_approval
            or user_question_requires_approval
            or worktree_remove_requires_approval
        ):
            rule = (
                "user_interaction"
                if user_question_requires_approval
                else "config:set"
                if config_write_requires_approval
                else "worktree:remove"
                if worktree_remove_requires_approval
                else "mode:ask"
                if self.require_approval_for_all
                else "ask"
            )
            return ToolPermissionDecision(
                allowed=False,
                reason="tool requires user input" if user_question_requires_approval else "tool requires user approval",
                requires_approval=True,
                metadata={
                    "permission": "user_interaction" if user_question_requires_approval else "ask",
                    "source": "agent_spec",
                    "rule": rule,
                    "tool": call.name,
                    **({"matched_rule": approval_rule} if approval_rule is not None else {}),
                },
            )
        metadata = {
            "source": "agent_spec" if self.restrict_allowed_tools else "policy_default",
            "rule": "allow",
            "tool": call.name,
            **({"matched_rule": allowed_rule} if allowed_rule is not None else {}),
        }
        return ToolPermissionDecision(allowed=True, metadata=metadata)


PermissionResult = Union[bool, ToolPermissionDecision]
PermissionHandler = Callable[[ToolCall], Union[PermissionResult, Awaitable[PermissionResult]]]


class CallbackToolPermissionPolicy:
    def __init__(self, handler: PermissionHandler):
        self.handler = handler

    async def authorize(self, call: ToolCall) -> ToolPermissionDecision:
        result = self.handler(call)
        if inspect.isawaitable(result):
            result = await result
        if isinstance(result, ToolPermissionDecision):
            return result
        return ToolPermissionDecision(allowed=bool(result))


def _unique(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        value = str(item)
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
