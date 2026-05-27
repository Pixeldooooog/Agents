from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from agents.kernel.schema import RuntimeEvent


@dataclass(frozen=True)
class SDKSessionReplayEvent:
    event: RuntimeEvent
    record: Any
    session_id: str
    run_id: str
    duration_ms: int


def compact_replay_events(entries: Sequence[SDKSessionReplayEvent]) -> list[SDKSessionReplayEvent]:
    events = list(entries)
    boundary_index = _last_compact_boundary_index(events)
    if boundary_index < 0:
        return events

    boundary = events[boundary_index]
    segment = _preserved_segment(boundary.event)
    if not segment:
        return events[boundary_index:]

    preserved = _preserved_entries(events[:boundary_index], segment)
    if preserved is None:
        return events
    preserved_ids = {_event_uuid(entry.event) for entry in preserved}
    return [
        boundary,
        *preserved,
        *(entry for entry in events[boundary_index + 1 :] if _event_uuid(entry.event) not in preserved_ids),
    ]


def _last_compact_boundary_index(events: list[SDKSessionReplayEvent]) -> int:
    for index in range(len(events) - 1, -1, -1):
        if events[index].event.type == "compact_boundary":
            return index
    return -1


def _preserved_segment(event: RuntimeEvent) -> dict[str, str]:
    metadata = event.payload.get("preserved_segment", event.payload.get("preservedSegment"))
    if not isinstance(metadata, dict):
        return {}
    head = metadata.get("head_uuid", metadata.get("headUuid"))
    tail = metadata.get("tail_uuid", metadata.get("tailUuid"))
    if not head or not tail:
        return {}
    return {"head_uuid": str(head), "tail_uuid": str(tail)}


def _preserved_entries(
    entries: list[SDKSessionReplayEvent],
    segment: dict[str, str],
) -> list[SDKSessionReplayEvent] | None:
    head_index = _event_index(entries, segment["head_uuid"])
    tail_index = _event_index(entries, segment["tail_uuid"])
    if head_index < 0 or tail_index < 0 or tail_index < head_index:
        return None
    return [
        entry
        for entry in entries[head_index : tail_index + 1]
        if _event_uuid(entry.event)
    ]


def _event_index(entries: list[SDKSessionReplayEvent], message_id: str) -> int:
    for index, entry in enumerate(entries):
        if _event_uuid(entry.event) == message_id:
            return index
    return -1


def _event_uuid(event: RuntimeEvent) -> str:
    payload = event.payload or {}
    for key in ("uuid", "message_id", "messageId", "id"):
        value = payload.get(key)
        if value:
            return str(value)
    nested = payload.get("message")
    if isinstance(nested, dict):
        for key in ("uuid", "message_id", "messageId", "id"):
            value = nested.get(key)
            if value:
                return str(value)
    return ""
