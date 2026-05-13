from __future__ import annotations

import json
from typing import Any

from agents.kernel.capabilities.sandbox.records import SandboxEventRecord, SandboxWorkspaceSnapshotRecord


def build_operation_frames(
    *,
    run_id: str,
    sandbox_events: list[SandboxEventRecord],
    sandbox_snapshots: list[SandboxWorkspaceSnapshotRecord],
    artifacts: list[Any] | None = None,
) -> list[dict[str, Any]]:
    snapshots_by_lease = _snapshots_by_lease(sandbox_snapshots)
    frames: list[dict[str, Any]] = []
    sequence = 0
    for event in sandbox_events:
        if event.event_type == "tool_started":
            args = _decode_json(event.payload.get("arguments"))
            frames.extend(
                [
                    _frame(event, run_id, sequence, "opening", args=args, step=("open app", _app_detail(event.tool_name, args))),
                    _frame(event, run_id, sequence + 1, "running", args=args, step=_active_step(event.tool_name, args)),
                ]
            )
            sequence += 2
        elif event.event_type == "tool_finished":
            args = _decode_json(event.payload.get("arguments"))
            result = _decode_json(event.payload.get("result"))
            snapshot = _nearest_snapshot(snapshots_by_lease.get(event.lease_id, []), event.created_at)
            diff = snapshot.diff if snapshot is not None else {}
            files = _files_from_diff(diff) or _files_from_args(args)
            failed = event.status == "error"
            frames.extend(
                [
                    _frame(
                        event,
                        run_id,
                        sequence,
                        "closing" if not failed else "error",
                        args=args,
                        result=result,
                        diff=diff,
                        files=files,
                        step=_closing_step(event.tool_name, failed),
                    ),
                    _frame(
                        event,
                        run_id,
                        sequence + 1,
                        "error" if failed else "done",
                        args=args,
                        result=result,
                        diff=diff,
                        files=files,
                        artifacts=artifacts or [],
                        step=_done_step(event.tool_name, failed),
                    ),
                ]
            )
            sequence += 2
    return frames


def _frame(
    event: SandboxEventRecord,
    run_id: str,
    sequence: int,
    phase: str,
    *,
    args: dict[str, Any],
    result: Any = None,
    diff: dict[str, Any] | None = None,
    files: list[dict[str, str]] | None = None,
    artifacts: list[Any] | None = None,
    step: tuple[str, str],
) -> dict[str, Any]:
    tool_name = event.tool_name or "workspace"
    target = _target_for(tool_name, args, result)
    payload: dict[str, Any] = {
        "id": "operation:%s:%s:%s" % (event.tool_call_id or tool_name, sequence, phase),
        "runId": event.run_id or run_id,
        "toolCallId": event.tool_call_id,
        "toolName": tool_name,
        "scene": _scene_for(tool_name),
        "phase": phase,
        "sequence": sequence,
        "source": "sandbox_trace",
        "title": _title_for(tool_name, phase),
        "target": target,
        "detail": _detail_for(tool_name, args, result),
        "argsPreview": _scrub(args),
        "resultPreview": _preview(result),
        "diffPreview": diff or {},
        "files": files or _files_from_args(args),
        "sources": _sources_from_result(result),
        "artifacts": artifacts or [],
        "stats": {"duration_ms": event.duration_ms} if event.duration_ms else {},
        "step": {"label": step[0], "detail": step[1]},
    }
    timestamp = round(event.created_at * 1000)
    if phase in {"opening", "running"}:
        payload["startedAt"] = timestamp
    else:
        payload["endedAt"] = timestamp
    return {key: value for key, value in payload.items() if value not in ("", None, [], {})}


