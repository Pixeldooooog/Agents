from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Literal


CCR_HEARTBEAT_INTERVAL_SECONDS = 20.0
CCR_UPLOAD_BASE_DELAY_SECONDS = 0.5
CCR_UPLOAD_MAX_DELAY_SECONDS = 30.0
CCR_WORKER_STATE_BASE_DELAY_SECONDS = 0.5
CCR_WORKER_STATE_MAX_DELAY_SECONDS = 30.0
CCR_STREAM_EVENT_FLUSH_INTERVAL_SECONDS = 0.1
CCR_GET_MAX_ATTEMPTS = 10
CCR_GET_BASE_DELAY_SECONDS = 0.5
CCR_GET_MAX_DELAY_SECONDS = 30.0
CCR_MAX_CONSECUTIVE_AUTH_FAILURES = 10


SDKCCRDeliveryStatus = Literal["received", "processing", "processed"]
SDKCCRShutdownReason = Literal[
    "epoch_mismatch",
    "auth_expired",
    "auth_failures_exhausted",
]
SDKCCRShutdownHandler = Callable[[SDKCCRShutdownReason], Any]


class SDKCCRInitError(RuntimeError):
    """Raised when a CCR worker cannot be initialized."""


class SDKCCRShutdownError(RuntimeError):
    """Raised when CCR reports this worker must shut down."""

    def __init__(self, reason: SDKCCRShutdownReason, message: str | None = None) -> None:
        self.reason = reason
        super().__init__(message or reason)


class SDKCCREpochMismatchError(SDKCCRShutdownError):
    """Raised when CCR reports that this worker epoch was superseded."""

    def __init__(self) -> None:
        super().__init__("epoch_mismatch", "worker epoch mismatch")


class SDKCCRAuthFailureError(SDKCCRShutdownError):
    """Raised when CCR authentication is terminal for this worker."""


class SDKCCRRequestResult:
    def __init__(
        self,
        ok: bool,
        *,
        status: int | None = None,
        data: Any = None,
        retry_after_seconds: float | None = None,
    ) -> None:
        self.ok = ok
        self.status = status
        self.data = data
        self.retry_after_seconds = retry_after_seconds


SDKCCRRequestHandler = Callable[
    [str, str, Mapping[str, str], dict[str, Any] | None],
    Awaitable[SDKCCRRequestResult],
]
