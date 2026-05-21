from __future__ import annotations

import asyncio
import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Union

from pydantic import TypeAdapter

from agents.sdk.control import (
    SDKControlCancelRequest,
    SDKControlPermissionRequest,
    SDKControlRequest,
    SDKControlRequestInner,
    SDKControlResponse,
    SDKControlResponseInner,
    SDKControlSuccessResponse,
    SDKStdinMessage,
    SDKStdoutMessage,
    validate_sdk_stdin_message,
    validate_sdk_stdout_message,
)


MAX_RESOLVED_TOOL_USE_IDS = 1000
SDKResponseValidator = Union[Callable[[Any], Any], TypeAdapter[Any]]
SDKUnexpectedResponseHandler = Callable[[SDKControlResponse], Any]


class SDKControlStreamClosedError(RuntimeError):
    """Raised when a pending SDK control request loses its input stream."""


class SDKControlRequestCancelledError(RuntimeError):
    """Raised when a pending SDK control request is canceled."""


class SDKControlRequestError(RuntimeError):
    """Raised when a host returns an SDK control error response."""


@dataclass
class _PendingControlRequest:
    request: SDKControlRequest
    future: asyncio.Future[Any]
    response_validator: SDKResponseValidator | None = None


class SDKStructuredIO:
    """Structured SDK control transport with stdout FIFO and pending replies.

    This mirrors the core of src-origin's StructuredIO boundary without taking
    ownership of process stdio or remote socket policy. Callers enqueue outgoing
    control requests through send_request(), emit outbound messages through the
    FIFO, and feed stdin messages back through receive().
    """

    def __init__(self, *, replay_user_messages: bool = False) -> None:
        self.replay_user_messages = replay_user_messages
        self._outbound: asyncio.Queue[SDKStdoutMessage | None] = asyncio.Queue()
        self._pending_requests: dict[str, _PendingControlRequest] = {}
        self._resolved_tool_use_ids: set[str] = set()
        self._resolved_tool_use_order: deque[str] = deque()
        self._closed = False
        self._unexpected_response_handler: SDKUnexpectedResponseHandler | None = None
        self._on_control_request_sent: Callable[[SDKControlRequest], Any] | None = None
        self._on_control_request_resolved: Callable[[str], Any] | None = None

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def pending_count(self) -> int:
        return len(self._pending_requests)

    def get_pending_permission_requests(self) -> list[SDKControlRequest]:
        return [
            pending.request
            for pending in self._pending_requests.values()
            if isinstance(pending.request.request, SDKControlPermissionRequest)
        ]

    def set_unexpected_response_handler(self, handler: SDKUnexpectedResponseHandler | None) -> None:
        self._unexpected_response_handler = handler

    def set_on_control_request_sent(self, handler: Callable[[SDKControlRequest], Any] | None) -> None:
        self._on_control_request_sent = handler

    def set_on_control_request_resolved(self, handler: Callable[[str], Any] | None) -> None:
        self._on_control_request_resolved = handler

    async def write(self, message: SDKStdoutMessage | dict[str, Any]) -> None:
        if self._closed:
            raise SDKControlStreamClosedError("SDK structured IO stream is closed")
        await self._outbound.put(validate_sdk_stdout_message(message))

    async def next_stdout_message(self) -> SDKStdoutMessage | None:
        return await self._outbound.get()

    def drain_stdout_messages(self) -> list[SDKStdoutMessage]:
        messages: list[SDKStdoutMessage] = []
        while True:
            try:
                message = self._outbound.get_nowait()
            except asyncio.QueueEmpty:
                return messages
            if message is not None:
                messages.append(message)

    async def send_request(
        self,
        request: SDKControlRequestInner | dict[str, Any],
        *,
        response_validator: SDKResponseValidator | None = None,
        request_id: str | None = None,
    ) -> Any:
        if self._closed:
            raise SDKControlStreamClosedError("SDK structured IO stream is closed")
        control = SDKControlRequest(
            request_id=request_id or str(uuid.uuid4()),
            request=request,
        )
        loop = asyncio.get_running_loop()
        future: asyncio.Future[Any] = loop.create_future()
        self._pending_requests[control.request_id] = _PendingControlRequest(
            request=control,
            future=future,
            response_validator=response_validator,
        )
        await self.write(control)
        if isinstance(control.request, SDKControlPermissionRequest) and self._on_control_request_sent:
            _maybe_schedule(self._on_control_request_sent(control))
        try:
            return await future
        finally:
            self._pending_requests.pop(control.request_id, None)

    async def cancel_request(self, request_id: str) -> None:
        pending = self._pending_requests.get(request_id)
        await self.write(SDKControlCancelRequest(request_id=request_id))
        if pending is not None and not pending.future.done():
            self._track_resolved_tool_use_id(pending.request)
            pending.future.set_exception(SDKControlRequestCancelledError("SDK control request canceled"))

    async def inject_control_response(self, response: SDKControlResponse | dict[str, Any]) -> None:
        control_response = validate_sdk_stdin_message(response)
        if not isinstance(control_response, SDKControlResponse):
            raise TypeError("inject_control_response expects a control_response message")
        request_id = control_response.response.request_id
        pending = self._pending_requests.get(request_id)
        if pending is None:
            return
        self._track_resolved_tool_use_id(pending.request)
        await self.write(SDKControlCancelRequest(request_id=request_id))
        self._resolve_pending_request(pending, control_response.response)

    async def receive(self, message: SDKStdinMessage | dict[str, Any]) -> SDKStdinMessage | None:
        inbound = validate_sdk_stdin_message(message)
        if not isinstance(inbound, SDKControlResponse):
            return inbound

        request_id = inbound.response.request_id
        pending = self._pending_requests.get(request_id)
        if pending is None:
            if self._is_duplicate_resolved_tool_response(inbound):
                return None
            if self._unexpected_response_handler is not None:
                _maybe_schedule(self._unexpected_response_handler(inbound))
            return inbound if self.replay_user_messages else None

        self._track_resolved_tool_use_id(pending.request)
        self._pending_requests.pop(request_id, None)
        if isinstance(pending.request.request, SDKControlPermissionRequest) and self._on_control_request_resolved:
            _maybe_schedule(self._on_control_request_resolved(request_id))
        self._resolve_pending_request(pending, inbound.response)
        return inbound if self.replay_user_messages else None

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for pending in list(self._pending_requests.values()):
            if not pending.future.done():
                pending.future.set_exception(
                    SDKControlStreamClosedError("SDK structured IO stream closed before response received")
                )
        self._pending_requests.clear()
        self._outbound.put_nowait(None)

    def _resolve_pending_request(
        self,
        pending: _PendingControlRequest,
        response: SDKControlResponseInner,
    ) -> None:
        if pending.future.done():
            return
        if response.subtype == "error":
            pending.future.set_exception(SDKControlRequestError(response.error))
            return
        payload = response.response if isinstance(response, SDKControlSuccessResponse) else None
        try:
            pending.future.set_result(_validate_response_payload(payload or {}, pending.response_validator))
        except Exception as exc:
            pending.future.set_exception(exc)

    def _track_resolved_tool_use_id(self, request: SDKControlRequest) -> None:
        if not isinstance(request.request, SDKControlPermissionRequest):
            return
        tool_use_id = request.request.tool_use_id
        if tool_use_id in self._resolved_tool_use_ids:
            return
        self._resolved_tool_use_ids.add(tool_use_id)
        self._resolved_tool_use_order.append(tool_use_id)
        while len(self._resolved_tool_use_order) > MAX_RESOLVED_TOOL_USE_IDS:
            expired = self._resolved_tool_use_order.popleft()
            self._resolved_tool_use_ids.discard(expired)

    def _is_duplicate_resolved_tool_response(self, response: SDKControlResponse) -> bool:
        if response.response.subtype != "success":
            return False
        payload = response.response.response or {}
        tool_use_id = payload.get("toolUseID") if isinstance(payload, dict) else None
        return isinstance(tool_use_id, str) and tool_use_id in self._resolved_tool_use_ids


def _validate_response_payload(payload: Any, validator: SDKResponseValidator | None) -> Any:
    if validator is None:
        return payload
    validate_python = getattr(validator, "validate_python", None)
    if callable(validate_python):
        return validate_python(payload)
    return validator(payload)


def _maybe_schedule(result: Any) -> None:
    if not asyncio.iscoroutine(result):
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(result)
