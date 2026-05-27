from __future__ import annotations

from typing import Any

from agents.kernel.schema import RuntimeEvent
from agents.sdk.event_payloads import _tool_result_payload_data
from agents.sdk.types import SDKAuthStatusMessage


def _auth_status_from_tool_result(
    event: RuntimeEvent,
    *,
    session_id: str,
    run_id: str,
) -> SDKAuthStatusMessage | None:
    if not _is_auth_tool_result(event):
        return None
    payload = _tool_result_payload_data(event.payload)
    status = str(payload.get("status") or "")
    auth_url = str(payload.get("authUrl") or payload.get("auth_url") or "")
    message = str(payload.get("message") or "")
    output = [item for item in [message, auth_url] if item]
    if not output and status:
        output = [status]
    error = message if status in {"error", "unsupported"} else ""
    return SDKAuthStatusMessage(
        session_id=session_id,
        run_id=run_id,
        is_authenticating=status == "auth_url",
        output=output,
        error=error,
        metadata={key: value for key, value in payload.items() if key != "_meta"},
    )


def _is_auth_tool_result(event: RuntimeEvent) -> bool:
    if event.type != "tool_result":
        return False
    if str(event.name).endswith("__authenticate"):
        return True
    contract = event.payload.get("contract")
    metadata: Any = contract.get("metadata") if isinstance(contract, dict) else {}
    return bool(isinstance(metadata, dict) and metadata.get("auth_tool"))
