import type { ActionContract, BudgetLimit, RunLease, WorkScope } from "./execution.js";

export interface ExecutionGrant {
  grantId: string;
  version: number;
  taskId?: string;
  scope: WorkScope;
  capabilities: string[];
  expiresAtMs: number;
  revoked: boolean;
  budget: BudgetLimit;
}
export interface ActionApproval {
  actionId: string;
  operationId: string;
  argumentsHash: string;
  tool: ActionContract["tool"];
  scope: WorkScope;
  taskId?: string;
  grantId: string;
  grantVersion: number;
  expiresAtMs: number;
  decision: "approved" | "denied";
}
export interface DispatchContext {
  nowMs: number;
  lease: RunLease;
  expectedWorkerId: string;
  expectedEpoch: number;
  grant: ExecutionGrant;
  requiredCapability: string;
  // These inputs are resolved by trusted execution services, never supplied by model arguments.
  resourceAllowed: boolean;
  budgetReserved: boolean;
  cancelRequested: boolean;
  approvalRequired: boolean;
  approval?: ActionApproval;
}

/** Contract precondition only: B2 must repeat this at the actual execution boundary. */
export function assertActionDispatch(action: ActionContract, context: DispatchContext): void {
  const { lease, grant, approval, nowMs } = context;
  if (!Number.isFinite(nowMs)) throw new Error("invalid_clock");
  if (context.cancelRequested) throw new Error("cancel_requested");
  if (lease.runId !== action.runId || lease.workerId !== context.expectedWorkerId
    || !Number.isSafeInteger(lease.epoch) || lease.epoch < 1 || lease.epoch !== context.expectedEpoch
    || !Number.isFinite(lease.expiresAtMs) || lease.expiresAtMs <= nowMs) throw new Error("stale_lease");
  if (!Number.isSafeInteger(grant.version) || grant.version < 1 || grant.revoked || !Number.isFinite(grant.expiresAtMs) || grant.expiresAtMs <= nowMs
    || grant.grantId !== action.grantId || grant.version !== action.grantVersion
    || grant.taskId !== action.taskId || !sameScope(grant.scope, action.scope)
    || !grant.capabilities.includes(context.requiredCapability)) throw new Error("invalid_grant");
  if (!context.resourceAllowed) throw new Error("resource_denied");
  if (!context.budgetReserved) throw new Error("budget_exhausted");
  if (context.approvalRequired && (!approval || approval.decision !== "approved"
    || !Number.isFinite(approval.expiresAtMs) || approval.expiresAtMs <= nowMs
    || approval.actionId !== action.actionId || approval.operationId !== action.operationId
    || approval.argumentsHash !== action.argumentsHash || approval.taskId !== action.taskId
    || approval.grantId !== grant.grantId || approval.grantVersion !== grant.version
    || approval.tool.name !== action.tool.name || approval.tool.version !== action.tool.version
    || !sameScope(approval.scope, action.scope))) throw new Error("invalid_approval");
  if (action.state !== "prepared") throw new Error("action_requires_recovery_decision");
}

function sameScope(a: WorkScope, b: WorkScope): boolean {
  return a.principalId === b.principalId && a.projectId === b.projectId
    && a.workspaceId === b.workspaceId && a.resourceSetId === b.resourceSetId
    && a.connectorAccountId === b.connectorAccountId;
}
