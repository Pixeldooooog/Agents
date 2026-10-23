import type { AgentSpec } from "../types/agentTypes.js";
import type { AgentResult, PendingApproval } from "../types/runtimeTypes.js";
import { runtimeStartMessages } from "./runtimeMessages.js";
import type { RuntimeOptions } from "./runtimeOptions.js";
import { resolvePendingApproval } from "./runtimeToolExecution.js";
import { runRuntimeTurnLoop } from "./runtimeTurnLoop.js";

export type { RuntimeOptions } from "./runtimeOptions.js";

export class AgentRuntime {
  private readonly options: RuntimeOptions;

  constructor(options: RuntimeOptions) {
    this.options = { ...options, fileReadState: options.fileReadState || {} };
  }

  async run(spec: AgentSpec, message: string, runId: string): Promise<AgentResult> {
    return runRuntimeTurnLoop({
      options: this.options,
      spec,
      runId,
      initialMessages: await runtimeStartMessages(this.options.settings, this.options.store, spec, message)
    });
  }

  async resumeWithApproval(spec: AgentSpec, pendingApproval: PendingApproval, approved: boolean, runId: string): Promise<AgentResult> {
    const resolution = await resolvePendingApproval(this.options, spec, pendingApproval, approved, runId);
    return runRuntimeTurnLoop({
      options: this.options,
      spec,
      runId,
      initialMessages: resolution.messages,
      initialToolResults: resolution.toolResults,
      initialEvents: resolution.events
    });
  }
}
