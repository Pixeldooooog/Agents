from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any, Literal

from agents.sdk.async_messages import (
    _SDKAsyncMessageQueueItem,
    _async_message_priority,
    _async_message_priority_value,
    _sorted_async_message_items,
)
from agents.sdk.control import SDKControlCancelAsyncMessageRequest
from agents.sdk.types import SDKOptions, SDKUserMessage


class SDKControlAsyncStateMixin:
    def _cancel_async_message_control_response(self, request: SDKControlCancelAsyncMessageRequest) -> dict[str, Any]:
        removed = self._dequeue_matching_async_messages(
            lambda item: item.message.uuid == request.message_uuid,
        )
        return {"cancelled": bool(removed)}

    def _dequeue_matching_async_messages(
        self,
        predicate: Callable[[_SDKAsyncMessageQueueItem], bool],
    ) -> list[SDKUserMessage]:
        matched: list[_SDKAsyncMessageQueueItem] = []
        remaining: list[_SDKAsyncMessageQueueItem] = []
        for item in self.async_message_queue:
            if predicate(item):
                matched.append(item)
            else:
                remaining.append(item)
        if not matched:
            return []
        self.async_message_queue = remaining
        return [item.message for item in _sorted_async_message_items(matched)]

    def _interrupt_active_turn_for_async_message(self, session_id: str) -> None:
        if not session_id:
            return
        task = self.active_turn_tasks.get(session_id)
        if task is None or task.done():
            return
        try:
            current = asyncio.current_task()
        except RuntimeError:
            current = None
        if task is current:
            return
        task.cancel("interrupt")

    def _wake_active_sleep_for_async_message(self, session_id: str) -> None:
        if session_id:
            event = self.active_sleep_wake_events.get(session_id)
            if event is not None:
                event.set()
            return
        for event in set(self.active_sleep_wake_events.values()):
            event.set()

    def _has_async_messages(
        self,
        *,
        session_id: str = "",
        max_priority: Literal["now", "next", "later"] = "later",
    ) -> bool:
        max_rank = _async_message_priority(max_priority)
        for item in self.async_message_queue:
            if session_id and item.message.session_id != session_id:
                continue
            if _async_message_priority(item.message.priority) <= max_rank:
                return True
        return False

    def _interrupt_control_response(self, options: SDKOptions) -> dict[str, Any]:
        keys = [str(options.session_id or "")]
        run_id = str(options.metadata.get("run_id") or options.metadata.get("runId") or "")
        if run_id:
            keys.append(run_id)
        current = asyncio.current_task()
        for key in keys:
            if not key:
                continue
            task = self.active_turn_tasks.get(key)
            if task is None or task.done():
                continue
            if task is current:
                return {"interrupted": False, "reason": "cannot interrupt the current control handler task"}
            task.cancel("interrupt")
            return {"interrupted": True, "session_id": key, "run_id": self.active_turn_run_ids.get(key, "")}
        return {"interrupted": False, "reason": "no active SDK turn is attached to this control handler"}

    def _clear_active_turn(
        self,
        session_id: str,
        run_id: str,
        task: asyncio.Task[Any] | None,
        session: Any | None = None,
    ) -> None:
        for key in (session_id, run_id):
            if task is None or self.active_turn_tasks.get(key) is task:
                self.active_turn_tasks.pop(key, None)
                self.active_turn_run_ids.pop(key, None)
                self.active_sleep_wake_events.pop(key, None)
            if session is None or self.active_turn_sessions.get(key) is session:
                self.active_turn_sessions.pop(key, None)

    def _install_sleep_wake_for_turn(self, session: Any, *, session_id: str, run_id: str) -> None:
        context = getattr(session, "tool_context", None)
        if context is None:
            return
        event = asyncio.Event()
        context.sleep_wake_event = event
        context.sleep_wake_check = lambda: self._has_async_messages(session_id=session_id, max_priority="later")
        context.async_message_enqueue = lambda message: self.enqueue_async_message(
            message,
            session_id=session_id,
            priority=_async_message_priority_value(message),
        )
        self.active_sleep_wake_events[session_id] = event
        self.active_sleep_wake_events[run_id] = event
