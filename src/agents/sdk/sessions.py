from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from agents.sdk.control import SDKControlRequest, SDKControlResponse, validate_sdk_control_request
from agents.sdk.options import _apply_session_control_request, _merge_session_options
from agents.sdk.types import (
    SDKForkSessionOptions,
    SDKGetSessionMessagesOptions,
    SDKMessage,
    SDKOptions,
    SDKResultMessage,
    SDKSessionInfo,
    SDKUserMessage,
)

if TYPE_CHECKING:
    from agents.sdk.client import AgentSDKClient


@dataclass
class SDKSession:
    """High-level persistent SDK session handle.

    The handle keeps a stable SDK session id while each prompt still executes as
    a stored run, which keeps the wrapper decoupled from the kernel runtime.
    """

    client: AgentSDKClient
    session_id: str
    options: SDKOptions

    async def query(
        self,
        prompt: str,
        options: SDKOptions | dict[str, Any] | None = None,
    ) -> AsyncIterator[SDKMessage]:
        merged = _merge_session_options(self.options, options, session_id=self.session_id)
        last_result: SDKResultMessage | None = None
        async for message in self.client.query(prompt, merged):
            if isinstance(message, SDKResultMessage):
                last_result = message
            yield message
        if last_result is not None and last_result.stop_reason == "awaiting_approval":
            return
        async for message in self._drain_async_messages(merged):
            yield message

    async def _drain_async_messages(self, options: SDKOptions) -> AsyncIterator[SDKMessage]:
        while True:
            queued = self.client.dequeue_async_message(session_id=self.session_id)
            if queued is None:
                return
            async for message in self.client.query_user_message(queued, options):
                yield message

    async def prompt(
        self,
        prompt: str,
        options: SDKOptions | dict[str, Any] | None = None,
    ) -> SDKResultMessage:
        result: SDKResultMessage | None = None
        async for message in self.query(prompt, options):
            if isinstance(message, SDKResultMessage):
                result = message
        if result is None:
            raise RuntimeError("SDK session prompt completed without a result message")
        return result

    def enqueue_async_message(
        self,
        message: SDKUserMessage | dict[str, Any] | str,
        *,
        priority: Literal["now", "next", "later"] | None = None,
    ) -> SDKUserMessage:
        return self.client.enqueue_async_message(message, session_id=self.session_id, priority=priority)

    def list_async_messages(self) -> list[SDKUserMessage]:
        return self.client.list_async_messages(session_id=self.session_id)

    def dequeue_async_message(self) -> SDKUserMessage | None:
        return self.client.dequeue_async_message(session_id=self.session_id)

    async def messages(
        self,
        options: SDKGetSessionMessagesOptions | dict[str, Any] | None = None,
    ) -> list[SDKMessage]:
        return await self.client.get_session_messages(self.session_id, options)

    async def info(self) -> SDKSessionInfo | None:
        return await self.client.get_session_info(self.session_id)

    async def rename(self, title: str) -> None:
        await self.client.rename_session(self.session_id, title)

    async def tag(self, tag: str | None) -> None:
        await self.client.tag_session(self.session_id, tag)

    async def fork(self, options: SDKForkSessionOptions | dict[str, Any] | None = None) -> "SDKSession":
        result = await self.client.fork_session(self.session_id, options)
        return await self.client.resume_session(result.session_id)

    async def handle_control_request(
        self,
        message: SDKControlRequest | dict[str, Any],
    ) -> SDKControlResponse:
        control = validate_sdk_control_request(message)
        self.options = _apply_session_control_request(self.options, control.request)
        return await self.client.handle_control_request(control, self.options)
