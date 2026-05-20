from __future__ import annotations

import json
import sys
import threading

write_lock = threading.Lock()

def write(payload):
    with write_lock:
        sys.stdout.write(json.dumps(payload, separators=(",", ":")) + "\n")
        sys.stdout.flush()


def runtime_event(event):
    write({"type": "runtime_event", "event": event})


def ready():
    write(
        {
            "type": "ready",
            "session_id": "fixture-session",
            "runtime": {"protocol": "fixture", "model": "terminal-flow", "model_profile": "fixture"},
            "workspace": {"path": ".", "display": "fixture-workspace"},
            "profile": "coding",
            "permission": "guarded",
            "sandbox": "fixture",
            "tools": ["filesystem.write", "shell.run"],
            "commands": [
                {"name": "/status", "description": "fixture status", "availability": "idle", "source": "fixture"},
                {"name": "/model", "description": "fixture model", "argumentHint": "<profile>", "availability": "idle", "source": "fixture"},
                {"name": "/sessions", "description": "fixture sessions", "availability": "idle", "source": "fixture"},
                {"name": "/session", "description": "fixture session", "availability": "idle", "source": "fixture"},
                {"name": "/agents", "description": "fixture agents", "availability": "idle", "source": "fixture"},
                {"name": "/tasks", "description": "fixture tasks", "availability": "idle", "source": "fixture"},
                {"name": "/capabilities", "description": "fixture capabilities", "availability": "idle", "source": "fixture"},
                {"name": "/plugins", "description": "fixture plugins", "availability": "idle", "source": "fixture"},
                {"name": "/permissions", "description": "fixture permissions", "availability": "idle", "source": "fixture"},
                {"name": "/prompt", "description": "fixture prompt", "availability": "idle", "source": "fixture"},
                {"name": "/skills", "description": "fixture skills", "availability": "idle", "source": "fixture"},
                {"name": "/mcp", "description": "fixture mcp", "availability": "idle", "source": "fixture"},
                {"name": "/memory", "description": "fixture memory", "availability": "idle", "source": "fixture"},
                {"name": "/exit", "description": "fixture exit", "availability": "always", "source": "fixture"},
            ],
            "model_profiles": [
                {"name": "fixture", "protocol": "fixture", "model": "terminal-flow", "configured": True, "active": True}
            ],
        }
    )


def finish_normal(run_id, text):
    write({"type": "turn_started", "run_id": run_id})
    runtime_event({"type": "text_delta", "name": "assistant", "payload": {"delta": "fixture answer: %s" % text}})
    runtime_event({"type": "model_message", "name": "assistant", "payload": {"content": "fixture answer: %s" % text}})
    runtime_event({"type": "done", "name": "assistant", "payload": {"status": "finished", "content": "fixture answer: %s" % text, "event_count": 2}})
    write({"type": "turn_finished", "status": "finished", "run_id": run_id})


def finish_large_paste_turn(run_id):
    write({"type": "turn_started", "run_id": run_id})
    runtime_event({"type": "text_delta", "name": "assistant", "payload": {"delta": "large paste received"}})
    runtime_event({"type": "model_message", "name": "assistant", "payload": {"content": "large paste received"}})
    runtime_event({"type": "done", "name": "assistant", "payload": {"status": "finished", "content": "large paste received", "event_count": 2}})
    write({"type": "turn_finished", "status": "finished", "run_id": run_id})


def finish_tool_turn(run_id):
    write({"type": "turn_started", "run_id": run_id})
    runtime_event(
        {
            "type": "tool_start",
            "name": "filesystem.read",
            "payload": {
                "id": "tool-read-1",
                "name": "filesystem.read",
                "arguments": {"path": "fixture.txt"},
                "impact": {"risk": "low"},
            },
        }
    )
    runtime_event(
        {
            "type": "tool_result",
            "name": "filesystem.read",
            "payload": {
                "tool_call_id": "tool-read-1",
                "name": "filesystem.read",
                "content": {"path": "fixture.txt", "content": "fixture file body"},
                "is_error": False,
            },
        }
    )
    runtime_event({"type": "text_delta", "name": "assistant", "payload": {"delta": "tool turn complete"}})
    runtime_event({"type": "model_message", "name": "assistant", "payload": {"content": "tool turn complete"}})
    runtime_event({"type": "done", "name": "assistant", "payload": {"status": "finished", "content": "tool turn complete", "event_count": 4}})
    write({"type": "turn_finished", "status": "finished", "run_id": run_id})


def finish_retry_turn(run_id):
    write({"type": "turn_started", "run_id": run_id})
    runtime_event(
        {
            "type": "model_retry",
            "name": "model",
            "payload": {"failed_attempt": 1, "next_attempt": 2, "max_attempts": 3, "delay_seconds": 0.1, "error": "fixture transient failure"},
        }
    )
    runtime_event({"type": "text_delta", "name": "assistant", "payload": {"delta": "fixture retry recovered"}})
    runtime_event({"type": "model_message", "name": "assistant", "payload": {"content": "fixture retry recovered"}})
    runtime_event({"type": "done", "name": "assistant", "payload": {"status": "finished", "content": "fixture retry recovered", "event_count": 2}})
    write({"type": "turn_finished", "status": "finished", "run_id": run_id})


