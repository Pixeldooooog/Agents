from agents.kernel.schema import RuntimeEvent
from agents.sdk import validate_sdk_message
from agents.sdk.client import _project_runtime_event_messages
from agents.sdk.types import SDKModelRecoveryMessage


def test_sdk_projects_model_recovery_runtime_events():
    [message] = _project_runtime_event_messages(
        RuntimeEvent(
            type="model_recovery",
            name="max_output_tokens",
            payload={
                "uuid": "recovery-1",
                "attempt": 1,
                "max_attempts": 3,
                "stop_reason": "max_tokens",
                "message": "continuing after model output limit",
            },
        ),
        session_id="session-1",
        run_id="run-1",
        duration_ms=0,
        num_turns=1,
    )

    assert isinstance(message, SDKModelRecoveryMessage)
    assert message.type == "system"
    assert message.subtype == "model_recovery"
    assert message.uuid == "recovery-1"
    assert message.reason == "max_output_tokens"
    assert message.attempt == 1
    assert message.max_attempts == 3
    assert message.stop_reason == "max_tokens"
    assert message.message == "continuing after model output limit"
    assert validate_sdk_message(message.model_dump()) == message
