from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

import anyio
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream

import mcp.types as types
from mcp.shared.message import SessionMessage


SDKMCPMessageHandler = Callable[[dict[str, Any]], Any]


def sdk_control_client(handler: SDKMCPMessageHandler) -> "_SDKControlClientContext":
    return _SDKControlClientContext(handler)


class _SDKControlClientContext:
    def __init__(self, handler: SDKMCPMessageHandler):
        self._handler = handler
        self._task_group: Any | None = None
        self._read_stream_writer: MemoryObjectSendStream[SessionMessage | Exception] | None = None
        self._read_stream: MemoryObjectReceiveStream[SessionMessage | Exception] | None = None
        self._write_stream: MemoryObjectSendStream[SessionMessage] | None = None
        self._write_stream_reader: MemoryObjectReceiveStream[SessionMessage] | None = None

    async def __aenter__(
        self,
    ) -> tuple[MemoryObjectReceiveStream[SessionMessage | Exception], MemoryObjectSendStream[SessionMessage]]:
        self._read_stream_writer, self._read_stream = anyio.create_memory_object_stream(0)
        self._write_stream, self._write_stream_reader = anyio.create_memory_object_stream(0)
        self._task_group = anyio.create_task_group()
        await self._task_group.__aenter__()
        self._task_group.start_soon(self._bridge_messages)
        return self._read_stream, self._write_stream

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self._task_group is not None:
            self._task_group.cancel_scope.cancel()
            await self._task_group.__aexit__(exc_type, exc, tb)
            self._task_group = None

    async def _bridge_messages(self) -> None:
        assert self._write_stream_reader is not None
        assert self._read_stream_writer is not None
        async with self._write_stream_reader, self._read_stream_writer:
            async for session_message in self._write_stream_reader:
                try:
                    response = self._handler(_message_payload(session_message))
                    if inspect.isawaitable(response):
                        response = await response
                    for item in _response_items(response):
                        message = types.JSONRPCMessage.model_validate(item)
                        await self._read_stream_writer.send(SessionMessage(message))
                except Exception as exc:
                    await self._read_stream_writer.send(exc)


def _message_payload(session_message: SessionMessage) -> dict[str, Any]:
    return session_message.message.model_dump(
        by_alias=True,
        mode="json",
        exclude_none=True,
    )


def _response_items(response: Any) -> list[dict[str, Any]]:
    if response is None:
        return []
    if isinstance(response, dict) and isinstance(response.get("mcp_response"), dict):
        return [dict(response["mcp_response"])]
    if isinstance(response, list):
        return [dict(item) for item in response if isinstance(item, dict)]
    if isinstance(response, dict):
        return [dict(response)]
    raise TypeError("SDK MCP handler must return a JSON-RPC response object")