def finish_long_turn(run_id):
    content = "\n".join("long-line-%02d" % index for index in range(1, 21))
    write({"type": "turn_started", "run_id": run_id})
    runtime_event({"type": "text_delta", "name": "assistant", "payload": {"delta": content}})
    runtime_event({"type": "model_message", "name": "assistant", "payload": {"content": content}})
    runtime_event({"type": "done", "name": "assistant", "payload": {"status": "finished", "content": content, "event_count": 2}})
    write({"type": "turn_finished", "status": "finished", "run_id": run_id})


def finish_done_only_turn(run_id):
    write({"type": "turn_started", "run_id": run_id})
    runtime_event({"type": "done", "name": "assistant", "payload": {"status": "finished", "content": "done only answer", "event_count": 1}})
    write({"type": "turn_finished", "status": "finished", "run_id": run_id})


def finish_error_turn(run_id):
    write({"type": "turn_started", "run_id": run_id})
    runtime_event({"type": "error", "name": "runtime", "payload": {"message": "fixture runtime exploded"}})
    runtime_event({"type": "done", "name": "assistant", "payload": {"status": "error", "content": "fixture runtime exploded", "error": "fixture runtime exploded", "event_count": 1}})
    write({"type": "turn_finished", "status": "error", "run_id": run_id})


def finish_tool_loop_turn(run_id):
    message = "tool-call loop exceeded max iterations"
    write({"type": "turn_started", "run_id": run_id})
    runtime_event({"type": "error", "name": "runtime", "payload": {"message": message}})
    runtime_event({"type": "done", "name": "assistant", "payload": {"status": "error", "content": message, "error": message, "event_count": 1}})
    write({"type": "turn_finished", "status": "error", "run_id": run_id})


def request_approval(run_id):
    write({"type": "turn_started", "run_id": run_id})
    runtime_event(
        {
            "type": "tool_approval_required",
            "name": "filesystem.write",
            "payload": {
                "approval_id": "fixture-approval",
                "tool_call": {
                    "id": "fixture-approval",
                    "name": "filesystem.write",
                    "arguments": {"path": "fixture.txt", "content": "approved"},
                },
                "impact": {"risk": "writes a fixture file"},
                "permission": {"reason": "fixture approval smoke"},
            },
        }
    )
    runtime_event({"type": "done", "name": "assistant", "payload": {"status": "awaiting_approval", "content": "tool approval required", "event_count": 2}})
    write({"type": "turn_finished", "status": "awaiting_approval", "run_id": run_id})


def finish_approval(run_id, approved):
    runtime_event(
        {
            "type": "tool_approval_decision",
            "name": "filesystem.write",
            "payload": {
                "approval_id": "fixture-approval",
                "approved": approved,
                "scope": "allow_once" if approved else "deny",
                "tool_call": {"id": "fixture-approval", "name": "filesystem.write", "arguments": {"path": "fixture.txt"}},
            },
        }
    )
    text = "fixture approval granted" if approved else "fixture approval denied"
    runtime_event({"type": "text_delta", "name": "assistant", "payload": {"delta": text}})
    runtime_event({"type": "model_message", "name": "assistant", "payload": {"content": text}})
    runtime_event({"type": "done", "name": "assistant", "payload": {"status": "finished", "content": text, "event_count": 4}})
    write({"type": "turn_finished", "status": "finished", "run_id": run_id})


