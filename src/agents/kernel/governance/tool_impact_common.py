from __future__ import annotations

import json
import shlex
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse


MAX_PREVIEW_CHARS = 4000


@dataclass(frozen=True)
class ToolImpact:
    tool_name: str
    risk: str
    operations: list[str] = field(default_factory=list)
    paths: list[str] = field(default_factory=list)
    commands: list[str] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)
    writes_files: bool = False
    requires_network: bool = False
    external_disclosure: bool = False
    query: str = ""
    cost_estimate: dict[str, Any] = field(default_factory=dict)
    diff_preview: str = ""
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "tool_name": self.tool_name,
            "risk": self.risk,
            "operations": list(self.operations),
            "paths": list(self.paths),
            "commands": list(self.commands),
            "domains": list(self.domains),
            "writes_files": self.writes_files,
            "requires_network": self.requires_network,
            "external_disclosure": self.external_disclosure,
            "query": self.query,
            "cost_estimate": dict(self.cost_estimate),
        }
        if self.diff_preview:
            payload["diff_preview"] = self.diff_preview
        if self.summary:
            payload["summary"] = self.summary
        return payload


def _impact(
    tool_name: str,
    risk: str,
    *,
    operations: list[str] | None = None,
    paths: list[str] | None = None,
    commands: list[str] | None = None,
    domains: list[str] | None = None,
    writes_files: bool = False,
    requires_network: bool = False,
    external_disclosure: bool = False,
    query: str = "",
    cost_estimate: dict[str, Any] | None = None,
    diff_preview: str = "",
    summary: str = "",
) -> ToolImpact:
    return ToolImpact(
        tool_name=tool_name,
        risk=risk,
        operations=_unique(operations or []),
        paths=_unique(item for item in (paths or []) if item),
        commands=_unique(item for item in (commands or []) if item),
        domains=_unique(item for item in (domains or []) if item),
        writes_files=writes_files,
        requires_network=requires_network,
        external_disclosure=external_disclosure,
        query=query,
        cost_estimate=dict(cost_estimate or {}),
        diff_preview=diff_preview,
        summary=summary,
    )


def _web_cost_estimate(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name == "web.search":
        depth = _string(arguments.get("search_depth") or "basic")
        raw_cost = 1 if arguments.get("include_raw_content") else 0
        return {
            "provider": "tavily",
            "estimated_credits": (2 if depth == "advanced" else 1) + raw_cost,
            "basis": depth,
        }
    if name == "web.extract":
        urls = arguments.get("urls") or []
        depth = _string(arguments.get("extract_depth") or "basic")
        per_url = 2 if depth == "advanced" else 1
        return {"provider": "tavily", "estimated_credits": per_url * max(1, len(urls)), "basis": depth}
    if name == "web.map":
        return {"provider": "tavily", "estimated_credits": 1, "basis": "map"}
    return {}


def _web_summary(name: str, query: str, domains: list[str]) -> str:
    if name == "web.search":
        return "search web for %s" % query if query else "search web"
    if domains:
        return "%s %s" % (name, ", ".join(_unique(domains)[:3]))
    return name


def _browser_paths(name: str, arguments: dict[str, Any]) -> list[str]:
    if name == "browser.open":
        return [_string(arguments.get("output_path") or "artifact://run/{run_id}/downloads/browser-open.html")]
    if name == "browser.download":
        return [_string(arguments.get("path") or "artifact://run/{run_id}/downloads/download.bin")]
    return []


def _domain(url: str) -> str:
    parsed = urlparse(url)
    return parsed.netloc.lower()


def _program_summary(command: str) -> str:
    try:
        parts = shlex.split(command)
    except ValueError:
        return command
    return "run %s" % parts[0] if parts else command


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _truncate(value: str, limit: int = MAX_PREVIEW_CHARS) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return text[:limit] + "\n[truncated]"


def _json_preview(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        return str(value or "")


def _string(value: Any) -> str:
    return str(value or "")


def _unique(values) -> list[str]:
    result: list[str] = []
    seen = set()
    for value in values:
        text = str(value or "")
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result
