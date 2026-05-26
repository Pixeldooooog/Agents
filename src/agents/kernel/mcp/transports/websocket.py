from __future__ import annotations

import json
from collections.abc import AsyncGenerator, Mapping
from contextlib import asynccontextmanager
from typing import Any

import anyio
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from pydantic import ValidationError
from websockets.asyncio.client import connect as ws_connect
from websockets.typing import Subprotocol

import mcp.types as types
from mcp.shared.message import SessionMessage


@asynccontextmanager
async def websocket_client_with_headers(
    url: str,
    *,
    headers: Mapping[str, str] | None = None,
) -> AsyncGenerator[
    tuple[MemoryObjectReceiveStream[SessionMessage | Exception], MemoryObjectSendStream[SessionMessage]],
    None,
]:
    read_stream_writer, read_stream = anyio.create_memory_object_stream(0)
    write_stream, write_stream_reader = anyio.create_memory_object_stream(0)

    async with ws_connect(
        url,
        subprotocols=[Subprotocol("mcp")],
        additional_headers=_headers(headers),
    ) as ws:

        async def ws_reader() -> None:
            async with read_stream_writer:
                async for raw_text in ws:
                    try:
                        message = types.JSONRPCMessage.model_validate_json(raw_text)
                        await read_stream_writer.send(SessionMessage(message))
                    except ValidationError as exc:
                        await read_stream_writer.send(exc)

        async def ws_writer() -> None:
            async with write_stream_reader:
                async for session_message in write_stream_reader:
                    payload = session_message.message.model_dump(
                        by_alias=True,
                        mode="json",
                        exclude_none=True,
                    )
                    await ws.send(json.dumps(payload))

        async with anyio.create_task_group() as task_group:
            task_group.start_soon(ws_reader)
            task_group.start_soon(ws_writer)
            yield read_stream, write_stream
            task_group.cancel_scope.cancel()


def _headers(headers: Mapping[str, Any] | None) -> dict[str, str] | None:
    normalized = {
        str(key): str(value)
        for key, value in dict(headers or {}).items()
        if str(key or "").strip()
    }
    return normalized or None
