import type { Settings } from "../config/settings.js";
import type { AgentSpec } from "../types/agentTypes.js";

export const DEFAULT_TOOL_ITERATION_LIMIT = 40;
export type RuntimeToolLoopBudget = { mode: "limited"; maxIterations: number };

/** Per-request hints may reduce the operator limit, never disable or raise it. */
export function runtimeToolLoopBudget(settings: Settings, spec: AgentSpec): RuntimeToolLoopBudget {
  const operatorLimit = positiveInteger(settings.agent.maxToolIterations) ?? DEFAULT_TOOL_ITERATION_LIMIT;
  const requestedLimit = positiveInteger(spec.runtime?.maxToolIterations)
    ?? positiveInteger(spec.metadata.max_tool_iterations)
    ?? positiveInteger(spec.metadata.maxTurns)
    ?? positiveInteger(spec.metadata.max_turns)
    ?? operatorLimit;
  return { mode: "limited", maxIterations: Math.min(operatorLimit, requestedLimit) };
}

export function canContinueToolLoop(completedToolIterations: number, budget: RuntimeToolLoopBudget): boolean {
  return completedToolIterations < budget.maxIterations;
}

function positiveInteger(value: unknown): number | undefined {
  if (value === undefined || value === null || value === "") return undefined;
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : undefined;
}
