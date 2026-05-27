from agents.kernel.context.compaction_metadata import compact_boundary_payload, preserved_segment
from agents.kernel.schema import Message


def test_compact_boundary_payload_reports_preserved_segment_ids():
    messages = [
        Message.from_text("user", "old request " + ("alpha " * 80), raw={"uuid": "old-user"}),
        Message.from_text("assistant", "old answer " + ("beta " * 80), raw={"uuid": "old-assistant"}),
        Message.from_text("user", "recent request", raw={"uuid": "recent-user"}),
    ]
    fitted = [messages[-1]]

    payload = compact_boundary_payload(
        messages,
        fitted,
        trigger="auto",
        pre_tokens=180,
        post_tokens=12,
    )

    assert payload["uuid"]
    assert payload["trigger"] == "auto"
    assert payload["pre_tokens"] == 180
    assert payload["post_tokens"] == 12
    assert payload["before_messages"] == 3
    assert payload["after_messages"] == 1
    assert payload["dropped_messages"] == 2
    assert payload["preserved_segment"] == {
        "head_uuid": "recent-user",
        "anchor_uuid": payload["uuid"],
        "tail_uuid": "recent-user",
    }


def test_preserved_segment_ignores_synthetic_messages_without_source_ids():
    source = Message.from_text("user", "source", raw={"uuid": "source-user"})
    synthetic = Message.from_text("assistant", "summary")

    assert preserved_segment([source], [synthetic, source], anchor_uuid="boundary-1") == {
        "head_uuid": "source-user",
        "anchor_uuid": "boundary-1",
        "tail_uuid": "source-user",
    }
