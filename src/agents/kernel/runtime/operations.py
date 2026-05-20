from __future__ import annotations

from typing import Any

from agents.kernel.schema import RuntimeEvent

OPERATION_SCENES = {"workspace", "edit", "web", "browser", "terminal", "git", "document", "summary"}


def build_runtime_operation_frames(run_id: str, events: list[RuntimeEvent]) -> list[dict[str, Any]]:
    frames: list[dict[str, Any]] = []
    for sequence, event in enumerate(events):
        frame = _frame_from_event(run_id, event, sequence)
        if frame:
            frames.append(frame)
    return frames


def _frame_from_event(run_id: str, event: RuntimeEvent, sequence: int) -> dict[str, Any]:
    if event.type not in {"tool_start", "tool_result", "tool_approval_required", "tool_approval_decision"}:
        return {}
    payload = dict(event.payload or {})
    call = _tool_call_payload(event)
    contract = dict(payload.get("contract") or {})
    tool_name = str(call.get("name") or payload.get("name") or event.name or "tool")
    tool_call_id = str(call.get("id") or payload.get("tool_call_id") or tool_name)
    phase = _phase_for_event(event)
    target = str(contract.get("target") or _target_from_call(call, payload) or "")
    result = payload.get("raw")
    if result is None:
        result = payload.get("result")
    if result is None:
        result = payload.get("content")
    frame = {
        "id": "runtime:%s:%s:%s" % (tool_call_id, sequence, phase),
        "runId": str(payload.get("run_id") or run_id),
        "toolCallId": tool_call_id,
        "toolName": tool_name,
        "scene": _scene_from_contract(tool_name, contract),
        "phase": phase,
        "sequence": sequence,
        "source": "runtime_contract",
        "title": _title_for_event(event, tool_name, contract, phase),
        "target": target,
        "detail": _detail_for_event(event, contract, payload),
        "argsPreview": _scrub(dict(call.get("arguments") or payload.get("arguments") or {})),
        "resultPreview": _preview(result),
        "files": [{"path": path, "status": "target"} for path in _paths_from_contract(contract)],
        "sources": _sources_from_result(result),
        "stats": {"contract": contract} if contract else {},
        "step": _step_for_event(event, target, contract),
    }
    return {key: value for key, value in frame.items() if value not in ("", None, [], {})}


def _tool_call_payload(event: RuntimeEvent) -> dict[str, Any]:
    payload = dict(event.payload or {})
    tool_call = payload.get("tool_call")
    if isinstance(tool_call, dict):
        return dict(tool_call)
    if event.type == "tool_result":
        return {
            "id": payload.get("tool_call_id", ""),
            "name": event.name,
            "arguments": {},
        }
    return payload


def _phase_for_event(event: RuntimeEvent) -> str:
    if event.type == "tool_start":
        return "opening"
    if event.type == "tool_result":
        return "error" if event.payload.get("is_error") else "done"
    if event.type == "tool_approval_required":
        return "running"
    if event.type == "tool_approval_decision":
        return "done" if event.payload.get("approved") else "error"
    return "running"


def _scene_from_contract(tool_name: str, contract: dict[str, Any]) -> str:
    activity = contract.get("activity") if isinstance(contract.get("activity"), dict) else {}
    kind = str(activity.get("kind") or "")
    if kind in OPERATION_SCENES:
        return kind
    return _scene_for_tool(tool_name)


def _scene_for_tool(tool_name: str) -> str:
    if tool_name.startswith(("filesystem.write", "filesystem.delete", "filesystem.move", "patch.")):
        return "edit"
    if tool_name.startswith("web."):
        return "web"
    if tool_name.startswith("browser."):
        return "browser"
    if tool_name.startswith(("shell.", "test.")):
        return "terminal"
    if tool_name.startswith("git."):
        return "git"
    if tool_name.startswith(("skill.", "prompt.", "mcp.", "context.", "todo.", "plan.", "task.", "schedule.", "workflow.", "agent.", "team.")):
        return "document"
    return "workspace"


def _title_for_event(event: RuntimeEvent, tool_name: str, contract: dict[str, Any], phase: str) -> str:
    activity = contract.get("activity") if isinstance(contract.get("activity"), dict) else {}
    title = str(activity.get("title") or "")
    if event.type == "tool_approval_required":
        return "Approval required: %s" % (title or tool_name)
    if event.type == "tool_approval_decision":
        return "Approved: %s" % (title or tool_name) if event.payload.get("approved") else "Denied: %s" % (title or tool_name)
    if title:
        return title
    verb = "Failed" if phase == "error" else "Completed" if phase == "done" else "Operating"
    return "%s %s" % (verb, tool_name)


def _detail_for_event(event: RuntimeEvent, contract: dict[str, Any], payload: dict[str, Any]) -> str:
    activity = contract.get("activity") if isinstance(contract.get("activity"), dict) else {}
    summary = str(activity.get("summary") or "")
    if summary:
        return summary
    if event.type == "tool_approval_required":
        permission = payload.get("permission") if isinstance(payload.get("permission"), dict) else {}
        return str(permission.get("reason") or "Waiting for user approval")
    if event.type == "tool_approval_decision":
        return str(payload.get("reason") or payload.get("scope") or "Approval decision recorded")
    return str(payload.get("content") or "")


def _step_for_event(event: RuntimeEvent, target: str, contract: dict[str, Any]) -> dict[str, str]:
    if event.type == "tool_start":
        return {"label": "start tool", "detail": target}
    if event.type == "tool_result":
        return {"label": "capture result", "detail": target}
    if event.type == "tool_approval_required":
        return {"label": "wait for approval", "detail": target}
    if event.type == "tool_approval_decision":
        return {"label": "resume after approval", "detail": target}
    return {}


def _target_from_call(call: dict[str, Any], payload: dict[str, Any]) -> str:
    args = call.get("arguments") if isinstance(call.get("arguments"), dict) else payload.get("arguments")
    if not isinstance(args, dict):
        return ""
    for key in ("path", "query", "url", "command", "name", "title", "task_id", "agent_id", "team_id"):
        if args.get(key):
            return str(args[key])
    if args.get("source_path") or args.get("destination_path"):
        return " -> ".join(str(args[key]) for key in ("source_path", "destination_path") if args.get(key))
    return ""


def _paths_from_contract(contract: dict[str, Any]) -> list[str]:
    paths = contract.get("paths")
    if not isinstance(paths, list):
        return []
    return [str(path) for path in paths if str(path)]


def _scrub(args: dict[str, Any]) -> dict[str, Any]:
    payload = dict(args)
    for key in list(payload):
        if any(marker in key.lower() for marker in ("key", "token", "secret", "password")):
            payload[key] = "[redacted]"
    return payload


def _preview(result: Any) -> Any:
    if isinstance(result, str):
        return result[:1200]
    return result


def _sources_from_result(result: Any) -> list[dict[str, Any]]:
    if not isinstance(result, dict) or not isinstance(result.get("sources"), list):
        return []
    return [
        {
            "title": str(source.get("title") or source.get("url") or "Source"),
            "url": str(source.get("url") or ""),
            "domain": str(source.get("domain") or ""),
            "content": str(source.get("content") or "")[:220],
            "score": source.get("score"),
        }
        for source in result["sources"][:6]
        if isinstance(source, dict)
    ]
