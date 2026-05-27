from __future__ import annotations

from agents.kernel.schema import RuntimeEvent
from agents.sdk.event_artifacts import _files_persisted_from_tool_result
from agents.sdk.event_auth import _auth_status_from_tool_result
from agents.sdk.event_fields import (
    _duration_ms,
    _first_non_empty,
    _float,
    _int,
    _is_sdk_interrupt_cancel,
    _json_list,
    _json_object,
    _millis,
    _nullable_text_field,
    _string_list_field,
    _text_field,
    _truncate,
)
from agents.sdk.event_messages import (
    _project_runtime_event,
    _project_session_state_event,
    _session_state_event,
)
from agents.sdk.event_payloads import _tool_contract, _tool_result_payload_data
from agents.sdk.event_tasks import _task_messages_from_tool_result
from agents.sdk.types import SDKMessage


def _project_runtime_event_messages(
    event: RuntimeEvent,
    *,
    session_id: str,
    run_id: str,
    duration_ms: int,
    num_turns: int,
) -> list[SDKMessage]:
    message = _project_runtime_event(
        event,
        session_id=session_id,
        run_id=run_id,
        duration_ms=duration_ms,
        num_turns=num_turns,
    )
    messages = [] if message is None else [message]
    auth_status = _auth_status_from_tool_result(event, session_id=session_id, run_id=run_id)
    if auth_status is not None:
        messages.append(auth_status)
    messages.extend(_task_messages_from_tool_result(event, session_id=session_id, run_id=run_id))
    files_persisted = _files_persisted_from_tool_result(event, session_id=session_id, run_id=run_id)
    if files_persisted is not None:
        messages.append(files_persisted)
    return messages


__all__ = [
    "_duration_ms",
    "_first_non_empty",
    "_float",
    "_int",
    "_is_sdk_interrupt_cancel",
    "_json_list",
    "_json_object",
    "_millis",
    "_nullable_text_field",
    "_project_runtime_event",
    "_project_runtime_event_messages",
    "_project_session_state_event",
    "_session_state_event",
    "_string_list_field",
    "_text_field",
    "_tool_contract",
    "_tool_result_payload_data",
    "_truncate",
]
