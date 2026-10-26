import type { AgentSpec } from "../types/agentTypes.js";
import type { RunState } from "../contracts/execution.js";
import type { PendingApproval, PersistedRunEvent, RunRecord, RuntimeEvent } from "../types/runtimeTypes.js";
import type { RunListFilters } from "../store/storeFilters.js";

export type RunStore = {
  /** Creates the run in the `queued` state. */
  startRun(spec: AgentSpec): Promise<RunRecord>;
  /** Moves a `waiting_approval` run back to `queued` once per approval ID. */
  claimPendingApproval(runId: string, approvalId: string): Promise<PendingApproval | undefined>;
  /** Appends the event with its contract envelope and returns what was stored. */
  recordEvent(runId: string, event: RuntimeEvent): Promise<PersistedRunEvent>;
  /** Applies each state in order under the contract transition table; rejects the whole sequence on any invalid step. */
  transitionRun(runId: string, states: readonly [RunState, ...RunState[]]): Promise<RunRecord>;
  setPendingApproval(runId: string, pendingApproval: PendingApproval | undefined): Promise<void>;
  updateRunMetadata(runId: string, metadata: Record<string, string>): Promise<void>;
  loadRun(runId: string): Promise<RunRecord | undefined>;
  listRuns(filters?: RunListFilters): Promise<RunRecord[]>;
};
