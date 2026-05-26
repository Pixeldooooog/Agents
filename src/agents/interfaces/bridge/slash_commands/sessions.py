from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agents.interfaces.bridge.payloads import (
    context_payload,
    messages_payload,
    parse_positive_int,
    session_payload,
    session_records_payload,
    short_session_id,
    status_payload,
)
from agents.interfaces.bridge.sessions import save_session_snapshot
from agents.interfaces.bridge.slash_commands.common import (
    BridgeWriter,
    error_message,
    safe_file_stem,
    split_once,
    tool_context,
)
from agents.kernel.capabilities.tools.builtin.session_context import session_summary


async def handle_resume_command(state: Any, argument: str, *, write: BridgeWriter) -> None:
    record = state.session_store.load(argument)
    if record is None:
        write({"type": "error", "message": "session not found: %s" % argument})
        return
    state.session.messages = list(record.messages)
    _sync_session_prompt_from_messages(state.session)
    state.session_id = record.session_id
    write({"type": "session_resumed", "session_id": record.session_id, "messages": messages_payload(record.messages)})
    write(
        {
            "type": "notice",
            "message": "resumed %s · %s messages" % (short_session_id(record.session_id), record.message_count),
        }
    )
    write({"type": "status", "status": status_payload(state)})
    if record.pending_run_id and record.pending_approval:
        await _restore_pending_approval(state, record, write=write)


def handle_sessions_command(state: Any, argument: str, *, write: BridgeWriter) -> None:
    action, rest = split_once(argument)
    if action in {"delete", "remove", "forget"}:
        target = rest.strip()
        if not target:
            write({"type": "error", "message": "usage: /sessions delete <id>"})
            return
        record = state.session_store.delete(target)
        if record is None:
            write({"type": "error", "message": "session not found: %s" % target})
            return
        write({"type": "notice", "message": "session deleted: %s" % short_session_id(record.session_id)})
        write({"type": "sessions", "sessions": session_records_payload(state.session_store.list())})
        return
    write({"type": "error", "message": "unknown sessions command: %s" % action})


def handle_export_command(state: Any, argument: str, *, write: BridgeWriter) -> None:
    try:
        export_format, target = _parse_export_argument(state, argument)
        content = _session_export_content(state, export_format)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    except Exception as exc:  # noqa: BLE001 - command output should surface export failures.
        write({"type": "error", "message": "session export failed: %s" % exc})
        return
    write({"type": "notice", "message": "session exported: %s" % _display_export_path(state, target)})
    write({"type": "session", "session": session_payload(state)})


def handle_fork_command(state: Any, argument: str, *, write: BridgeWriter) -> None:
    keep_count = parse_positive_int(argument) if argument.strip() else None
    if argument.strip() and keep_count is None:
        write({"type": "error", "message": "usage: /fork [non_system_message_count]"})
        return
    messages = _fork_messages(list(getattr(state.session, "messages", []) or []), keep_count)
    if not messages:
        write({"type": "error", "message": "session has no messages to fork"})
        return
    state.session_id = state.session_store.new_session_id()
    state.session.messages = messages
    save_session_snapshot(state)
    write({"type": "notice", "message": "forked session: %s" % short_session_id(state.session_id)})
    write({"type": "session_resumed", "session_id": state.session_id, "messages": messages_payload(messages)})
    write({"type": "status", "status": status_payload(state)})


def handle_rewind_command(state: Any, argument: str, *, write: BridgeWriter) -> None:
    if argument.strip():
        drop_count = parse_positive_int(argument)
        if drop_count is None:
            write({"type": "error", "message": "usage: /rewind [drop_last_non_system_count]"})
            return
    else:
        drop_count = 1
    messages, dropped = _rewind_messages(list(getattr(state.session, "messages", []) or []), drop_count)
    state.session.messages = messages
    save_session_snapshot(state)
    write({"type": "notice", "message": "rewound %s message%s" % (dropped, "" if dropped == 1 else "s")})
    write({"type": "session_resumed", "session_id": state.session_id, "messages": messages_payload(messages)})
    write({"type": "context", "context": context_payload(state)})