def _decode_json(value: Any) -> Any:
    if not isinstance(value, str):
        return value if value is not None else {}
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _scrub(args: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(args, dict):
        return {}
    payload = dict(args)
    for key in list(payload):
        if any(marker in key.lower() for marker in ("key", "token", "secret", "password")):
            payload[key] = "[redacted]"
    return payload


def _preview(result: Any) -> Any:
    if isinstance(result, str):
        return result[:1200]
    return result


def _scene_for(tool_name: str) -> str:
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


def _title_for(tool_name: str, phase: str) -> str:
    action = {"opening": "Opening", "running": "Operating", "closing": "Closing", "done": "Completed", "error": "Failed"}.get(phase, "Operating")
    if tool_name.startswith("web."):
        return "%s web workspace" % action
    if tool_name.startswith(("shell.", "test.", "git.")):
        return "%s terminal" % action
    if tool_name.startswith(("filesystem.write", "filesystem.delete", "filesystem.move", "patch.")):
        return "%s editor" % action
    if tool_name.startswith(("skill.", "prompt.", "mcp.", "context.")):
        return "%s document reader" % action
    return "%s workspace" % action


def _target_for(tool_name: str, args: dict[str, Any], result: Any) -> str:
    if not isinstance(args, dict):
        return tool_name
    for key in ("path", "query", "url", "command", "name", "title", "task_id", "agent_id", "team_id"):
        if args.get(key):
            return str(args[key])
    if args.get("source_path") or args.get("destination_path"):
        return " -> ".join(str(args[key]) for key in ("source_path", "destination_path") if args.get(key))
    if isinstance(result, dict) and result.get("path"):
        return str(result["path"])
    return tool_name


def _detail_for(tool_name: str, args: dict[str, Any], result: Any) -> str:
    if tool_name.startswith("web."):
        return "Inspect web sources for %s" % _target_for(tool_name, args, result)
    if tool_name.startswith(("shell.", "test.", "git.")):
        return "Run command and collect output"
    if tool_name.startswith(("filesystem.write", "filesystem.delete", "filesystem.move", "patch.")):
        return "Apply workspace file change"
    if tool_name.startswith(("skill.", "prompt.", "mcp.", "context.")):
        return "Open context source and extract constraints"
    return "Read workspace state"


def _app_detail(tool_name: str, args: dict[str, Any]) -> str:
    scene = _scene_for(tool_name)
    app = {"web": "Browser", "browser": "Browser", "terminal": "Terminal", "git": "Git terminal", "edit": "Editor", "document": "Reader"}.get(scene, "Finder")
    return "Launch %s for %s" % (app, _target_for(tool_name, args, None))


def _active_step(tool_name: str, args: dict[str, Any]) -> tuple[str, str]:
    target = _target_for(tool_name, args, None)
    if tool_name.startswith("web."):
        return ("search sources", target)
    if tool_name.startswith(("shell.", "test.", "git.")):
        return ("execute command", target)
    if tool_name.startswith(("filesystem.write", "filesystem.delete", "filesystem.move", "patch.")):
        return ("edit file", target)
    if tool_name.startswith(("skill.", "prompt.", "mcp.", "context.")):
        return ("read source", target)
    return ("inspect workspace", target)


def _closing_step(tool_name: str, failed: bool) -> tuple[str, str]:
    return ("capture error" if failed else "capture evidence", "Persist tool output and workspace state")


def _done_step(tool_name: str, failed: bool) -> tuple[str, str]:
    return ("stop operation" if failed else "close window", "Return result for %s" % tool_name)


def _files_from_args(args: dict[str, Any]) -> list[dict[str, str]]:
    if not isinstance(args, dict):
        return []
    paths = [args.get("path"), args.get("source_path"), args.get("destination_path")]
    return [{"path": str(path), "status": "target"} for path in paths if path]


def _files_from_diff(diff: dict[str, Any]) -> list[dict[str, str]]:
    files: list[dict[str, str]] = []
    for status, paths in (diff or {}).items():
        if status not in {"created", "modified", "deleted"} or not isinstance(paths, list):
            continue
        files.extend({"path": str(path), "status": status} for path in paths[:6])
    return files[:12]


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


def _snapshots_by_lease(snapshots: list[SandboxWorkspaceSnapshotRecord]) -> dict[str, list[SandboxWorkspaceSnapshotRecord]]:
    grouped: dict[str, list[SandboxWorkspaceSnapshotRecord]] = {}
    for snapshot in snapshots:
        grouped.setdefault(snapshot.lease_id, []).append(snapshot)
    for items in grouped.values():
        items.sort(key=lambda item: item.created_at)
    return grouped


def _nearest_snapshot(snapshots: list[SandboxWorkspaceSnapshotRecord], before_time: float) -> SandboxWorkspaceSnapshotRecord | None:
    matches = [item for item in snapshots if item.phase == "after" and item.created_at <= before_time]
    return matches[-1] if matches else None
