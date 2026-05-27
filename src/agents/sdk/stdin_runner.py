from __future__ import annotations

import asyncio
from collections.abc import AsyncIterable, AsyncIterator, Iterable
from typing import Any

from agents.sdk.async_messages import _coerce_async_user_message
from agents.sdk.control import (
    SDKControlRequest,
    SDKControlResponse,
    SDKKeepAliveMessage,
    SDKStdinMessage,
    SDKStdoutMessage,
    SDKUpdateEnvironmentVariablesMessage,
    validate_sdk_stdin_message,
)
from agents.sdk.options import _coerce_options
from agents.sdk.runtime_io import (
    _aiter_stdin_messages,
    _anext,
    _apply_environment_variables_update,
    _close_transport,
    _iter_transport_chunks,
    _replay_user_messages_enabled,
)
from agents.sdk.sessions import SDKSession
from agents.sdk.structured_io import SDKStructuredIO, encode_stdout_message, iter_stdin_jsonl
from agents.sdk.transports import SDKJsonlTransport
from agents.sdk.types import SDKOptions, SDKUserMessage


class SDKStdinRunnerMixin:
    async def run_stdin(
        self,
        messages: AsyncIterable[SDKStdinMessage | dict[str, Any]] | Iterable[SDKStdinMessage | dict[str, Any]],
        options: SDKOptions | dict[str, Any] | None = None,
        structured_io: SDKStructuredIO | None = None,
    ) -> AsyncIterator[SDKStdoutMessage]:
        session = self.create_sdk_session(_coerce_options(options))
        replay_user_messages = _replay_user_messages_enabled(session.options)
        io = structured_io or SDKStructuredIO(replay_user_messages=replay_user_messages)
        io.replay_user_messages = replay_user_messages
        received_user_uuids: set[str] = set()
        inbound = _aiter_stdin_messages(messages)
        inbound_task: asyncio.Task[SDKStdinMessage | dict[str, Any]] | None = asyncio.create_task(_anext(inbound))
        outbound_task: asyncio.Task[SDKStdoutMessage | None] | None = asyncio.create_task(io.next_stdout_message())
        try:
            while inbound_task is not None or outbound_task is not None:
                tasks = {task for task in (inbound_task, outbound_task) if task is not None}
                done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                if outbound_task in done:
                    outbound = outbound_task.result()
                    if outbound is None:
                        outbound_task = None
                    else:
                        yield outbound
                        outbound_task = asyncio.create_task(io.next_stdout_message())
                if inbound_task in done:
                    try:
                        raw_message = inbound_task.result()
                    except StopAsyncIteration:
                        inbound_task = None
                        io.close()
                        continue
                    async for output in self._process_stdin_message(
                        raw_message,
                        session=session,
                        structured_io=io,
                        replay_user_messages=replay_user_messages,
                        received_user_uuids=received_user_uuids,
                    ):
                        yield output
                    inbound_task = asyncio.create_task(_anext(inbound))
        finally:
            for task in (inbound_task, outbound_task):
                if task is not None and not task.done():
                    task.cancel()

    async def _process_stdin_message(
        self,
        raw_message: SDKStdinMessage | dict[str, Any],
        *,
        session: SDKSession,
        structured_io: SDKStructuredIO,
        replay_user_messages: bool,
        received_user_uuids: set[str],
    ) -> AsyncIterator[SDKStdoutMessage]:
        message = await structured_io.receive(validate_sdk_stdin_message(raw_message))
        if message is None:
            return
        if isinstance(message, SDKUserMessage):
            user_message = _coerce_async_user_message(message, session_id=session.session_id)
            if replay_user_messages:
                yield user_message.model_copy(update={"isReplay": True})
            if user_message.uuid in received_user_uuids:
                return
            received_user_uuids.add(user_message.uuid)
            session.enqueue_async_message(user_message)
            async for output in session._drain_async_messages(session.options):
                yield output
        elif isinstance(message, SDKControlRequest):
            yield await session.handle_control_request(message)
        elif isinstance(message, SDKUpdateEnvironmentVariablesMessage):
            _apply_environment_variables_update(session.options, message)
        elif isinstance(message, SDKKeepAliveMessage):
            return
        elif isinstance(message, SDKControlResponse):
            yield message

    async def run_stdin_jsonl(
        self,
        chunks: AsyncIterable[str | bytes] | Iterable[str | bytes],
        options: SDKOptions | dict[str, Any] | None = None,
        structured_io: SDKStructuredIO | None = None,
    ) -> AsyncIterator[str]:
        async for message in self.run_stdin(iter_stdin_jsonl(chunks), options, structured_io=structured_io):
            yield encode_stdout_message(message)

    async def run_jsonl_transport(
        self,
        transport: SDKJsonlTransport,
        options: SDKOptions | dict[str, Any] | None = None,
        structured_io: SDKStructuredIO | None = None,
        *,
        close_transport: bool = True,
    ) -> None:
        try:
            async for line in self.run_stdin_jsonl(
                _iter_transport_chunks(transport),
                options,
                structured_io=structured_io,
            ):
                await transport.write(line)
        finally:
            if close_transport:
                await _close_transport(transport)