def handle_compact_command(state: Any, argument: str, *, write: BridgeWriter) -> None:
    compact = getattr(state.session, "compact", None)
    if compact is None:
        write({"type": "error", "message": "context compaction is not available"})
        return
    target_tokens = parse_positive_int(argument)
    stats = compact(target_tokens)
    save_session_snapshot(state)
    dropped = int(stats.get("dropped_messages", 0))
    write({"type": "notice", "message": "compacted %s message%s" % (dropped, "" if dropped == 1 else "s")})
    write({"type": "context", "context": {key: str(value) for key, value in stats.items()}})


def handle_summary_command(state: Any, argument: str, *, write: BridgeWriter) -> None:
    context = tool_context(state)
    if context is None:
        write({"type": "error", "message": "tool context is not available"})
        return
    max_messages = parse_positive_int(argument) or 50
    try:
        payload = session_summary(context, max_messages=max_messages)
    except Exception as exc:  # noqa: BLE001 - slash commands report tool-facing errors.
        write({"type": "error", "message": error_message(exc)})
        return
    rows = [
        ["summary", str(payload.get("summary") or "")],
        ["messages", "%s / %s" % (payload.get("messages", 0), payload.get("total", 0))],
        ["roles", ", ".join("%s=%s" % (role, count) for role, count in dict(payload.get("roles") or {}).items()) or "-"],
    ]
    write({"type": "session", "session": rows})


def handle_context_command(state: Any, argument: str, *, write: BridgeWriter) -> None:
    action, rest = split_once(argument)
    if not action:
        write({"type": "context", "context": context_payload(state)})
        return
    if action == "messages":
        write({"type": "context_messages", "messages": _context_message_rows(state)})
        return
    if action == "drop":
        count = parse_positive_int(rest) or 0
        if count <= 0:
            write({"type": "error", "message": "usage: /context drop <count>"})
            return
        dropped = _drop_context_messages(state, count)
        save_session_snapshot(state)
        write({"type": "notice", "message": "dropped %s context message%s" % (dropped, "" if dropped == 1 else "s")})
        write({"type": "context", "context": context_payload(state)})
        return
    write({"type": "error", "message": "unknown context command: %s" % action})


async def _restore_pending_approval(state: Any, record: Any, *, write: BridgeWriter) -> None:
    checkpoint = getattr(record, "checkpoint", None)
    save = getattr(getattr(getattr(state, "persistence", None), "checkpoints", None), "save", None)
    if checkpoint is not None and save is not None:
        try:
            await save(checkpoint)
        except Exception:
            pass
    event = dict(record.pending_approval)
    payload = dict(event.get("payload") or {})
    payload["run_id"] = record.pending_run_id
    event["payload"] = payload
    write({"type": "runtime_event", "event": event})


def _sync_session_prompt_from_messages(session: Any) -> None:
    messages = list(getattr(session, "messages", []) or [])
    prompt = ""
    if messages and getattr(messages[0], "role", "") == "system":
        prompt = messages[0].content_text()
    context_window = getattr(session, "context_window", None)
    if context_window is not None:
        context_window.system_prompt = str(prompt or "").strip()


def _context_message_rows(state: Any) -> list[list[str]]:
    rows: list[list[str]] = []
    for index, message in enumerate(list(getattr(state.session, "messages", []) or [])[-30:]):
        role = str(getattr(message, "role", ""))
        content = message.content_text() if hasattr(message, "content_text") else str(message)
        rows.append([str(index), "%s · %s" % (role, content.replace("\n", " ")[:160])])
    return rows or [["messages", "none"]]


def _drop_context_messages(state: Any, count: int) -> int:
    messages = list(getattr(state.session, "messages", []) or [])
    kept: list[Any] = []
    dropped = 0
    for message in messages:
        if dropped < count and getattr(message, "role", "") != "system":
            dropped += 1
            continue
        kept.append(message)
    state.session.messages = kept
    return dropped


