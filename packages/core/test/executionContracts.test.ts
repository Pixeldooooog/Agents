import { expect, test } from "bun:test";
import { assertRunTransition, actionRecoveryDecision, assertActionDispatch, type ActionContract, type DispatchContext } from "../src/contracts/index.js";
import { runtimeToolLoopBudget, canContinueToolLoop } from "../src/runtime/runtimeLimits.js";
import type { Settings } from "../src/config/settings.js";
import type { AgentSpec } from "../src/types/agentTypes.js";

test("unknown external effects prevent completion and cancellation; stale workers cannot transition", () => {
  const evidence = { expectedVersion: 4, actualVersion: 4, activeActions: 0, unknownActions: 1 };
  expect(() => assertRunTransition("running", "completed", evidence)).toThrow("reconciliation");
  expect(() => assertRunTransition("running", "cancelled", evidence)).toThrow("reconciliation");
  assertRunTransition("running", "reconciling", evidence);
  expect(() => assertRunTransition("running", "completed", { ...evidence, unknownActions: 0, activeActions: 1 })).toThrow("settle");
  expect(() => assertRunTransition("running", "reconciling", { ...evidence, expectedVersion: 3 })).toThrow("stale");
  expect(actionRecoveryDecision("unknown", "non_repeatable")).toBe("manual_reconciliation");
  expect(actionRecoveryDecision("dispatched", "reconcilable")).toBe("query_receipt");
  expect(actionRecoveryDecision("succeeded", "idempotent")).toBe("consume_result");
});

test("dispatch binds approval to arguments, account, grant and live lease", () => {
  const scope = { principalId: "p", workspaceId: "w", resourceSetId: "r", connectorAccountId: "account" };
  const action: ActionContract = { schemaVersion: 1, actionId: "a", operationId: "o", runId: "run", scope, tool: { name: "send", version: "1" }, argumentsHash: "hash", grantId: "g", grantVersion: 1, state: "prepared", replaySafety: "non_repeatable" };
  const context: DispatchContext = { nowMs: 10, lease: { runId: "run", workerId: "worker", epoch: 2, expiresAtMs: 100 }, expectedWorkerId: "worker", expectedEpoch: 2, grant: { grantId: "g", version: 1, scope, capabilities: ["send"], expiresAtMs: 100, revoked: false, budget: { maxToolCalls: 1, maxTokens: 100, maxDurationMs: 100 } }, requiredCapability: "send", resourceAllowed: true, budgetReserved: true, cancelRequested: false, approvalRequired: true, approval: { ...action, expiresAtMs: 100, decision: "approved" } };
  assertActionDispatch(action, context);
  expect(() => assertActionDispatch(action, { ...context, expectedEpoch: 3 })).toThrow("stale_lease");
  expect(() => assertActionDispatch(action, { ...context, cancelRequested: true })).toThrow("cancel_requested");
  expect(() => assertActionDispatch({ ...action, argumentsHash: "changed" }, context)).toThrow("invalid_approval");
  expect(() => assertActionDispatch({ ...action, scope: { ...scope, connectorAccountId: "other" } }, context)).toThrow("invalid_grant");
  expect(() => assertActionDispatch(action, { ...context, grant: { ...context.grant, revoked: true } })).toThrow("invalid_grant");
  expect(() => assertActionDispatch(action, { ...context, budgetReserved: false })).toThrow("budget_exhausted");
});

test("request hints cannot disable or raise operator tool limits", () => {
  const settings = { agent: { maxToolIterations: 3 } } as Settings;
  for (const requested of [0, -1, 4, Infinity, 1.5]) {
    const spec = { metadata: {}, runtime: { maxToolIterations: requested } } as AgentSpec;
    expect(runtimeToolLoopBudget(settings, spec).maxIterations).toBe(3);
  }
  const budget = runtimeToolLoopBudget(settings, { metadata: { maxTurns: 2 } } as AgentSpec);
  expect(budget.maxIterations).toBe(2);
  expect(canContinueToolLoop(2, budget)).toBe(false);
  expect(runtimeToolLoopBudget({ agent: { maxToolIterations: 0 } } as Settings, { metadata: {} } as AgentSpec).maxIterations).toBe(40);
});
