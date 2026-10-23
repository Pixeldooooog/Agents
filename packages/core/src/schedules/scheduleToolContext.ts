import type { AgentSpec } from "../types/agentTypes.js";
import type { ScheduleRecord } from "../types/scheduleTypes.js";
import type { ToolExecutionContext } from "../tools/toolContracts.js";
import { resolveSchedule } from "./scheduleRecords.js";
import { scheduleScopeFromSpec } from "./scheduleScopes.js";

export function requiredStore(context: ToolExecutionContext) {
  if (!context.store) throw new Error("state store is not available");
  return context.store;
}

export function requiredSpec(context: ToolExecutionContext): AgentSpec {
  if (!context.spec) throw new Error("agent spec is not available");
  return context.spec;
}

export async function resolveScopedSchedule(context: ToolExecutionContext, scheduleId: string): Promise<ScheduleRecord> {
  const schedules = await requiredStore(context).listSchedules({
    ...scheduleScopeFromSpec(context.spec),
    limit: 100
  });
  return resolveSchedule(schedules, scheduleId);
}

export function boundedLimit(value: unknown): number {
  const limit = Number(value || 50);
  return Number.isFinite(limit) ? Math.max(1, Math.min(100, limit)) : 50;
}
