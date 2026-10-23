import { buildModelProfiles, listBuiltinTools } from "@agents/core";
import type { HostServices } from "../services/hostServices.js";
import { TerminalModelProfiles } from "./terminalModelProfiles.js";
import { terminalCommandCatalog } from "./terminalCommandCatalog.js";
import { handleTerminalSlashCommand } from "./terminalSlashCommands.js";
import { TerminalSessionStore, transcriptMessages } from "./terminalSessionStore.js";
import { ScriptedTerminalTurns } from "./scriptedTerminalTurns.js";
import type { TerminalEventWriter } from "./terminalEventWriter.js";

export type TerminalHostCommandResult = "continue" | "exit";

export class TerminalHostSession {
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
    this.terminalSessions = new TerminalSessionStore(process.env.AGENTS_TERMINAL_SESSION_STORE || `${repoRoot}/.agents/terminal-sessions`);
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
      this.writer.write({ type: "exit" });
      return "exit";
    }
    if (commandType === "cancel") {
      this.scriptedTurns.cancel(String(command.reason || ""));
      return "continue";
    }
    if (commandType === "approval") {
      const approvals = objectField(command.approvals);
      this.scriptedTurns.approval(String(command.run_id || "fixture-approval-run"), Object.values(approvals).some(Boolean));
      return "continue";
    }
    if (commandType === "slash") {
      await handleTerminalSlashCommand(String(command.text || ""), this.slashCommandContext());
      return "continue";
    }
    if (commandType === "user_message") {
      await this.userMessage(String(command.text || ""), String(command.run_id || newRunId()));
      return "continue";
    }
    this.writer.write({ type: "error", message: `unknown terminal host command: ${commandType}` });
    return "continue";
  }

  private async userMessage(text: string, runId: string): Promise<void> {
    if (this.scriptedTurns.handle(runId, text)) return;
    const spec = this.services.runs.specFromPayload({ message: text });
    const { run, result } = await this.services.runs.runAgent(spec, text, {
      stream: true,
      afterRunStarted: (startedRun) => this.writer.write({ type: "turn_started", run_id: startedRun.run_id }),
      onEvent: (event) => this.writer.runtimeEvent(event)
    });
    this.writer.write({ type: "turn_finished", status: result.status, run_id: run.run_id });
  }

  private async resumeSession(sessionId: string): Promise<void> {
    const session = await this.terminalSessions.load(sessionId);
    if (!session) {
      this.writer.write({ type: "error", message: `session not found: ${sessionId}` });
      return;
    }
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