def main():
    ready()
    active_run = ""
    active_lock = threading.Lock()

    def set_active(run_id):
        nonlocal active_run
        with active_lock:
            active_run = run_id

    def clear_active(run_id):
        nonlocal active_run
        with active_lock:
            if active_run == run_id:
                active_run = ""
                return True
            return False

    def current_active():
        with active_lock:
            return active_run

    def finish_slow(run_id):
        if clear_active(run_id):
            write({"type": "turn_finished", "status": "finished", "run_id": run_id})

    def finish_stream_scroll(run_id, content):
        if clear_active(run_id):
            runtime_event({"type": "model_message", "name": "assistant", "payload": {"content": content}})
            runtime_event({"type": "done", "name": "assistant", "payload": {"status": "finished", "content": content, "event_count": 2}})
            write({"type": "turn_finished", "status": "finished", "run_id": run_id})

    def stream_scroll_line(run_id, lines, index=0):
        if current_active() != run_id:
            return
        prefix = "" if index == 0 else "\n"
        runtime_event({"type": "text_delta", "name": "assistant", "payload": {"delta": prefix + lines[index]}})
        if index + 1 < len(lines):
            threading.Timer(0.025, stream_scroll_line, args=(run_id, lines, index + 1)).start()
            return
        threading.Timer(0.12, finish_stream_scroll, args=(run_id, "\n".join(lines))).start()

    for line in sys.stdin:
        if not line.strip():
            continue
        command = json.loads(line)
        command_type = str(command.get("type") or "")
        if command_type == "exit":
            write({"type": "exit"})
            return
        if command_type == "cancel":
            run_id = current_active()
            if run_id:
                clear_active(run_id)
                status = "canceled" if str(command.get("reason") or "") == "interrupt" else "cancelled"
                write({"type": "turn_finished", "status": status, "run_id": run_id})
            else:
                write({"type": "notice", "message": "nothing to cancel"})
            continue
        if current_active():
            write({"type": "error", "message": "run already active; use /cancel to interrupt"})
            continue
        if command_type == "slash":
            text = str(command.get("text") or "")
            if text == "/status":
                write({"type": "status", "status": {"runtime": "fixture", "state": "ok"}})
            elif text == "/diff":
                write({"type": "diff", "diff": [["M", "fixture.txt"]]})
            elif text == "/session":
                write({"type": "session", "session": [["session", "fixture-session"], ["active_run", "none"]]})
            elif text == "/agents":
                write({"type": "agents", "agents": [["fixture-agent", "Fixture Agent · model fixture/terminal-flow"]]})
            elif text == "/tasks":
                write({"type": "tasks", "tasks": [["fixture-task", "created · agent fixture-agent · Fixture task"]]})
            elif text == "/capabilities":
                write({"type": "capabilities", "capabilities": [["commands", "18"], ["tools", "2 enabled"]]})
            elif text == "/plugins":
                write({"type": "plugins", "plugins": [["fixture-plugin", "0.1.0 · fixture"]]})
            elif text == "/skills":
                write({"type": "skills", "skills": [["fixture-skill", "configured · fixture"]]})
            elif text == "/mcp":
                write({"type": "mcp", "mcp": [["server", "fixture"], ["tools", "1"]]})
            elif text == "/memory":
                write({"type": "memory", "memory": [["fixture-memory", "workspace · fixture memory"]]})
            elif text == "/permissions":
                write({"type": "permissions", "permissions": [["profile", "guarded"], ["runtime_mode", "auto"], ["approval_required", "filesystem.write"]]})
            elif text == "/prompt":
                write({"type": "prompt", "prompt": [["system_chars", "42"], ["included_fragments", "2"], ["layers", "system:1, skills:1"]]})
            elif text.startswith("/large-paste-message"):
                write({"type": "error", "message": "large paste was treated as a slash command"})
            else:
                write({"type": "notice", "message": "fixture slash: %s" % text})
            continue
        if command_type == "approval":
            approvals = command.get("approvals") if isinstance(command.get("approvals"), dict) else {}
            finish_approval(str(command.get("run_id") or "fixture-approval-run"), bool(approvals.get("fixture-approval")))
            continue
        if command_type == "user_message":
            run_id = str(command.get("run_id") or "fixture-run")
            text = str(command.get("text") or "")
            if text.startswith("/large-paste-message"):
                finish_large_paste_turn(run_id)
            elif "approval" in text:
                request_approval(run_id)
            elif "tool" in text:
                finish_tool_turn(run_id)
            elif "retry" in text:
                finish_retry_turn(run_id)
            elif "long" in text:
                finish_long_turn(run_id)
            elif "done only" in text:
                finish_done_only_turn(run_id)
            elif "error" in text:
                finish_error_turn(run_id)
            elif "loop exceeded" in text:
                finish_tool_loop_turn(run_id)
            elif "slow" in text:
                set_active(run_id)
                write({"type": "turn_started", "run_id": run_id})
                runtime_event({"type": "text_delta", "name": "assistant", "payload": {"delta": "working slowly"}})
                threading.Timer(0.35, finish_slow, args=(run_id,)).start()
            elif "interruptible" in text:
                set_active(run_id)
                write({"type": "turn_started", "run_id": run_id})
                runtime_event(
                    {
                        "type": "tool_start",
                        "name": "shell.run",
                        "payload": {
                            "id": "tool-shell-1",
                            "name": "shell.run",
                            "arguments": {"command": "sleep 10"},
                            "contract": {"metadata": {"interrupt_behavior": "cancel"}},
                        },
                    }
                )
            elif "stream scroll" in text:
                lines = ["stream-line-%02d" % index for index in range(1, 31)]
                set_active(run_id)
                write({"type": "turn_started", "run_id": run_id})
                stream_scroll_line(run_id, lines)
            elif "hang" in text:
                set_active(run_id)
                write({"type": "turn_started", "run_id": run_id})
                runtime_event({"type": "text_delta", "name": "assistant", "payload": {"delta": "working until cancelled"}})
            else:
                finish_normal(run_id, text)
            continue
        write({"type": "error", "message": "unknown fixture command: %s" % command_type})


if __name__ == "__main__":
    main()
