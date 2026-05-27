from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from agents.kernel.schema import RuntimeEvent
from agents.sdk.event_fields import _first_non_empty
from agents.sdk.event_payloads import _tool_result_payload_data
from agents.sdk.types import SDKFilesPersistedMessage


def _files_persisted_from_tool_result(
    event: RuntimeEvent,
    *,
    session_id: str,
    run_id: str,
) -> SDKFilesPersistedMessage | None:
    if event.type != "tool_result":
        return None
    payload = _tool_result_payload_data(event.payload)
    artifacts = _artifact_payloads(payload)
    failed = _artifact_failures(payload)
    if not artifacts and not failed:
        return None
    processed_at = _first_non_empty(_artifact_processed_at(artifact) for artifact in artifacts)
    return SDKFilesPersistedMessage(
        session_id=session_id,
        run_id=run_id,
        files=[
            {
                "filename": _artifact_filename(artifact),
                "file_id": str(artifact.get("artifact_id") or artifact.get("file_id") or artifact.get("id") or ""),
            }
            for artifact in artifacts
        ],
        failed=failed,
        processed_at=processed_at or datetime.now(timezone.utc).isoformat(),
    )


def _artifact_payloads(payload: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    artifact = payload.get("artifact")
    if isinstance(artifact, dict):
        result.append(dict(artifact))
    for key in ("artifacts", "files"):
        values = payload.get(key)
        if isinstance(values, list):
            result.extend(dict(item) for item in values if isinstance(item, dict))
    return [item for item in result if item.get("artifact_id") or item.get("file_id") or item.get("id")]


def _artifact_failures(payload: dict[str, Any]) -> list[dict[str, str]]:
    values = payload.get("failed") or payload.get("failed_files") or []
    if not isinstance(values, list):
        return []
    failed: list[dict[str, str]] = []
    for item in values:
        if isinstance(item, dict):
            failed.append(
                {
                    "filename": str(item.get("filename") or item.get("path") or item.get("uri") or ""),
                    "error": str(item.get("error") or item.get("message") or ""),
                }
            )
    return failed


def _artifact_filename(artifact: dict[str, Any]) -> str:
    for key in ("filename", "workspace_path", "path", "uri"):
        value = str(artifact.get(key) or "")
        if value:
            return value.rsplit("/", 1)[-1] if key == "uri" else value
    return str(artifact.get("artifact_id") or artifact.get("file_id") or "artifact")


def _artifact_processed_at(artifact: dict[str, Any]) -> str:
    value = artifact.get("processed_at") or artifact.get("created_at")
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)) and value:
        return datetime.fromtimestamp(float(value), timezone.utc).isoformat()
    return ""
