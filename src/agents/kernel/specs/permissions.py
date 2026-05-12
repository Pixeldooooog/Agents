from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class ToolPermissionRule:
    source: str
    behavior: str
    tool: str
    content: str = ""

    def to_dict(self) -> dict:
        payload = {
            "source": self.source,
            "behavior": self.behavior,
            "tool": self.tool,
        }
        if self.content:
            payload["content"] = self.content
        return payload


@dataclass(frozen=True)
class ToolPermissionSpec:
    mode: str = "auto"
    allowed_tools: Optional[list[str]] = None
    denied_tools: list[str] = field(default_factory=list)
    approval_required_tools: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: dict | None) -> "ToolPermissionSpec":
        if not payload:
            return cls()
        allowed = payload.get("allowed_tools")
        return cls(
            mode=str(payload.get("mode") or "auto"),
            allowed_tools=list(allowed) if allowed is not None else None,
            denied_tools=list(payload.get("denied_tools") or []),
            approval_required_tools=list(payload.get("approval_required_tools") or []),
        )

    def normalized_mode(self) -> str:
        mode = (self.mode or "auto").strip().lower()
        if mode in {"auto", "ask", "deny"}:
            return mode
        return "auto"

    def rules(self, source: str = "agent_spec") -> list[ToolPermissionRule]:
        rules: list[ToolPermissionRule] = []
        mode = self.normalized_mode()
        if mode in {"ask", "deny"}:
            rules.append(ToolPermissionRule(source=source, behavior="ask" if mode == "ask" else "deny", tool="*", content="mode:%s" % mode))
        if self.allowed_tools is not None:
            rules.extend(ToolPermissionRule(source=source, behavior="allow", tool=str(tool)) for tool in self.allowed_tools)
        rules.extend(ToolPermissionRule(source=source, behavior="deny", tool=str(tool)) for tool in self.denied_tools)
        rules.extend(ToolPermissionRule(source=source, behavior="ask", tool=str(tool)) for tool in self.approval_required_tools)
        return rules

    def rules_by_source(self, source: str = "agent_spec") -> dict[str, dict[str, list[str]]]:
        grouped: dict[str, dict[str, list[str]]] = {}
        for rule in self.rules(source=source):
            grouped.setdefault(rule.source, {}).setdefault(rule.behavior, []).append(rule.tool)
        return grouped

    def to_dict(self) -> dict:
        payload = {
            "mode": self.normalized_mode(),
            "denied_tools": list(self.denied_tools),
            "approval_required_tools": list(self.approval_required_tools),
        }
        if self.allowed_tools is not None:
            payload["allowed_tools"] = list(self.allowed_tools)
        return payload
