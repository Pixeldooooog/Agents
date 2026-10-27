import { conversationHistory } from "../session/conversationHistory.js";
import { runtimeStartMessages } from "./runtimeMessages.js";
import type { Settings } from "../config/settings.js";
import { profileDefaults } from "../models/modelProfiles.js";
import type { StateStore } from "../ports/stateStore.js";
import type { AgentChatPayload, AgentSpec } from "../types/agentTypes.js";
import { specFromPayload } from "../types/agentTypes.js";
import type { AgentResult, RunRecord, RuntimeEvent } from "../types/runtimeTypes.js";
import { AgentRuntime } from "./agentRuntime.js";
import type { RuntimeOptions } from "./runtimeOptions.js";

export type AgentRunServiceOptions = {
  settings: Settings;
  store: StateStore;
  taskRunner?: RuntimeOptions["taskRunner"];
  mcpProviders?: RuntimeOptions["mcpProviders"];
  lspProvider?: RuntimeOptions["lspProvider"];
  agentRunner?: RuntimeOptions["agentRunner"];
  commandExecutor?: RuntimeOptions["commandExecutor"];
  executionPolicy?: RuntimeOptions["executionPolicy"];
};

export type AgentRunExecutionOptions = {
  previousRunId?: string;
  stream?: boolean;
  signal?: AbortSignal;
  fileReadState?: RuntimeOptions["fileReadState"];
  sleepWake?: RuntimeOptions["sleepWake"];
  afterRunStarted?: (run: RunRecord) => void | Promise<void>;
  onEvent?: (event: RuntimeEvent) => void | Promise<void>;
};

export type AgentApprovalResumeOptions = AgentRunExecutionOptions & {
  approvalId: string;
  spec?: AgentSpec;
};

export type PersistedAgentRun = {
  run: RunRecord;
  result: AgentResult;
  events: RuntimeEvent[];
};

export type AgentRunServiceErrorCode = "run_not_found" | "run_not_waiting_approval" | "pending_approval_missing" | "approval_conflict" | "approval_id_required" | "invalid_approval_decision" | "conversation_unavailable";

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
    return specFromPayload(payload, profileDefaults(this.options.settings, payload.protocol));
  }

  async runPayload(payload: AgentChatPayload, options: AgentRunExecutionOptions = {}): Promise<PersistedAgentRun> {
    return this.runAgent(this.specFromPayload(payload), payload.message, { ...options, previousRunId: payload.previous_run_id ?? options.previousRunId });
  }

  async runAgent(spec: AgentSpec, message: string, options: AgentRunExecutionOptions = {}): Promise<PersistedAgentRun> {
    const history = options.previousRunId !== undefined ? await this.conversationForRun(options.previousRunId, spec) : [];
    const messages = await runtimeStartMessages(this.options.settings, this.options.store, spec, message, history);
    const queued = await this.options.store.startRun(spec);
    await this.options.store.setRunMessages(queued.run_id, messages);
    const run = await this.options.store.transitionRun(queued.run_id, ["preparing", "running"]);
    await options.afterRunStarted?.(run);
    const events: RuntimeEvent[] = [];
    const runtime = this.runtimeFor(run.run_id, events, options);
    const result = await runtime.runConversation(spec, messages, run.run_id);
    await persistAgentRunOutcome(this.options.store, run.run_id, result);
    return {
      run: await this.loadCurrentRun(run),
      result,
      events
    };
  }

  async resumeApproval(runId: string, approved: boolean, options: AgentApprovalResumeOptions): Promise<PersistedAgentRun> {
    if (typeof options.approvalId !== "string" || !options.approvalId.trim()) throw new AgentRunServiceError("approval_id_required", "approvalId is required", 400);
    if (typeof approved !== "boolean") throw new AgentRunServiceError("invalid_approval_decision", "approved must be a boolean", 400);
    options.signal?.throwIfAborted();
    const run = await this.requireApprovalRun(runId);
    const spec = options.spec || this.specFromPayload({ message: "", ...run.spec });
    const pending = await this.options.store.claimPendingApproval(runId, options.approvalId);
    if (!pending) throw new AgentRunServiceError("approval_conflict", "approval was consumed or no longer matches", 409);
    await this.options.store.transitionRun(runId, ["preparing", "running"]);
    const events: RuntimeEvent[] = [];
    const runtime = this.runtimeFor(runId, events, options);
    const result = await runtime.resumeWithApproval(spec, pending, approved, runId);
    await persistAgentRunOutcome(this.options.store, runId, result);
    return {
      run: await this.loadCurrentRun(run),
      result,
      events
    };
  }

  async conversationForRun(runId: string, spec: AgentSpec) {
    if (typeof runId !== "string" || !runId.trim()) throw new AgentRunServiceError("run_not_found", "previous run ID is required", 400);
    const run = await this.options.store.loadRun(runId);
    if (!run || (["tenant_id", "user_id", "agent_id", "workspace_id"] as const).some(key => run[key] !== spec[key])) {
      throw new AgentRunServiceError("run_not_found", "conversation run not found in this scope", 404);
    }
    if (run.status !== "completed" || !run.messages) throw new AgentRunServiceError("conversation_unavailable", "only completed runs with a conversation snapshot can be continued", 409);
    return conversationHistory(run.messages);
  }

  private runtimeFor(runId: string, events: RuntimeEvent[], options: AgentRunExecutionOptions): AgentRuntime {
    return new AgentRuntime({
      settings: this.options.settings,
      store: this.options.store,
      taskRunner: this.options.taskRunner,
      mcpProviders: this.options.mcpProviders,
      lspProvider: this.options.lspProvider,
      agentRunner: this.options.agentRunner,
      commandExecutor: this.options.commandExecutor,
      executionPolicy: this.options.executionPolicy,
      signal: options.signal,
      fileReadState: options.fileReadState,
      sleepWake: options.sleepWake,
      stream: options.stream,
      onEvent: async (event) => {
        // Deltas are transient UI data; persist the validated model_message instead.
        const delivered = event.type === "text_delta" ? event : await this.options.store.recordEvent(runId, event);
        events.push(delivered);
        await options.onEvent?.(delivered);
      }
    });
  }

  private async requireApprovalRun(runId: string): Promise<RunRecord> {
    const run = await this.options.store.loadRun(runId);
    if (!run) throw new AgentRunServiceError("run_not_found", `run not found: ${runId}`, 404);
    if (run.status !== "waiting_approval") {
      throw new AgentRunServiceError("run_not_waiting_approval", `run is not waiting for tool approval: ${runId}`, 409);
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

export async function persistAgentRunOutcome(store: StateStore, runId: string, result: AgentResult): Promise<void> {
  if (result.status === "completed") await store.setRunMessages(runId, result.messages);
  await store.setPendingApproval(runId, result.pending_approval);
  await store.transitionRun(runId, [result.status]);
}
