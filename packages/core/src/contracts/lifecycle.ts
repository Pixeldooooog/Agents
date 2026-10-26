import type { ActionState, ReplaySafety, RunState } from "./execution.js";

const runTransitions: Record<RunState, readonly RunState[]> = {
  queued: ["preparing", "paused", "cancelled", "expired"],
  preparing: ["running", "paused", "reconciling", "failed", "cancelled", "expired"],
  running: ["waiting_input", "waiting_approval", "paused", "reconciling", "completed", "failed", "cancelled", "expired"],
  waiting_input: ["queued", "paused", "cancelled", "expired"],
  waiting_approval: ["queued", "paused", "cancelled", "expired"],
  paused: ["queued", "cancelled", "expired"],
  reconciling: ["queued", "paused", "completed", "failed", "cancelled", "expired"],
  completed: [], failed: [], cancelled: [], expired: []
};
const terminalStates: ReadonlySet<RunState> = new Set(["completed", "failed", "cancelled", "expired"]);

export interface TransitionEvidence {
  expectedVersion: number;
  actualVersion: number;
  activeActions: number;
  unknownActions: number;
}

/** Caller persists transition + event under the same version check in B2. */
export function assertRunTransition(from: RunState, to: RunState, evidence: TransitionEvidence): void {
  if (!Number.isSafeInteger(evidence.actualVersion) || evidence.actualVersion < 0
    || evidence.expectedVersion !== evidence.actualVersion) throw new Error("stale_run_version");
  if (![evidence.activeActions, evidence.unknownActions].every(value => Number.isSafeInteger(value) && value >= 0)) {
    throw new Error("invalid_action_counts");
  }
  if (!runTransitions[from]?.includes(to)) throw new Error(`invalid_run_transition:${from}:${to}`);
  if (evidence.unknownActions > 0 && to !== "reconciling") throw new Error("action_reconciliation_required");
  if (evidence.activeActions > 0 && (terminalStates.has(to)
    || ["queued", "paused", "waiting_input", "waiting_approval"].includes(to))) {
    throw new Error("active_actions_must_settle");
  }
}

export type RecoveryDecision = "consume_result" | "dispatch_after_authorization" | "query_receipt"
  | "retry_same_operation_after_authorization" | "manual_reconciliation" | "do_not_retry";

export function actionRecoveryDecision(state: ActionState, safety: ReplaySafety): RecoveryDecision {
  if (state === "succeeded") return "consume_result";
  if (state === "cancelled") return "do_not_retry";
  if (state === "prepared") return "dispatch_after_authorization";
  if (safety === "reconcilable") return "query_receipt";
  if (safety === "read_only" || safety === "idempotent") return "retry_same_operation_after_authorization";
  return state === "failed" ? "do_not_retry" : "manual_reconciliation";
}
