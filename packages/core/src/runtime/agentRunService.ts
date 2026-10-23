import type { Settings } from "../config/settings.js";
import { profileDefaults } from "../models/modelProfiles.js";
import type { JsonStateStore } from "../store/jsonStateStore.js";
import type { AgentChatPayload, AgentSpec } from "../types/agentTypes.js";
import { specFromPayload } from "../types/agentTypes.js";
import type { AgentResult, RunRecord, RunStatus, RuntimeEvent } from "../types/runtimeTypes.js";
import { AgentRuntime } from "./agentRuntime.js";
import type { RuntimeOptions } from "./runtimeOptions.js";

export type AgentRunServiceOptions = {
  settings: Settings;
  store: JsonStateStore;
  taskRunner?: RuntimeOptions["taskRunner"];
  mcpProviders?: RuntimeOptions["mcpProviders"];
  lspProvider?: RuntimeOptions["lspProvider"];
  agentRunner?: RuntimeOptions["agentRunner"];
};

export type AgentRunExecutionOptions = {
  stream?: boolean;
  signal?: AbortSignal;
  fileReadState?: RuntimeOptions["fileReadState"];
  sleepWake?: RuntimeOptions["sleepWake"];
  afterRunStarted?: (run: RunRecord) => void | Promise<void>;
  onEvent?: (event: RuntimeEvent) => void | Promise<void>;
};

export type AgentApprovalResumeOptions = AgentRunExecutionOptions & {
  spec?: AgentSpec;
};

export type PersistedAgentRun = {
  run: RunRecord;
  result: AgentResult;
  events: RuntimeEvent[];
};

export type AgentRunServiceErrorCode = "run_not_found" | "run_not_awaiting_approval" | "pending_approval_missing";

export class AgentRunServiceError extends Error {
  constructor(
    readonly code: AgentRunServiceErrorCode,
    message: string,
    readonly statusCode: number
  ) {
    super(message);
    this.name = "AgentRunServiceError";
  }
}

export class AgentRunService {
  constructor(private readonly options: AgentRunServiceOptions) {}

  specFromPayload(payload: Partial<AgentChatPayload>): AgentSpec {
    return specFromPayload(payload, profileDefaults(this.options.settings));
  }

  async runPayload(payload: AgentChatPayload, options: AgentRunExecutionOptions = {}): Promise<PersistedAgentRun> {
    return this.runAgent(this.specFromPayload(payload), payload.message, options);
  }

  async runAgent(spec: AgentSpec, message: string, options: AgentRunExecutionOptions = {}): Promise<PersistedAgentRun> {
    const run = await this.options.store.startRun(spec);
    await options.afterRunStarted?.(run);
    const events: RuntimeEvent[] = [];
    const runtime = this.runtimeFor(run.run_id, events, options);
    const result = await runtime.run(spec, message, run.run_id);
    await persistAgentRunOutcome(this.options.store, run.run_id, result);
    return {
      run: await this.loadCurrentRun(run),
      result,
      events
    };
  }

  async resumeApproval(runId: string, approved: boolean, options: AgentApprovalResumeOptions = {}): Promise<PersistedAgentRun> {
    const run = await this.requireApprovalRun(runId);
    const spec = options.spec || this.specFromPayload({ message: "", ...run.spec });
    const events: RuntimeEvent[] = [];
    const runtime = this.runtimeFor(runId, events, options);
    const result = await runtime.resumeWithApproval(spec, run.pending_approval!, approved, runId);
    await persistAgentRunOutcome(this.options.store, runId, result);
    return {
      run: await this.loadCurrentRun(run),
      result,
      events
    };
  }

  private runtimeFor(runId: string, events: RuntimeEvent[], options: AgentRunExecutionOptions): AgentRuntime {
    return new AgentRuntime({
      settings: this.options.settings,
      store: this.options.store,
      taskRunner: this.options.taskRunner,
      mcpProviders: this.options.mcpProviders,
      lspProvider: this.options.lspProvider,
      agentRunner: this.options.agentRunner,
      signal: options.signal,
      fileReadState: options.fileReadState,
      sleepWake: options.sleepWake,
      stream: options.stream,
      onEvent: async (event) => {
        events.push(event);
        await this.options.store.recordEvent(runId, event);
        await options.onEvent?.(event);
      }
    });
  }

  private async requireApprovalRun(runId: string): Promise<RunRecord> {
    const run = await this.options.store.loadRun(runId);
    if (!run) throw new AgentRunServiceError("run_not_found", `run not found: ${runId}`, 404);
    if (run.status !== "awaiting_approval") {
      throw new AgentRunServiceError("run_not_awaiting_approval", `run is not waiting for tool approval: ${runId}`, 409);
    }
    if (!run.pending_approval) {
      throw new AgentRunServiceError("pending_approval_missing", `run has no pending approval payload: ${runId}`, 409);
    }
    return run;
  }

  private async loadCurrentRun(fallback: RunRecord): Promise<RunRecord> {
    return (await this.options.store.loadRun(fallback.run_id)) || fallback;
  }
}

export async function persistAgentRunOutcome(store: JsonStateStore, runId: string, result: AgentResult): Promise<void> {
  await store.setPendingApproval(runId, result.pending_approval);
  await store.finishRun(runId, runStatusForAgentResult(result));
}

export function runStatusForAgentResult(result: AgentResult): RunStatus {
  if (result.status === "awaiting_approval") return "awaiting_approval";
  if (result.status === "error") return "error";
  if (result.status === "canceled") return "canceled";
  return "finished";
}
