from agents.kernel.schema import RuntimeEvent
from agents.sdk import validate_sdk_message
from agents.sdk.client import _project_runtime_event_messages
from agents.sdk.session_compaction import SDKSessionReplayEvent, compact_replay_events
from agents.sdk.types import SDKCompactBoundaryMessage


def test_sdk_projects_compact_boundary_preserved_segment_metadata():
    [message] = _project_runtime_event_messages(
        RuntimeEvent(
            type="compact_boundary",
            name="context",
            payload={
                "uuid": "boundary-1",
                "trigger": "auto",
                "pre_tokens": 120,
                "post_tokens": 42,
                "before_messages": 5,
                "after_messages": 2,
                "dropped_messages": 3,
                "preserved_segment": {
                    "head_uuid": "user-3",
                    "anchor_uuid": "boundary-1",
                    "tail_uuid": "assistant-4",
                },
            },
        ),
        session_id="session-1",
        run_id="run-1",
        duration_ms=0,
        num_turns=1,
    )

    assert isinstance(message, SDKCompactBoundaryMessage)
    assert message.uuid == "boundary-1"
    assert message.compact_metadata["preserved_segment"] == {
        "head_uuid": "user-3",
        "anchor_uuid": "boundary-1",
        "tail_uuid": "assistant-4",
    }
    assert validate_sdk_message(message.model_dump()) == message


def test_sdk_compact_replay_keeps_preserved_segment_after_boundary():
    entries = [
        _entry(RuntimeEvent(type="user_message", payload={"uuid": "old-user"})),
        _entry(RuntimeEvent(type="user_message", payload={"uuid": "kept-user"})),
        _entry(
            RuntimeEvent(
                type="compact_boundary",
                payload={
                    "uuid": "boundary-1",
                    "preserved_segment": {
                        "head_uuid": "kept-user",
                        "anchor_uuid": "boundary-1",
                        "tail_uuid": "kept-user",
                    },
                },
            )
        ),
        _entry(RuntimeEvent(type="model_message", payload={"uuid": "assistant-1"})),
    ]

    replay = compact_replay_events(entries)

    assert [entry.event.type for entry in replay] == ["compact_boundary", "user_message", "model_message"]
    assert [entry.event.payload.get("uuid") for entry in replay] == ["boundary-1", "kept-user", "assistant-1"]


def test_sdk_compact_replay_keeps_full_history_when_preserved_segment_is_missing():
    entries = [
        _entry(RuntimeEvent(type="user_message", payload={"uuid": "kept-user"})),
        _entry(
            RuntimeEvent(
                type="compact_boundary",
                payload={
                    "uuid": "boundary-1",
                    "preserved_segment": {
                        "head_uuid": "missing-user",
                        "anchor_uuid": "boundary-1",
                        "tail_uuid": "missing-user",
                    },
                },
            )
        ),
    ]

    assert compact_replay_events(entries) == entries


def _entry(event: RuntimeEvent) -> SDKSessionReplayEvent:
    return SDKSessionReplayEvent(
        event=event,
        record=object(),
        session_id="session-1",
        run_id="run-1",
        duration_ms=0,
    )
