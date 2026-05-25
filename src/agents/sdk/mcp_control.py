from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from dataclasses import replace
from typing import Any

from agents.kernel.capabilities.tools import normalize_mcp_name

SDKServerEnabled = Callable[[str], Awaitable[bool]]
MCPStatusLookup = Callable[[str], Awaitable[str | None]]


def active_session_for_options(active_sessions: dict[str, Any], options: Any) -> Any | None:
    keys = [str(getattr(options, "session_id", "") or "")]
    metadata = getattr(options, "metadata", {}) or {}
    run_id = str(metadata.get("run_id") or metadata.get("runId") or "")
    if run_id:
        keys.append(run_id)
    for key in keys:
        if not key:
            continue
        session = active_sessions.get(key)
        if session is not None:
            return session
    return None


async def reconnect_mcp_server(
    server_name: str,
    *,
    active_session: Any | None,
    sdk_handler_registered: bool,
    sdk_server_enabled: SDKServerEnabled,
    status_for_server: MCPStatusLookup,
) -> dict[str, Any]:
    resolved_name = str(server_name or "").strip()
    if not resolved_name:
        raise ValueError("MCP server name is required")
    if sdk_handler_registered:
        if not await sdk_server_enabled(resolved_name):
            raise RuntimeError("SDK MCP server is disabled: %s" % resolved_name)
        return {"serverName": resolved_name, "status": "connected", "reconnected": True}
    if active_session is not None:
        result = await reconnect_active_session_mcp(active_session, resolved_name)
        return _reconnect_payload(resolved_name, result)
    status = await status_for_server(resolved_name)
    if status is None:
        raise KeyError("MCP server not found: %s" % resolved_name)
    return {
        "serverName": resolved_name,
        "status": status,
        "reconnected": False,
        "reason": "no active SDK turn is attached to this control handler",
    }


async def reconnect_active_session_mcp(session: Any, server_name: str) -> dict[str, Any]:
    from agents.kernel.capabilities.tools.builtin.mcp_management import mcp_reconnect

    context = getattr(session, "tool_context", None)
    runtime = getattr(session, "runtime", None)
    registry = getattr(runtime, "tools", None)
    if context is None or registry is None:
        raise RuntimeError("active SDK session does not expose MCP reload context")
    result = await mcp_reconnect(context, registry, name=server_name)
    _replace_runtime_mcp_tools(runtime, result)
    return result


def _replace_runtime_mcp_tools(runtime: Any, result: dict[str, Any]) -> None:
    config = getattr(runtime, "config", None)
    if config is None:
        return
    removed = {str(name) for name in result.get("removed_tools", []) or []}
    loaded = [str(name) for name in result.get("loaded_tools", []) or []]
    retained = [tool for tool in list(getattr(config, "enabled_tools", []) or []) if tool not in removed]
    runtime.config = replace(config, enabled_tools=_merge_unique_strings(retained, loaded))


def _reconnect_payload(server_name: str, result: dict[str, Any]) -> dict[str, Any]:
    provider_names = {
        str(provider.get("name") or "")
        for provider in result.get("providers", []) or []
        if isinstance(provider, dict)
    }
    payload: dict[str, Any] = {
        "serverName": server_name,
        "status": "connected" if server_name in provider_names else "disconnected",
        "reconnected": server_name in provider_names,
        "loadedTools": _mcp_tools_for_server(result.get("loaded_tools", []) or [], server_name),
        "removedTools": list(result.get("removed_tools", []) or []),
    }
    if server_name not in provider_names:
        payload["reason"] = "server was not loaded after reconnect"
    return payload


def _mcp_tools_for_server(tools: Iterable[Any], server_name: str) -> list[str]:
    prefix = "mcp__%s__" % normalize_mcp_name(server_name)
    return sorted(str(tool) for tool in tools if str(tool or "").startswith(prefix))


def _merge_unique_strings(*groups: Iterable[Any]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for item in group:
            value = str(item or "")
            if not value or value in seen:
                continue
            seen.add(value)
            merged.append(value)
    return merged