def _parse_export_argument(state: Any, argument: str) -> tuple[str, Path]:
    first, rest = split_once(argument)
    if first in {"json", "markdown", "md"}:
        export_format = "markdown" if first in {"markdown", "md"} else "json"
        requested = rest.strip()
    else:
        export_format = "json"
        requested = str(argument or "").strip()
    suffix = "md" if export_format == "markdown" else "json"
    workspace = Path(getattr(state, "active_workspace", "") or ".").expanduser().resolve()
    if requested:
        raw_target = Path(requested)
        if raw_target.is_absolute():
            raise ValueError("export path must be workspace-relative")
        target = (workspace / raw_target).resolve()
    else:
        safe_session = safe_file_stem(str(getattr(state, "session_id", "") or "session")) or "session"
        target = (workspace / ".agents" / "exports" / ("%s.%s" % (safe_session, suffix))).resolve()
    try:
        target.relative_to(workspace)
    except ValueError as exc:
        raise ValueError("export path must stay inside the workspace") from exc
    if target.suffix == "":
        target = target.with_suffix("." + suffix)
    return export_format, target


def _session_export_content(state: Any, export_format: str) -> str:
    messages = list(getattr(state.session, "messages", []) or [])
    runtime = getattr(state.session, "runtime", None)
    payload = {
        "session_id": str(getattr(state, "session_id", "") or ""),
        "profile": str(getattr(state, "profile", "") or ""),
        "model": {
            "protocol": str(getattr(runtime, "protocol", "") or ""),
            "model": str(getattr(runtime, "model", "") or ""),
        },
        "workspace_path": str(getattr(state, "active_workspace", "") or ""),
        "message_count": len(messages),
        "messages": [_export_message_payload(message) for message in messages],
    }
    if export_format == "json":
        return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    lines = [
        "# Session %s" % (payload["session_id"] or "export"),
        "",
        "- Profile: %s" % (payload["profile"] or "-"),
        "- Model: %s / %s" % (payload["model"]["protocol"] or "-", payload["model"]["model"] or "-"),
        "- Workspace: %s" % (payload["workspace_path"] or "-"),
        "- Messages: %s" % payload["message_count"],
        "",
    ]
    for message in messages:
        lines.extend(["## %s" % str(getattr(message, "role", "") or "message"), "", _message_text(message), ""])
    return "\n".join(lines).rstrip() + "\n"


def _export_message_payload(message: Any) -> dict[str, Any]:
    if hasattr(message, "to_dict"):
        return message.to_dict()
    return {"role": getattr(message, "role", ""), "content": _message_text(message)}


def _display_export_path(state: Any, target: Path) -> str:
    workspace = Path(getattr(state, "active_workspace", "") or ".").expanduser().resolve()
    try:
        return str(target.resolve().relative_to(workspace))
    except Exception:
        return str(target)


def _message_text(message: Any) -> str:
    content_text = getattr(message, "content_text", None)
    if content_text is not None:
        return str(content_text() or "")
    return str(getattr(message, "content", "") or "")


def _fork_messages(messages: list[Any], keep_non_system: int | None) -> list[Any]:
    if keep_non_system is None:
        return list(messages)
    kept: list[Any] = []
    seen = 0
    for message in messages:
        if getattr(message, "role", "") == "system":
            kept.append(message)
            continue
        if seen < keep_non_system:
            kept.append(message)
            seen += 1
    return kept


def _rewind_messages(messages: list[Any], drop_count: int) -> tuple[list[Any], int]:
    kept = list(messages)
    dropped = 0
    index = len(kept) - 1
    while index >= 0 and dropped < drop_count:
        if getattr(kept[index], "role", "") != "system":
            kept.pop(index)
            dropped += 1
        index -= 1
    return kept, dropped
