from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Literal
from urllib.parse import urlsplit, urlunsplit

from agents.sdk.structured_io import ndjson_safe_dumps
from agents.sdk.transports import SDKRetryableBatchError, SDKSerialBatchUploader


CCR_HEARTBEAT_INTERVAL_SECONDS = 20.0
CCR_UPLOAD_BASE_DELAY_SECONDS = 0.5
CCR_UPLOAD_MAX_DELAY_SECONDS = 30.0
CCR_WORKER_STATE_BASE_DELAY_SECONDS = 0.5
CCR_WORKER_STATE_MAX_DELAY_SECONDS = 30.0


SDKCCRDeliveryStatus = Literal["received", "processing", "processed"]
SDKCCRRequestHandler = Callable[
    [str, str, Mapping[str, str], dict[str, Any]],
    Awaitable["SDKCCRRequestResult"],
]


class SDKCCRInitError(RuntimeError):
    """Raised when a CCR worker cannot be initialized."""


class SDKCCREpochMismatchError(RuntimeError):
    """Raised when CCR reports that this worker epoch was superseded."""


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


class SDKWorkerStateUploader:
    """Coalescing uploader for CCR worker state patches."""

    def __init__(
        self,
        send: Callable[[dict[str, Any]], Awaitable[bool]],
        *,
        base_delay_seconds: float = CCR_WORKER_STATE_BASE_DELAY_SECONDS,
        max_delay_seconds: float = CCR_WORKER_STATE_MAX_DELAY_SECONDS,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._send = send
        self._base_delay_seconds = base_delay_seconds
        self._max_delay_seconds = max_delay_seconds
        self._sleep = sleep
        self._pending: dict[str, Any] | None = None
        self._drain_task: asyncio.Task[None] | None = None
        self._closed = False

    @property
    def pending_count(self) -> int:
        return 0 if self._pending is None else 1

    def enqueue(self, patch: dict[str, Any]) -> None:
        if self._closed:
            return
        self._pending = _coalesce_worker_state_patches(self._pending or {}, patch)
        if self._drain_task is None or self._drain_task.done():
            self._drain_task = asyncio.create_task(self._drain())

    async def flush(self) -> None:
        if self._drain_task is not None:
            await self._drain_task

    def close(self) -> None:
        self._closed = True
        self._pending = None
        if self._drain_task is not None and not self._drain_task.done():
            self._drain_task.cancel()

    async def _drain(self) -> None:
        try:
            while self._pending is not None and not self._closed:
                current = self._pending
                self._pending = None
                failures = 0
                while not self._closed:
                    if await self._send(current):
                        break
                    failures += 1
                    await self._sleep(
                        min(
                            self._base_delay_seconds * (2 ** (failures - 1)),
                            self._max_delay_seconds,
                        )
                    )
                    if self._pending is not None:
                        current = _coalesce_worker_state_patches(current, self._pending)
                        self._pending = None
        except asyncio.CancelledError:
            pass


class SDKCCRClient:
    """CCR v2 worker lifecycle and event uploader for SDK remote IO."""

    def __init__(
        self,
        session_url: str,
        *,
        transport: Any | None = None,
        request: SDKCCRRequestHandler | None = None,
        get_auth_headers: Callable[[], Mapping[str, str]] | None = None,
        heartbeat_interval_seconds: float | None = CCR_HEARTBEAT_INTERVAL_SECONDS,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.session_base_url = _normalize_session_url(session_url)
        self.session_id = self.session_base_url.rstrip("/").split("/")[-1]
        self.worker_epoch = 0
        self.closed = False
        self.current_state: str | None = None
        self._request_handler = request
        self._get_auth_headers = get_auth_headers or (lambda: {})
        self._heartbeat_interval_seconds = heartbeat_interval_seconds
        self._sleep = sleep
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._delivery_enqueue_tasks: list[asyncio.Task[None]] = []
        self._http_client = None
        self.worker_state = SDKWorkerStateUploader(
            self._send_worker_state,
            sleep=sleep,
        )
        self.event_uploader = SDKSerialBatchUploader(
            max_batch_size=100,
            max_queue_size=100_000,
            base_delay_seconds=CCR_UPLOAD_BASE_DELAY_SECONDS,
            max_delay_seconds=CCR_UPLOAD_MAX_DELAY_SECONDS,
            send=self._send_client_events,
            sleep=sleep,
        )
        self.internal_event_uploader = SDKSerialBatchUploader(
            max_batch_size=100,
            max_queue_size=200,
            base_delay_seconds=CCR_UPLOAD_BASE_DELAY_SECONDS,
            max_delay_seconds=CCR_UPLOAD_MAX_DELAY_SECONDS,
            send=self._send_internal_events,
            sleep=sleep,
        )
        self.delivery_uploader = SDKSerialBatchUploader(
            max_batch_size=64,
            max_queue_size=64,
            base_delay_seconds=CCR_UPLOAD_BASE_DELAY_SECONDS,
            max_delay_seconds=CCR_UPLOAD_MAX_DELAY_SECONDS,
            send=self._send_delivery_updates,
            sleep=sleep,
        )
        if transport is not None and hasattr(transport, "set_on_event"):
            transport.set_on_event(lambda event: self.report_delivery(str(event["event_id"]), "received"))

    @property
    def internal_events_pending(self) -> int:
        return self.internal_event_uploader.pending_count

    async def initialize(self, epoch: int) -> dict[str, Any] | None:
        if not self._get_auth_headers():
            raise SDKCCRInitError("no_auth_headers")
        self.worker_epoch = int(epoch)
        result = await self._request(
            "put",
            "/worker",
            {
                "worker_status": "idle",
                "worker_epoch": self.worker_epoch,
                "external_metadata": {"pending_action": None, "task_summary": None},
            },
        )
        if not result.ok:
            raise SDKCCRInitError("worker_register_failed")
        self.current_state = "idle"
        self._start_heartbeat()
        return result.data if isinstance(result.data, dict) else None

    def report_state(self, state: str, details: dict[str, Any] | None = None) -> None:
        if state == self.current_state and not details:
            return
        self.current_state = state
        self.worker_state.enqueue(
            {
                "worker_status": state,
                "requires_action_details": details or None,
            }
        )

    def report_metadata(self, metadata: dict[str, Any]) -> None:
        self.worker_state.enqueue({"external_metadata": dict(metadata)})

    def report_delivery(self, event_id: str, status: SDKCCRDeliveryStatus) -> None:
        task = asyncio.create_task(
            self.delivery_uploader.enqueue([{"eventId": event_id, "status": status}])
        )
        self._delivery_enqueue_tasks.append(task)

    async def write_event(self, message: dict[str, Any]) -> None:
        await self.event_uploader.enqueue([self._client_event(message)])

    async def write_internal_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        is_compaction: bool = False,
        agent_id: str | None = None,
    ) -> None:
        event: dict[str, Any] = {
            "payload": {
                "type": event_type,
                **payload,
                "uuid": payload.get("uuid") if isinstance(payload.get("uuid"), str) else str(uuid.uuid4()),
            }
        }
        if is_compaction:
            event["is_compaction"] = True
        if agent_id:
            event["agent_id"] = agent_id
        await self.internal_event_uploader.enqueue([event])

    async def flush(self) -> None:
        await self.event_uploader.flush()

    async def flush_internal_events(self) -> None:
        await self.internal_event_uploader.flush()

    async def flush_delivery(self) -> None:
        if self._delivery_enqueue_tasks:
            tasks = list(self._delivery_enqueue_tasks)
            self._delivery_enqueue_tasks = []
            await asyncio.gather(*tasks)
        await self.delivery_uploader.flush()

    async def flush_worker_state(self) -> None:
        await self.worker_state.flush()

    async def close(self) -> None:
        self.closed = True
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None
        self.worker_state.close()
        self.event_uploader.close()
        self.internal_event_uploader.close()
        self.delivery_uploader.close()
        for task in self._delivery_enqueue_tasks:
            task.cancel()
        self._delivery_enqueue_tasks = []
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    async def _send_worker_state(self, body: dict[str, Any]) -> bool:
        result = await self._request("put", "/worker", {"worker_epoch": self.worker_epoch, **body})
        return result.ok

    async def _send_client_events(self, events: list[dict[str, Any]]) -> None:
        result = await self._request(
            "post",
            "/worker/events",
            {"worker_epoch": self.worker_epoch, "events": events},
        )
        if not result.ok:
            raise SDKRetryableBatchError(
                "client event POST failed",
                retry_after_seconds=result.retry_after_seconds,
            )

    async def _send_internal_events(self, events: list[dict[str, Any]]) -> None:
        result = await self._request(
            "post",
            "/worker/internal-events",
            {"worker_epoch": self.worker_epoch, "events": events},
        )
        if not result.ok:
            raise SDKRetryableBatchError(
                "internal event POST failed",
                retry_after_seconds=result.retry_after_seconds,
            )

    async def _send_delivery_updates(self, updates: list[dict[str, Any]]) -> None:
        result = await self._request(
            "post",
            "/worker/events/delivery",
            {
                "worker_epoch": self.worker_epoch,
                "updates": [
                    {"event_id": update["eventId"], "status": update["status"]}
                    for update in updates
                ],
            },
        )
        if not result.ok:
            raise SDKRetryableBatchError(
                "delivery POST failed",
                retry_after_seconds=result.retry_after_seconds,
            )

    def _start_heartbeat(self) -> None:
        if self._heartbeat_interval_seconds is None or self._heartbeat_interval_seconds <= 0:
            return
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def _heartbeat_loop(self) -> None:
        try:
            while not self.closed:
                await self._sleep(self._heartbeat_interval_seconds or 0)
                if not self.closed:
                    await self._request(
                        "post",
                        "/worker/heartbeat",
                        {
                            "session_id": self.session_id,
                            "worker_epoch": self.worker_epoch,
                        },
                    )
        except asyncio.CancelledError:
            pass

    def _client_event(self, message: dict[str, Any]) -> dict[str, Any]:
        payload = dict(message)
        if not isinstance(payload.get("uuid"), str):
            payload["uuid"] = str(uuid.uuid4())
        return {"payload": payload}

    async def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any],
    ) -> SDKCCRRequestResult:
        headers = dict(self._get_auth_headers())
        if not headers:
            return SDKCCRRequestResult(False)
        if self._request_handler is not None:
            result = await self._request_handler(method, path, headers, body)
            if result.status == 409:
                raise SDKCCREpochMismatchError("worker epoch mismatch")
            return result
        client = await self._ensure_http_client()
        response = await client.request(
            method.upper(),
            f"{self.session_base_url}{path}",
            headers={**headers, "Content-Type": "application/json"},
            json=body,
        )
        if response.status_code == 409:
            raise SDKCCREpochMismatchError("worker epoch mismatch")
        retry_after = response.headers.get("retry-after")
        retry_after_seconds = float(retry_after) if retry_after else None
        return SDKCCRRequestResult(
            200 <= response.status_code < 300,
            status=response.status_code,
            data=response.json() if response.content else None,
            retry_after_seconds=retry_after_seconds,
        )

    async def _ensure_http_client(self) -> Any:
        if self._http_client is None:
            try:
                import httpx
            except ImportError as exc:
                raise RuntimeError("SDKCCRClient requires the httpx package") from exc
            self._http_client = httpx.AsyncClient(timeout=30.0)
        return self._http_client


def _coalesce_worker_state_patches(
    base: dict[str, Any],
    overlay: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overlay.items():
        if (
            key in {"external_metadata", "internal_metadata"}
            and isinstance(merged.get(key), dict)
            and isinstance(value, dict)
        ):
            merged[key] = {**merged[key], **value}
        else:
            merged[key] = value
    return merged


def _normalize_session_url(session_url: str) -> str:
    parts = urlsplit(session_url)
    path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))
