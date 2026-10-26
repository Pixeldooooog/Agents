import { buildModelProfiles, listBuiltinTools } from "@kevin/core";
import type { HostServices } from "../services/hostServices.js";
import { resumeTerminalApproval } from "./terminalRunApproval.js";
import { TerminalModelProfiles } from "./terminalModelProfiles.js";
import { terminalCommandCatalog } from "./terminalCommandCatalog.js";
import { handleTerminalSlashCommand } from "./terminalSlashCommands.js";
import { TerminalSessionStore, transcriptMessages } from "./terminalSessionStore.js";
import { ScriptedTerminalTurns } from "./scriptedTerminalTurns.js";
import type { TerminalEventWriter } from "./terminalEventWriter.js";

export type TerminalHostCommandResult = "continue" | "exit";

export class TerminalHostSession {
  private previousRunId?: string;
  private activeTurn?: Promise<void>;
  private activeController?: AbortController;
  private readonly scriptedTurns: ScriptedTerminalTurns;
  private readonly terminalSessions: TerminalSessionStore;
  private readonly modelProfiles: TerminalModelProfiles;
  private readonly builtinToolNames: string[];

  constructor(
    private readonly repoRoot: string,
    private readonly services: HostServices,
    private readonly writer: TerminalEventWriter
  ) {
    this.scriptedTurns = new ScriptedTerminalTurns(writer);
    this.terminalSessions = new TerminalSessionStore(process.env.KEVIN_TERMINAL_SESSION_STORE || `${repoRoot}/.kevin/terminal-sessions`);
    this.modelProfiles = new TerminalModelProfiles(buildModelProfiles(services.settings));
    this.builtinToolNames = listBuiltinTools().map((tool) => tool.name);
  }

  ready(): void {
    this.writer.write({
      type: "ready",
      session_id: "ts-session",
      runtime: this.modelProfiles.runtimeInfo(),
      workspace: { path: this.services.settings.repoRoot, display: this.services.settings.repoRoot },
      profile: "coding",
      permission: "guarded",
      sandbox: "local",
      tools: this.builtinToolNames,
      commands: terminalCommandCatalog(),
      model_profiles: this.modelProfiles.list()
    });
  }

  async handleCommand(command: Record<string, unknown>): Promise<TerminalHostCommandResult> {
    const commandType = String(command.type || "");
    if (commandType === "exit") {
      await this.close();
      this.writer.write({ type: "exit" });
      return "exit";
    }
    if (commandType === "cancel") {
      this.activeController?.abort();
      this.scriptedTurns.cancel(String(command.reason || ""));
      return "continue";
    }
    if (commandType === "approval") {
      const approvals = objectField(command.approvals);
      const entries = Object.entries(approvals);
      const [approvalId, approved] = entries[0] ?? [];
      if (entries.length !== 1 || typeof approved !== "boolean") {
        this.writer.write({ type: "error", message: "exactly one approval ID and boolean decision are required" });
        return "continue";
      }
      if (approvalId === "fixture-approval") this.scriptedTurns.approval(String(command.run_id || "fixture-approval-run"), approved);
      else this.startTurn(async signal => {
        const runId = String(command.run_id || "");
        await resumeTerminalApproval(this.services, this.writer, runId, approvalId, approved, signal);
        if ((await this.services.store.loadRun(runId))?.status === "completed") this.previousRunId = runId;
      });
      return "continue";
    }
    if (commandType === "slash") {
      await handleTerminalSlashCommand(String(command.text || ""), this.slashCommandContext());
      return "continue";
    }
    if (commandType === "user_message") {
      this.startTurn(signal => this.userMessage(String(command.text || ""), String(command.run_id || newRunId()), signal));
      return "continue";
    }
    this.writer.write({ type: "error", message: `unknown terminal host command: ${commandType}` });
    return "continue";
  }

  async close(): Promise<void> {
    this.activeController?.abort();
    await this.activeTurn;
  }

  private startTurn(work: (signal: AbortSignal) => Promise<void>): void {
    if (this.activeTurn) { this.writer.write({ type: "error", message: "a terminal turn is already running" }); return; }
    const controller = new AbortController();
    this.activeController = controller;
    this.activeTurn = Promise.resolve().then(() => work(controller.signal)).catch(error => {
      this.writer.write({ type: "error", message: error instanceof Error ? error.message : "turn failed" });
    }).finally(() => { this.activeTurn = undefined; this.activeController = undefined; });
  }

  private async userMessage(text: string, runId: string, signal: AbortSignal): Promise<void> {
    if (this.scriptedTurns.handle(runId, text)) return;
    const spec = this.services.runs.specFromPayload({ message: text });
    const { run, result } = await this.services.runs.runAgent(spec, text, {
      signal,
      previousRunId: this.previousRunId,
      stream: true,
      afterRunStarted: (startedRun) => this.writer.write({ type: "turn_started", run_id: startedRun.run_id }),
      onEvent: (event) => this.writer.runtimeEvent(event)
    });
    if (result.status === "completed") this.previousRunId = run.run_id;
    this.writer.write({ type: "turn_finished", status: result.status, run_id: run.run_id });
  }

  private async resumeSession(sessionId: string): Promise<void> {
    if (this.activeTurn) throw new Error("cannot switch conversation while a turn is running");
    if (process.env.KEVIN_TERMINAL_FIXTURE !== "1") {
      const spec = this.services.runs.specFromPayload({ message: "" });
      const messages = await this.services.runs.conversationForRun(sessionId, spec);
      this.previousRunId = sessionId;
      this.writer.write({ type: "session_resumed", session_id: sessionId, messages: messages.filter(item => item.role === "user" || item.role === "assistant").map(item => ({ role: item.role, content: item.content })) });
      return;
    }
    const session = await this.terminalSessions.load(sessionId);
    if (!session) throw new Error(`session not found: ${sessionId}`);
    this.writer.write({ type: "session_resumed", session_id: session.session_id, messages: transcriptMessages(session) });
    if (session.pending_approval) this.writer.runtimeEvent(session.pending_approval);
  }

  private slashCommandContext() {
    return {
      services: this.services,
      writer: this.writer,
      sessions: this.terminalSessions,
      modelProfiles: this.modelProfiles,
      builtinToolNames: this.builtinToolNames,
      resumeSession: (sessionId: string) => this.resumeSession(sessionId)
    };
  }
}

function objectField(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function newRunId(): string {
  return `run_${crypto.randomUUID().replaceAll("-", "")}`;
}
