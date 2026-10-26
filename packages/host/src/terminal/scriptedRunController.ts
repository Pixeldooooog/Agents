import type { TerminalEventWriter } from "./terminalEventWriter.js";

type TimerHandle = ReturnType<typeof setTimeout>;

export class ScriptedRunController {
  private activeRun = "";
  private timers = new Set<TimerHandle>();

  constructor(private readonly writer: TerminalEventWriter) {}

  cancel(reason = ""): void {
    if (!this.activeRun) {
      this.writer.write({ type: "notice", message: "nothing to cancel" });
      return;
    }
    const runId = this.activeRun;
    this.activeRun = "";
    this.clearTimers();
    this.writer.write({ type: "turn_finished", status: "cancelled", ...(reason ? { reason } : {}), run_id: runId });
  }

  start(runId: string): void {
    this.activeRun = runId;
    this.writer.write({ type: "turn_started", run_id: runId });
  }

  finish(runId: string, status: string): void {
    if (!this.isActive(runId)) return;
    this.activeRun = "";
    this.writer.write({ type: "turn_finished", status, run_id: runId });
  }

  isActive(runId: string): boolean {
    return this.activeRun === runId;
  }

  timer(callback: () => void, delay: number): void {
    const timer = setTimeout(() => {
      this.timers.delete(timer);
      callback();
    }, delay);
    this.timers.add(timer);
  }

  private clearTimers(): void {
    for (const timer of this.timers) clearTimeout(timer);
    this.timers.clear();
  }
}
