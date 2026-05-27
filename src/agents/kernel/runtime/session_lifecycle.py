from __future__ import annotations

import inspect
from typing import Any


async def close_session_resources(session: Any) -> None:
    first_error: Exception | None = None
    tool_context = getattr(session, "tool_context", None)
    if tool_context is not None:
        first_error = await _close_mcp_oauth_waiters(tool_context, first_error)

    providers = list(getattr(tool_context, "mcp_providers", []) or []) if tool_context is not None else []
    for provider in providers:
        first_error = await _close_provider(provider, first_error)
    if tool_context is not None:
        tool_context.mcp_providers = []

    model_client = getattr(session.runtime, "model_client", None)
    first_error = await _close_owned_resource(model_client, first_error)
    summary_generator = getattr(getattr(session.runtime, "tool_orchestrator", None), "tool_summary_generator", None)
    first_error = await _close_owned_resource(summary_generator, first_error, shared_model_client=model_client)
    context_compactor = getattr(getattr(session, "context_window", None), "compactor", None)
    first_error = await _close_owned_resource(context_compactor, first_error, shared_model_client=model_client)
    if first_error is not None:
        raise first_error


async def _close_mcp_oauth_waiters(tool_context: Any, first_error: Exception | None) -> Exception | None:
    try:
        from agents.kernel.mcp.oauth_runtime import close_mcp_oauth_waiters

        await close_mcp_oauth_waiters(tool_context)
    except Exception as exc:
        return first_error or exc
    return first_error


async def _close_provider(provider: Any, first_error: Exception | None) -> Exception | None:
    close_provider = getattr(provider, "close", None)
    if close_provider is None:
        return first_error
    try:
        result = close_provider()
        if inspect.isawaitable(result):
            await result
    except Exception as exc:
        return first_error or exc
    return first_error


async def _close_owned_resource(
    resource: Any,
    first_error: Exception | None,
    *,
    shared_model_client: Any = None,
) -> Exception | None:
    close = getattr(resource, "async_close", None)
    if close is None or (shared_model_client is not None and getattr(resource, "model_client", None) is shared_model_client):
        return first_error
    try:
        await close()
    except Exception as exc:
        return first_error or exc
    return first_error
