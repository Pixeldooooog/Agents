import type { TerminalEventWriter } from "./terminalEventWriter.js";
import { ScriptedRunController } from "./scriptedRunController.js";

export class ScriptedTerminalTurns {
  private readonly runs: ScriptedRunController;

  constructor(private readonly writer: TerminalEventWriter) {
    this.runs = new ScriptedRunController(writer);
  }

  cancel(reason = ""): void {
    this.runs.cancel(reason);
  }

  approval(runId: string, approved: boolean): void {
    this.writer.runtimeEvent({
      type: "tool_approval_decision",
      name: "filesystem.write",
      payload: { approval_id: "fixture-approval", approved, scope: approved ? "allow_once" : "deny", tool_call: { id: "fixture-approval", name: "filesystem.write", arguments: { path: "fixture.txt" } } }
    });
    this.finishWithText(runId, approved ? "fixture approval granted" : "fixture approval denied");
  }

  handle(runId: string, text: string): boolean {
    if (text.startsWith("/large-paste-message")) return this.largePaste(runId);
    if (text.includes("approval")) return this.requestApproval(runId);
    if (text.includes("tool")) return this.toolTurn(runId);
    if (text.includes("retry")) return this.retryTurn(runId);
    if (text.includes("long")) return this.longTurn(runId);
    if (text.includes("done only")) return this.doneOnly(runId);
    if (text.includes("error")) return this.errorTurn(runId, "fixture runtime exploded");
    if (text.includes("loop exceeded")) return this.errorTurn(runId, "tool-call loop exceeded max iterations");
    if (text.includes("slow")) return this.slow(runId);
    if (text.includes("interruptible")) return this.interruptible(runId);
    if (text.includes("stream scroll")) return this.streamScroll(runId);
    if (text.includes("hang")) return this.hang(runId);
    if (text.includes("fixture") || process.env.AGENTS_TERMINAL_FIXTURE === "1") return this.normal(runId, text);
    return false;
  }

  private normal(runId: string, text: string): true {
    this.writer.write({ type: "turn_started", run_id: runId });
    this.finishWithText(runId, `fixture answer: ${text}`);
    return true;
  }

  private largePaste(runId: string): true {
    this.writer.write({ type: "turn_started", run_id: runId });
    this.finishWithText(runId, "large paste received");
    return true;
  }

  private toolTurn(runId: string): true {
    this.writer.write({ type: "turn_started", run_id: runId });
    this.writer.runtimeEvent({ type: "tool_start", name: "filesystem.read", payload: { id: "tool-read-1", name: "filesystem.read", arguments: { path: "fixture.txt" }, impact: { risk: "low" } } });
    this.writer.runtimeEvent({ type: "tool_result", name: "filesystem.read", payload: { tool_call_id: "tool-read-1", name: "filesystem.read", content: { path: "fixture.txt", content: "fixture file body" }, is_error: false } });
    this.finishWithText(runId, "tool turn complete");
    return true;
  }

  private retryTurn(runId: string): true {
    this.writer.write({ type: "turn_started", run_id: runId });
    this.writer.runtimeEvent({ type: "model_retry", name: "model", payload: { failed_attempt: 1, next_attempt: 2, max_attempts: 3, delay_seconds: 0.1, error: "fixture transient failure" } });
    this.finishWithText(runId, "fixture retry recovered");
    return true;
  }

  private longTurn(runId: string): true {
    this.writer.write({ type: "turn_started", run_id: runId });
    this.finishWithText(runId, Array.from({ length: 20 }, (_, index) => `long-line-${String(index + 1).padStart(2, "0")}`).join("\n"));
    return true;
  }

  private doneOnly(runId: string): true {
    this.writer.write({ type: "turn_started", run_id: runId });
    this.writer.runtimeEvent({ type: "done", name: "assistant", payload: { status: "finished", content: "done only answer", event_count: 1 } });
    this.writer.write({ type: "turn_finished", status: "finished", run_id: runId });
    return true;
  }

  private errorTurn(runId: string, message: string): true {
    this.writer.write({ type: "turn_started", run_id: runId });
    this.writer.runtimeEvent({ type: "error", name: "runtime", payload: { message } });
    this.writer.runtimeEvent({ type: "done", name: "assistant", payload: { status: "error", content: message, error: message, event_count: 1 } });
    this.writer.write({ type: "turn_finished", status: "error", run_id: runId });
    return true;
  }

  private requestApproval(runId: string): true {
    this.writer.write({ type: "turn_started", run_id: runId });
    this.writer.runtimeEvent({
      type: "tool_approval_required",
      name: "filesystem.write",
      payload: {
        approval_id: "fixture-approval",
        tool_call: { id: "fixture-approval", name: "filesystem.write", arguments: { path: "fixture.txt", content: "approved" } },
        impact: { risk: "writes a fixture file" },
        permission: { reason: "fixture approval smoke" }
      }
    });
    this.writer.runtimeEvent({ type: "done", name: "assistant", payload: { status: "awaiting_approval", content: "tool approval required", event_count: 2 } });
    this.writer.write({ type: "turn_finished", status: "awaiting_approval", run_id: runId });
    return true;
  }

  private slow(runId: string): true {
    this.runs.start(runId);
    this.writer.runtimeEvent({ type: "text_delta", name: "assistant", payload: { delta: "working slowly" } });
    this.runs.timer(() => this.runs.finish(runId, "finished"), 350);
    return true;
  }

  private interruptible(runId: string): true {
    this.runs.start(runId);
    this.writer.runtimeEvent({ type: "tool_start", name: "shell.run", payload: { id: "tool-shell-1", name: "shell.run", arguments: { command: "sleep 10" }, contract: { metadata: { interrupt_behavior: "cancel" } } } });
    return true;
  }

  private streamScroll(runId: string): true {
    this.runs.start(runId);
    const lines = Array.from({ length: 30 }, (_, index) => `stream-line-${String(index + 1).padStart(2, "0")}`);
    const emit = (index: number) => {
      if (!this.runs.isActive(runId)) return;
      this.writer.runtimeEvent({ type: "text_delta", name: "assistant", payload: { delta: `${index === 0 ? "" : "\n"}${lines[index]}` } });
      if (index + 1 < lines.length) this.runs.timer(() => emit(index + 1), 25);
      else this.runs.timer(() => {
        if (!this.runs.isActive(runId)) return;
        this.writer.runtimeEvent({ type: "model_message", name: "assistant", payload: { content: lines.join("\n") } });
        this.writer.runtimeEvent({ type: "done", name: "assistant", payload: { status: "finished", content: lines.join("\n"), event_count: 2 } });
        this.runs.finish(runId, "finished");
      }, 120);
    };
    emit(0);
    return true;
  }

  private hang(runId: string): true {
    this.runs.start(runId);
    this.writer.runtimeEvent({ type: "text_delta", name: "assistant", payload: { delta: "working until cancelled" } });
    return true;
  }

  private finishWithText(runId: string, text: string): void {
    this.writer.runtimeEvent({ type: "text_delta", name: "assistant", payload: { delta: text } });
    this.writer.runtimeEvent({ type: "model_message", name: "assistant", payload: { content: text } });
    this.writer.runtimeEvent({ type: "done", name: "assistant", payload: { status: "finished", content: text, event_count: 2 } });
    this.writer.write({ type: "turn_finished", status: "finished", run_id: runId });
  }
}
