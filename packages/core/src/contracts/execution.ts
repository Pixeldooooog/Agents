/** Versioned target contracts. The legacy runtime is migrated at B1/B2, not by renaming fields. */
export const EXECUTION_SCHEMA_VERSION = 1 as const;
export type RunState = "queued" | "preparing" | "running" | "waiting_input" | "waiting_approval"
  | "paused" | "reconciling" | "completed" | "failed" | "cancelled" | "expired";
export type ActionState = "prepared" | "dispatched" | "succeeded" | "failed" | "unknown" | "cancelled";
export type ReplaySafety = "read_only" | "idempotent" | "reconcilable" | "non_repeatable";

export interface WorkScope {
  principalId: string;
  projectId?: string;
  workspaceId: string;
  resourceSetId: string;
  connectorAccountId?: string;
}
export interface BudgetLimit {
  maxToolCalls: number;
  maxTokens: number;
  maxDurationMs: number;
  estimatedCost?: { maxUsd: number; pricingVersion: string };
}
export interface TaskContract {
  schemaVersion: 1;
  taskId: string;
  conversationId?: string;
  goalId?: string;
  planRevision?: { planId: string; version: number };
  scope: WorkScope;
  grantId: string;
  instructions: string;
  acceptance: string[];
  budget: BudgetLimit;
  activeRunId?: string;
}
export interface RunLease {
  runId: string;
  workerId: string;
  epoch: number;
  expiresAtMs: number;
}
export interface RunContract {
  schemaVersion: 1;
  runId: string;
  taskId?: string;
  state: RunState;
  version: number;
  checkpointVersion: number;
  cancelRequested: boolean;
  lease?: RunLease;
}
export interface ActionContract {
  schemaVersion: 1;
  actionId: string;
  operationId: string;
  runId: string;
  taskId?: string;
  scope: WorkScope;
  tool: { name: string; version: string };
  argumentsHash: string;
  grantId: string;
  grantVersion: number;
  state: ActionState;
  replaySafety: ReplaySafety;
  receiptRef?: string;
  resultRef?: string;
}
export interface ToolCapabilityContract {
  name: string;
  version: string;
  inputSchema: Record<string, unknown>;
  replaySafety: ReplaySafety;
  cancellation: "cooperative" | "process_tree" | "cannot_interrupt";
  requiredCapabilities: string[];
  maxOutputBytes: number;
}
export interface CheckpointContract {
  schemaVersion: 1;
  runId: string;
  version: number;
  inputCursor: number;
  messageCursor: number;
  contextSummaryRef?: string;
  planRevision?: { planId: string; version: number };
  actionIds: string[];
  pendingInteractionIds: string[];
  artifactIds: string[];
  budgetLedgerRef: string;
}
