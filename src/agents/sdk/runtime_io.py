from __future__ import annotations

import inspect
import os
from collections.abc import AsyncIterable, AsyncIterator, Iterable
from typing import Any

from agents.sdk.control import (
    SDKControlElicitationRequest,
    SDKStdinMessage,
    SDKUpdateEnvironmentVariablesMessage,
)
from agents.sdk.transports import SDKJsonlTransport
from agents.sdk.types import SDKOptions


def _sdk_elicitation_request_from_mcp_params(server_name: str, params: Any) -> SDKControlElicitationRequest:
    mode = str(_mcp_param_field(params, "mode") or "form")
    requested_schema = _mcp_param_field(params, "requested_schema", "requestedSchema")
    return SDKControlElicitationRequest(
        mcp_server_name=str(server_name or ""),
        message=str(_mcp_param_field(params, "message") or ""),
        mode="url" if mode == "url" else "form",
        url=_optional_string(_mcp_param_field(params, "url")),
        elicitation_id=_optional_string(_mcp_param_field(params, "elicitation_id", "elicitationId")),
        requested_schema=dict(requested_schema) if isinstance(requested_schema, dict) else None,
    )


async def _aiter_stdin_messages(
    messages: AsyncIterable[SDKStdinMessage | dict[str, Any]] | Iterable[SDKStdinMessage | dict[str, Any]],
) -> AsyncIterator[SDKStdinMessage | dict[str, Any]]:
    if hasattr(messages, "__aiter__"):
        async for message in messages:  # type: ignore[union-attr]
            yield message
        return
    for message in messages:  # type: ignore[union-attr]
        yield message


async def _iter_transport_chunks(transport: SDKJsonlTransport) -> AsyncIterator[str | bytes]:
    while True:
        chunk = await transport.read()
        if chunk is None:
            return
        yield chunk


async def _close_transport(transport: SDKJsonlTransport) -> None:
    close = getattr(transport, "close", None)
    if not callable(close):
        return
    result = close()
    if inspect.isawaitable(result):
        await result


async def _anext(iterator: AsyncIterator[SDKStdinMessage | dict[str, Any]]) -> SDKStdinMessage | dict[str, Any]:
    return await iterator.__anext__()


def _apply_environment_variables_update(options: SDKOptions, message: SDKUpdateEnvironmentVariablesMessage) -> None:
    current = options.metadata.get("environment_variables")
    variables = dict(current) if isinstance(current, dict) else {}
    variables.update(message.variables)
    options.metadata["environment_variables"] = variables
    os.environ.update(message.variables)


def _replay_user_messages_enabled(options: SDKOptions) -> bool:
    return bool(
        options.replay_user_messages
        or options.metadata.get("replay_user_messages")
        or options.metadata.get("replayUserMessages")
    )


def _mcp_param_field(params: Any, *names: str) -> Any:
    if params is None:
        return None
    if isinstance(params, dict):
        for name in names:
            if name in params:
                return params[name]
        return None
    for name in names:
        if hasattr(params, name):
            return getattr(params, name)
    model_dump = getattr(params, "model_dump", None)
    if callable(model_dump):
        try:
            payload = model_dump(by_alias=True)
        except TypeError:
            payload = model_dump()
        if isinstance(payload, dict):
            for name in names:
                if name in payload:
                    return payload[name]
    return None


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None
