import type { Settings } from "../config/settings.js";
import type { AgentSpec } from "../types/agentTypes.js";

export type RuntimeToolLoopBudget =
  | { mode: "unlimited" }
  | { mode: "limited"; maxIterations: number };

export function runtimeToolLoopBudget(settings: Settings, spec: AgentSpec): RuntimeToolLoopBudget {
  const override = nonNegativeInteger(spec.runtime?.maxToolIterations)
    ?? positiveInteger(spec.metadata.max_tool_iterations)
    ?? positiveInteger(spec.metadata.maxTurns)
    ?? positiveInteger(spec.metadata.max_turns);
  const maxIterations = override ?? nonNegativeInteger(settings.agent.maxToolIterations) ?? 0;
  return maxIterations > 0 ? { mode: "limited", maxIterations } : { mode: "unlimited" };
}

export function canContinueToolLoop(completedToolIterations: number, budget: RuntimeToolLoopBudget): boolean {
  return budget.mode === "unlimited" || completedToolIterations < budget.maxIterations;
}

function nonNegativeInteger(value: unknown): number | undefined {
  if (value === undefined || value === null || value === "") return undefined;
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed >= 0 ? parsed : undefined;
}

function positiveInteger(value: unknown): number | undefined {
  const parsed = nonNegativeInteger(value);
  return parsed && parsed > 0 ? parsed : undefined;
}
