import type { AgentSpec } from "../types/agentTypes.js";
import type { PendingApproval, RunRecord, RunStatus, RuntimeEvent } from "../types/runtimeTypes.js";
import type { RunListFilters } from "../store/storeFilters.js";

export type RunStore = {
  startRun(spec: AgentSpec): Promise<RunRecord>;
  recordEvent(runId: string, event: RuntimeEvent): Promise<void>;
  finishRun(runId: string, status: RunStatus): Promise<void>;
  setPendingApproval(runId: string, pendingApproval: PendingApproval | undefined): Promise<void>;
  updateRunMetadata(runId: string, metadata: Record<string, string>): Promise<void>;
  loadRun(runId: string): Promise<RunRecord | undefined>;
  listRuns(filters?: RunListFilters): Promise<RunRecord[]>;
};
