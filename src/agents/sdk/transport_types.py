from __future__ import annotations

from collections.abc import AsyncIterable, Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol, Union


SDKSSEPostHandler = Callable[[str, Mapping[str, str], dict[str, Any]], Awaitable[int]]
SDKSSEReadChunksFactory = Callable[
    [str, Mapping[str, str]],
    AsyncIterable[Union[str, bytes]],
]
SDKSSECloseHandler = Callable[[Optional[int]], Any]
SDKHybridPostHandler = Callable[[str, Mapping[str, str], dict[str, Any]], Awaitable[int]]
SDKBatchDropHandler = Callable[[int, int], Any]
SDKBatchSendHandler = Callable[[list[dict[str, Any]]], Awaitable[None]]
SDKWebSocketConnector = Callable[..., Awaitable[Any]]
SDKWebSocketCloseHandler = Callable[[Optional[int]], Any]


class SDKJsonlTransport(Protocol):
    """Bidirectional JSONL transport for SDK structured IO."""

    async def read(self) -> str | bytes | None:
        """Return the next inbound JSONL chunk, or None when input closes."""

    async def write(self, data: str) -> None:
        """Write one or more outbound JSONL lines."""

    async def close(self) -> None:
        """Close the transport."""


@dataclass
class SDKSSEFrame:
    event: str | None = None
    id: str | None = None
    data: str | None = None


@dataclass
class SDKWebSocketConnectOptions:
    headers: dict[str, str]
    proxy: str | None = None
    ssl_context: Any | None = None
    raw_options: dict[str, Any] = field(default_factory=dict)


class SDKSSELivenessTimeoutError(TimeoutError):
    """Raised internally when an SSE read connection stops producing frames."""


class SDKRetryableBatchError(RuntimeError):
    """Raised by batch senders to retry the current batch."""

    def __init__(self, message: str, *, retry_after_seconds: float | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds
