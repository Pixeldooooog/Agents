from __future__ import annotations

import asyncio
import inspect
import time
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, Mapping

import httpx

from agents.kernel.mcp.oauth import (
    MCPOAuthCallbackListener,
    MCPOAuthProviderError,
    MCPOAuthStateMismatchError,
    build_mcp_oauth_redirect_uri,
    find_available_mcp_oauth_callback_port,
)
from agents.kernel.mcp.oauth_flow import (
    MCPOAuthPendingAuthorization,
    MCPOAuthFlowError,
    complete_mcp_oauth_authorization,
    start_mcp_oauth_authorization,
)
from agents.kernel.mcp.oauth_tokens import MCPOAuthTokenRequestError, generate_pkce_code_verifier


@dataclass(frozen=True)
class MCPOAuthLoopbackWaiter:
    server_name: str
    listener: Any
    task: asyncio.Task[Any]


async def authenticate_mcp_oauth_server(
    context: Any,
    server: Any,
    arguments: Mapping[str, Any] | None = None,
    *,
    http_client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    args = dict(arguments or {})
    callback_url = str(args.get("callback_url") or args.get("callbackUrl") or "").strip()
    flows = _pending_flows(context)
    server_name = str(getattr(server, "name", "") or "default")
    if callback_url:
        await _cancel_mcp_oauth_waiter(context, server_name)
        pending = flows.get(server_name)
        if pending is None:
            return {
                "status": "error",
                "server": server_name,
                "transport": str(getattr(server, "transport", "") or ""),
                "url": str(getattr(server, "url", "") or ""),
                "message": "No pending OAuth authorization exists for %s. Start authentication first." % server_name,
            }
        try:
            payload = await _complete_mcp_oauth_authorization_for_context(
                context,
                pending,
                callback_url,
                http_client=http_client,
            )
        except (MCPOAuthFlowError, MCPOAuthProviderError, MCPOAuthStateMismatchError, MCPOAuthTokenRequestError) as exc:
            return {
                "status": "error",
                "server": server_name,
                "transport": str(getattr(server, "transport", "") or ""),
                "url": str(getattr(server, "url", "") or ""),
                "message": str(exc),
            }
        flows.pop(server_name, None)
        return payload

    existing = flows.get(server_name)
    if existing is not None and not existing.is_expired():
        waiter = _oauth_waiters(context).get(server_name)
        return _authorization_started_payload(
            server,
            existing,
            callback_listening=waiter is not None,
            browser_opened=False,
            reused=True,
        )
    await _cancel_mcp_oauth_waiter(context, server_name)
    flows.pop(server_name, None)

    wait_for_callback = bool(args.get("wait_for_callback", args.get("waitForCallback", True)))
    open_browser = bool(args.get("open_browser", args.get("openBrowser", True)))
    state_value = generate_pkce_code_verifier()
    listener = None
    try:
        if wait_for_callback:
            listener = await _start_loopback_listener(context, state_value)
            redirect_uri = str(listener.redirect_uri)
        else:
            port = find_available_mcp_oauth_callback_port()
            redirect_uri = build_mcp_oauth_redirect_uri(port)
        pending = await start_mcp_oauth_authorization(
            server_name,
            str(getattr(server, "url", "") or ""),
            redirect_uri=redirect_uri,
            state=state_value,
            http_client=http_client,
        )
    except Exception as exc:  # noqa: BLE001 - surfaced as model-visible auth status.
        if listener is not None:
            with suppress(Exception):
                await listener.close()
        return {
            "status": "error",
            "server": server_name,
            "transport": str(getattr(server, "transport", "") or ""),
            "url": str(getattr(server, "url", "") or ""),
            "message": "Failed to start OAuth flow for %s: %s" % (server_name, exc),
        }
    flows[server_name] = pending
    if listener is not None:
        _oauth_waiters(context)[server_name] = MCPOAuthLoopbackWaiter(
            server_name=server_name,
            listener=listener,
            task=asyncio.create_task(
                _wait_for_loopback_callback(context, server, pending, listener, http_client=http_client)
            ),
        )
    browser_opened = await _maybe_open_authorization_url(context, pending.authorization_url, enabled=open_browser)
    return _authorization_started_payload(
        server,
        pending,
        callback_listening=listener is not None,
        browser_opened=browser_opened,
        reused=False,
    )


async def close_mcp_oauth_waiters(context: Any) -> None:
    first_error: Exception | None = None
    for server_name in list(_oauth_waiters(context)):
        try:
            await _cancel_mcp_oauth_waiter(context, server_name)
        except Exception as exc:
            if first_error is None:
                first_error = exc
    if first_error is not None:
        raise first_error


def _authorization_started_payload(
    server: Any,
    pending: MCPOAuthPendingAuthorization,
    *,
    callback_listening: bool,
    browser_opened: bool,
    reused: bool,
) -> dict[str, Any]:
    server_name = str(getattr(server, "name", "") or pending.server_name)
    return {
        "status": "auth_url",
        "server": server_name,
        "transport": str(getattr(server, "transport", "") or ""),
        "url": str(getattr(server, "url", "") or ""),
        "authUrl": pending.authorization_url,
        "auth_url": pending.authorization_url,
        "redirectUri": pending.redirect_uri,
        "redirect_uri": pending.redirect_uri,
        "expiresAt": pending.expires_at,
        "expires_at": pending.expires_at,
        "callbackListening": callback_listening,
        "callback_listening": callback_listening,
        "browserOpened": browser_opened,
        "browser_opened": browser_opened,
        "reused": reused,
        "message": (
            "Open this URL to authorize the %s MCP server. The local callback listener is waiting; "
            "if your browser cannot reach localhost, paste the full callback URL back into this tool as callback_url."
            if callback_listening
            else "Open this URL to authorize the %s MCP server, then paste the full callback URL back into this tool as callback_url."
        )
        % server_name,
    }


def _pending_flows(context: Any) -> dict[str, MCPOAuthPendingAuthorization]:
    flows = getattr(context, "mcp_oauth_flows", None)
    if not isinstance(flows, dict):
        flows = {}
        setattr(context, "mcp_oauth_flows", flows)
    return flows


def _oauth_waiters(context: Any) -> dict[str, MCPOAuthLoopbackWaiter]:
    waiters = getattr(context, "mcp_oauth_waiters", None)
    if not isinstance(waiters, dict):
        waiters = {}
        setattr(context, "mcp_oauth_waiters", waiters)
    return waiters


def _oauth_results(context: Any) -> dict[str, dict[str, Any]]:
    results = getattr(context, "mcp_oauth_results", None)
    if not isinstance(results, dict):
        results = {}
        setattr(context, "mcp_oauth_results", results)
    return results


async def _complete_mcp_oauth_authorization_for_context(
    context: Any,
    pending: MCPOAuthPendingAuthorization,
    callback_url: str,
    *,
    http_client: httpx.AsyncClient | None,
) -> dict[str, Any]:
    workspace = getattr(context, "workspace", None)
    payload = await complete_mcp_oauth_authorization(
        pending,
        callback_url,
        auth_store=getattr(context, "mcp_auth_store", None),
        tenant_id=str(getattr(workspace, "tenant_id", "") or ""),
        user_id=str(getattr(workspace, "user_id", "") or ""),
        agent_id=str(getattr(workspace, "agent_id", "") or ""),
        workspace_id=str(getattr(workspace, "workspace_id", "") or ""),
        http_client=http_client,
    )
    return await _attach_mcp_reload_result(context, payload)


async def _attach_mcp_reload_result(context: Any, payload: Mapping[str, Any]) -> dict[str, Any]:
    reload_result = await _reload_registry_for_authenticated_mcp(context)
    updated = dict(payload)
    updated["reload"] = reload_result
    updated["message"] = _authenticated_message_with_reload_result(updated, reload_result)
    return updated


async def _reload_registry_for_authenticated_mcp(context: Any) -> dict[str, Any]:
    registry = _active_mcp_registry(context)
    if registry is None:
        return {"status": "skipped", "reason": "no_active_registry"}

    lock = _oauth_reload_lock(context)
    async with lock:
        try:
            from agents.kernel.capabilities.tools.builtin.mcp.management import mcp_reload

            result = await mcp_reload(context, registry)
        except Exception as exc:  # noqa: BLE001 - token cache has already succeeded.
            return {"status": "error", "message": str(exc)}

    return {
        "status": "reloaded",
        "loaded_tools": list(result.get("loaded_tools") or []),
        "providers": list(result.get("providers") or []),
        "removed_tools": list(result.get("removed_tools") or []),
    }


def _active_mcp_registry(context: Any) -> Any | None:
    session = getattr(context, "session", None)
    runtime = getattr(session, "runtime", None)
    return getattr(runtime, "tools", None)


def _oauth_reload_lock(context: Any) -> Any:
    lock = getattr(context, "mcp_oauth_reload_lock", None)
    if lock is None:
        lock = asyncio.Lock()
        setattr(context, "mcp_oauth_reload_lock", lock)
    return lock


def _authenticated_message_with_reload_result(payload: Mapping[str, Any], reload_result: Mapping[str, Any]) -> str:
    server_name = str(payload.get("server") or "MCP server")
    status = str(reload_result.get("status") or "")
    if status == "reloaded":
        return "Authentication completed for %s. MCP tools were reloaded with the cached token." % server_name
    if status == "error":
        message = str(reload_result.get("message") or "unknown error")
        return "Authentication completed for %s. Token was cached, but MCP reload failed: %s" % (server_name, message)
    return str(
        payload.get("message")
        or "Authentication completed for %s. Run mcp.reload to reconnect with the cached token." % server_name
    )


async def _start_loopback_listener(context: Any, state: str) -> Any:
    port = find_available_mcp_oauth_callback_port()
    factory = getattr(context, "mcp_oauth_listener_factory", None)
    listener = factory(port=port, expected_state=state) if factory is not None else MCPOAuthCallbackListener(
        port=port,
        expected_state=state,
    )
    result = listener.start()
    if inspect.isawaitable(result):
        await result
    return listener


async def _cancel_mcp_oauth_waiter(context: Any, server_name: str) -> None:
    waiter = _oauth_waiters(context).pop(str(server_name or ""), None)
    if waiter is None:
        return
    waiter.task.cancel()
    with suppress(Exception):
        result = waiter.listener.close()
        if inspect.isawaitable(result):
            await result
    with suppress(asyncio.CancelledError):
        await waiter.task


async def _wait_for_loopback_callback(
    context: Any,
    server: Any,
    pending: MCPOAuthPendingAuthorization,
    listener: Any,
    *,
    http_client: httpx.AsyncClient | None,
) -> None:
    server_name = pending.server_name
    try:
        timeout = max(0.1, pending.expires_at - time.time()) if pending.expires_at else 5 * 60
        callback = await listener.wait(timeout_seconds=timeout)
        payload = await _complete_mcp_oauth_authorization_for_context(
            context,
            pending,
            callback.callback_url,
            http_client=http_client,
        )
        _oauth_results(context)[server_name] = payload
        _pending_flows(context).pop(server_name, None)
        _emit_oauth_event(context, "authenticated", payload)
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001 - OAuth failures are surfaced as status.
        payload = {
            "status": "error",
            "server": server_name,
            "transport": str(getattr(server, "transport", "") or ""),
            "url": str(getattr(server, "url", "") or ""),
            "message": str(exc),
        }
        _oauth_results(context)[server_name] = payload
        _pending_flows(context).pop(server_name, None)
        _emit_oauth_event(context, "error", payload)
    finally:
        _oauth_waiters(context).pop(server_name, None)
        with suppress(Exception):
            result = listener.close()
            if inspect.isawaitable(result):
                await result


async def _maybe_open_authorization_url(context: Any, authorization_url: str, *, enabled: bool) -> bool:
    if not enabled:
        return False
    opener = getattr(context, "mcp_oauth_browser_opener", None)
    if opener is None:
        return False
    result = opener(str(authorization_url or ""))
    if inspect.isawaitable(result):
        await result
    return True


def _emit_oauth_event(context: Any, status: str, payload: dict[str, Any]) -> None:
    emit = getattr(context, "emit_runtime_event", None)
    if emit is not None:
        emit("mcp_oauth", name="mcp.oauth", payload={"status": status, **dict(payload)})
