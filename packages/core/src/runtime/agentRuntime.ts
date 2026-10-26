import type { AgentSpec } from "../types/agentTypes.js";
import type { AgentResult, Message, PendingApproval } from "../types/runtimeTypes.js";
import { runtimeStartMessages } from "./runtimeMessages.js";
import type { RuntimeOptions } from "./runtimeOptions.js";
import { runRuntimeTurnLoop } from "./runtimeTurnLoop.js";

export type { RuntimeOptions } from "./runtimeOptions.js";

export class AgentRuntime {
  private readonly options: RuntimeOptions;

  constructor(options: RuntimeOptions) {
    this.options = { ...options, fileReadState: options.fileReadState || {} };
  }

  async run(spec: AgentSpec, message: string, runId: string, history: Message[] = []): Promise<AgentResult> {
    return this.runConversation(spec, await runtimeStartMessages(this.options.settings, this.options.store, spec, message, history), runId);
  }

  async runConversation(spec: AgentSpec, messages: Message[], runId: string): Promise<AgentResult> {
    return runRuntimeTurnLoop({ options: this.options, spec, runId, initialMessages: messages });
  }

  async resumeWithApproval(spec: AgentSpec, pendingApproval: PendingApproval, approved: boolean, runId: string): Promise<AgentResult> {
    return runRuntimeTurnLoop({
      options: this.options,
      spec,
      runId,
      initialMessages: pendingApproval.messages,
      initialToolResults: pendingApproval.tool_results,
      resume: { pendingApproval, approved }
    });
  }
}
