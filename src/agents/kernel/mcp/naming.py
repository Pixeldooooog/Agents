from __future__ import annotations

import re
from typing import Dict


_MCP_UNSAFE_NAME_RE = re.compile(r"[^a-zA-Z0-9_-]")
ALLOWED_IDE_TOOL_NAMES = {"mcp__ide__executeCode", "mcp__ide__getDiagnostics"}


def normalize_mcp_name(name: str) -> str:
    value = str(name or "")
    normalized = _MCP_UNSAFE_NAME_RE.sub("_", value)
    if value.startswith("claude.ai "):
        normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized or "unnamed"


def build_mcp_tool_name(server_name: str, tool_name: str) -> str:
    return "mcp__%s__%s" % (normalize_mcp_name(server_name), normalize_mcp_name(tool_name))


def is_included_mcp_tool(name: str) -> bool:
    return not name.startswith("mcp__ide__") or name in ALLOWED_IDE_TOOL_NAMES


def mcp_info_from_name(name: str) -> Dict[str, str] | None:
    value = str(name or "")
    if not value.startswith("mcp__"):
        return None
    parts = value[len("mcp__") :].split("__", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        return None
    return {"server": parts[0], "tool": parts[1]}


def mcp_location(transport: str, url: str) -> str:
    transport_value = str(transport or "stdio")
    url_value = str(url or "").strip()
    return "%s at %s" % (transport_value, url_value) if url_value else transport_value
