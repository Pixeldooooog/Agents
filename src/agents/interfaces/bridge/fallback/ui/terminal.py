from __future__ import annotations

from typing import Iterable

from rich.console import Console
from rich.text import Text

from agents.kernel.schema import RuntimeEvent
from agents.interfaces.bridge.fallback.ui.activity import ToolActivity, TurnActivity, plural
from agents.interfaces.bridge.fallback.ui.adapter import RuntimeEventAdapter
from agents.interfaces.bridge.fallback.ui.events import UIEvent
from agents.interfaces.bridge.fallback.ui import panels
from agents.interfaces.bridge.fallback.ui.format import (
    compact,
    tool_arguments,
)


class TerminalUI:
    def __init__(self, console: Console | None = None):
        self.console = console or Console(highlight=False)
        self.event_adapter = RuntimeEventAdapter()

    def startup(
        self,
        session,
        *,
        profile: str,
        permission: str,
        sandbox_provider: str,
        tools: Iterable[str],
        model_profile: str = "",
    ) -> None:
        panels.startup(self.console, session, profile=profile, permission=permission, sandbox_provider=sandbox_provider, tools=tools, model_profile=model_profile)

    def help(self) -> None:
        panels.help(self.console)

    def status(self, session, *, profile: str, permission: str, tools: Iterable[str], model_profile: str = "") -> None:
        panels.status(self.console, session, profile=profile, permission=permission, tools=tools, model_profile=model_profile)

    def model(self, session, profiles: Iterable[Any] = ()) -> None:
        panels.model(self.console, session, profiles=profiles)

    def model_switched(self, session, profile: str = "") -> None:
        runtime = "%s · %s" % (session.runtime.protocol, session.runtime.model)
        if profile:
            self.status_line("model", "switched to %s  profile %s" % (runtime, profile), "cyan")
            return
        self.status_line("model", "switched to %s" % runtime, "cyan")

    def doctor(
        self,
        session,
        *,
        profiles: Iterable[Any],
        tools: Iterable[str],
        env_file: str,
        model_profile: str = "",
    ) -> None:
        panels.doctor(self.console, session, profiles=profiles, tools=tools, env_file=env_file, model_profile=model_profile)

    def workspace(self, session) -> None:
        workspace = getattr(session, "workspace", None)
        if workspace is None:
            self.notice("No workspace is bound to this session.")
            return
        panels.workspace(self.console, session)

    def tools(self, tools: Iterable[str]) -> None:
        panels.tools(self.console, tools)

    def context(self, session) -> None:
        panels.context(self.console, session)

    def trace(self, session) -> None:
        panels.trace(self.console, session)

    def key_values(self, title: str, rows: dict[str, str]) -> None:
        panels.key_values(self.console, title, rows)

    def user_prompt_label(self) -> str:
        return "›"

    def user_prompt_suffix(self) -> str:
        return " "

    def assistant_prefix(self) -> None:
        return

    def assistant_delta(self, text: str, state: TurnActivity) -> None:
        value = str(text)
        while value:
            if not state.assistant_line_open:
                self.console.file.write("  ")
                state.assistant_line_open = True
            newline_index = value.find("\n")
            if newline_index < 0:
                self.console.file.write(value)
                break
            self.console.file.write(value[: newline_index + 1])
            state.assistant_line_open = False
            value = value[newline_index + 1 :]
        self.console.file.flush()

    def newline(self) -> None:
        self.console.print()

    def turn_started(self, session, state: TurnActivity | None = None) -> TurnActivity:
        state = state or TurnActivity()
        state.start_thinking()
        self.status_line("thinking", "%s · %s" % (session.runtime.protocol, session.runtime.model), "cyan")
        return state

    def retry(self, event: UIEvent) -> None:
        next_attempt = str(event.payload.get("next_attempt") or "?")
        max_attempts = str(event.payload.get("max_attempts") or "?")
        delay = float(event.payload.get("delay_seconds") or 0)
        error = compact(str(event.payload.get("error") or "model request failed"))
        self.status_line("retry", "model request %s/%s in %.1fs  %s" % (next_attempt, max_attempts, delay, error), "yellow")

    def turn_finished(self, *, status: str, state: TurnActivity) -> None:
        state.status = status
        self.finish_assistant_stream(state)
        self.flush_thinking(state)
        self.flush_tool_summary(state)
        if status == "finished" and state.tool_count and not state.assistant_after_tool:
            self.status_line("note", "no final answer after tool use", "yellow")
        elapsed = state.elapsed_seconds()
        suffix = " · %s" % plural(state.tool_count, "tool", "tools") if state.tool_count else ""
        style = "dim" if status in {"finished", "awaiting_approval"} else "red"
        label = "done" if status == "finished" else status.replace("_", " ")
        self.status_line(label, "%.1fs%s" % (elapsed, suffix), style)

    def runtime_event(self, event: RuntimeEvent, state: TurnActivity) -> None:
        ui_event = self.event_adapter.adapt(event)
        if ui_event is not None:
            self.ui_event(ui_event, state)

    def ui_event(self, event: UIEvent, state: TurnActivity) -> None:
        if event.type == "assistant_delta":
            if not state.wrote_text:
                self.flush_thinking(state)
                self.flush_tool_summary(state)
                self.assistant_prefix()
                state.wrote_text = True
            state.record_assistant_text()
            state.streamed_text = True
            self.assistant_delta(event.text, state)
            return
        if event.type == "thinking_delta":
            state.add_reasoning(event.text)
            return
        self.finish_assistant_stream(state)
        if event.type == "assistant_message" and event.text:
            self.flush_thinking(state)
            self.flush_tool_summary(state)
            self.assistant(event.text)
            state.record_assistant_text()
            state.printed_assistant = True
        elif event.type == "model_retry":
            self.retry(event)
        elif event.type == "tool_started":
            self.flush_thinking(state)
            self.tool_start(event, state)
        elif event.type == "tool_finished":
            self.tool_result(event, state)
        elif event.type == "approval_required":
            self.flush_thinking(state)
            self.flush_tool_summary(state)
            self.approval_request(event)
        elif event.type == "approval_decision":
            self.approval_decision(event.name, event.status)
        elif event.type == "error":
            self.flush_tool_summary(state)
            self.error(event.text)
        elif (
            event.type == "done"
            and event.status not in {"awaiting_approval", "error"}
            and event.text
            and not state.streamed_text
            and not state.printed_assistant
        ):
            self.flush_tool_summary(state)
            self.assistant(event.text)
            state.record_assistant_text()
            state.printed_assistant = True

    def assistant(self, content: str) -> None:
        lines = str(content).splitlines() or [""]
        for line in lines:
            self.console.print(Text.assemble(("  ", "dim"), line))

    def tool_start(self, event: UIEvent, state: TurnActivity) -> None:
        arguments = event.payload.get("arguments") or {}
        activity = ToolActivity(
            id=str(event.payload.get("id") or event.name),
            name=event.name,
            arguments=dict(arguments) if isinstance(arguments, dict) else {},
            risk=str(event.payload.get("risk") or "unknown"),
        )
        state.record_tool_start(activity)
        detail = activity.name
        args = tool_arguments(activity.arguments)
        if args:
            detail = "%s  %s" % (detail, args)
        self.status_line("tool", detail, "magenta")

    def tool_result(self, event: UIEvent, state: TurnActivity) -> None:
        is_error = bool(event.payload.get("is_error"))
        summary = state.record_tool_result(
            event.name,
            event.text,
            tool_id=str(event.payload.get("id") or ""),
            is_error=is_error,
        )
        style = "red" if is_error else "dim"
        self.result_line(summary, style)

    def flush_tool_summary(self, state: TurnActivity) -> None:
        if state.showed_tool_details:
            state.tool_stats = {}
            return
        summary = state.consume_tool_summary()
        if summary:
            self.status_line("tools", summary, "dim")

    def flush_thinking(self, state: TurnActivity) -> None:
        if not state.thinking_active:
            return
        state.thinking_active = False
        if state.reasoning_chars:
            self.status_line("reasoning", "%s chars" % state.reasoning_chars, "dim")

    def approval_request(self, event: UIEvent) -> None:
        self.status_line("approval", "%s · risk %s" % (event.name, str(event.payload.get("risk", "unknown"))), "yellow")
        args = compact(event.payload.get("arguments") or {})
        if args:
            self.result_line(args, "dim")

    def approval_decision(self, name: str, scope: str) -> None:
        self.status_line("approved", "%s %s" % (name, scope), "yellow")

    def notice(self, message: str) -> None:
        self.status_line("notice", message, "dim")

    def error(self, message: str) -> None:
        self.status_line("error", message, "red")

    def status_line(self, label: str, message: str, style: str = "dim", *, end: str = "\n") -> None:
        label_style = "bold %s" % style if style not in {"dim", "red"} else style
        text = Text("  ")
        text.append(label, style=label_style)
        if message:
            text.append(" ", style="dim")
            text.append(message, style=style)
        self.console.print(text, end=end)

    def result_line(self, message: str, style: str = "dim") -> None:
        self.console.print(Text.assemble(("    ↳ ", "dim"), (message, style)))

    def finish_assistant_stream(self, state: TurnActivity) -> None:
        if not state.wrote_text:
            return
        if state.assistant_line_open:
            self.newline()
        state.wrote_text = False
        state.assistant_line_open = False
