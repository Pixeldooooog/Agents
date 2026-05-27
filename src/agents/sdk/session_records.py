from __future__ import annotations

import uuid
from datetime import datetime, timezone

from agents.kernel.schema import RuntimeEvent
from agents.kernel.state.runs import RunRecord
from agents.sdk.event_fields import _first_non_empty, _millis
from agents.sdk.file_rewind import _record_cwd
from agents.sdk.types import SDKSessionInfo, SDKUserMessage


def _user_message_event(
    prompt: str,
    *,
    session_id: str,
    run_id: str,
    user_message: SDKUserMessage | None = None,
) -> RuntimeEvent:
    message_id = str(getattr(user_message, "uuid", "") or "msg_%s" % uuid.uuid4().hex)
    message = (
        dict(user_message.message)
        if user_message is not None
        else {
            "role": "user",
            "content": [{"type": "text", "text": prompt}],
        }
    )
    timestamp = getattr(user_message, "timestamp", None) if user_message is not None else None
    return RuntimeEvent(
        type="user_message",
        name="user",
        payload={
            "uuid": message_id,
            "message_id": message_id,
            "session_id": session_id,
            "run_id": run_id,
            "message": message,
            "content": prompt,
            "parent_tool_use_id": getattr(user_message, "parent_tool_use_id", None) if user_message is not None else None,
            "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
            "isSynthetic": bool(getattr(user_message, "isSynthetic", False)) if user_message is not None else False,
            "tool_use_result": getattr(user_message, "tool_use_result", None) if user_message is not None else None,
            "priority": getattr(user_message, "priority", None) if user_message is not None else None,
            "isReplay": bool(getattr(user_message, "isReplay", True)) if user_message is not None else True,
        },
    )


def _session_infos_from_runs(records: list[RunRecord]) -> list[SDKSessionInfo]:
    grouped: dict[str, list[RunRecord]] = {}
    for record in records:
        grouped.setdefault(_session_id_for_run(record), []).append(record)
    infos = [_session_info_from_runs(items) for items in grouped.values()]
    return sorted(infos, key=lambda item: item.last_modified, reverse=True)


def _session_info_from_runs(records: list[RunRecord]) -> SDKSessionInfo:
    ordered = sorted(records, key=lambda item: item.created_at)
    latest = sorted(records, key=lambda item: item.updated_at, reverse=True)[0]
    metadata = dict(latest.metadata)
    custom_title = str(metadata.get("sdk_title") or metadata.get("custom_title") or metadata.get("title") or "")
    first_prompt = _first_non_empty(record.metadata.get("sdk_first_prompt", "") for record in ordered)
    summary = custom_title or first_prompt or latest.run_id
    info = SDKSessionInfo(
        sessionId=_session_id_for_run(latest),
        summary=summary,
        lastModified=_millis(latest.updated_at),
        createdAt=_millis(ordered[0].created_at),
        customTitle=custom_title or None,
        firstPrompt=first_prompt or None,
        cwd=_first_non_empty(_record_cwd(record) for record in reversed(ordered)),
        tag=str(metadata.get("sdk_tag") or metadata.get("tag") or ""),
    )
    info._status = latest.status.value
    info._latest_run_id = latest.run_id
    info._run_ids = [record.run_id for record in ordered]
    info._metadata = {**metadata, "run_count": len(records)}
    return info


def _session_id_for_run(record: RunRecord) -> str:
    return str(
        record.metadata.get("sdk_session_id")
        or record.metadata.get("file_history_session_id")
        or record.metadata.get("fileHistorySessionId")
        or record.run_id
    )


def _runtime_fields_from_run(record: RunRecord) -> tuple[str, str, list[str]]:
    spec = record.spec
    model_spec = spec.get("model") if isinstance(spec.get("model"), dict) else {}
    tools = spec.get("tools") if isinstance(spec.get("tools"), dict) else {}
    enabled_tools = spec.get("enabled_tools")
    if enabled_tools is None:
        enabled_tools = tools.get("enabled_tools") if isinstance(tools, dict) else []
    if not isinstance(enabled_tools, list):
        enabled_tools = []
    return (
        str(model_spec.get("model") or "") if isinstance(model_spec, dict) else "",
        str(model_spec.get("protocol") or "") if isinstance(model_spec, dict) else "",
        [str(item) for item in enabled_tools],
    )


def _duration_ms_from_record(record: RunRecord) -> int:
    return int(max(0, record.updated_at - record.created_at) * 1000)
