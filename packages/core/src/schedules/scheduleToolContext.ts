import type { AgentSpec } from "../types/agentTypes.js";
import type { ScheduleRecord } from "../types/scheduleTypes.js";
import type { ToolContext } from "../tools/toolContracts.js";

export type ScheduleToolContext = ToolContext<"store">;
import { resolveSchedule } from "./scheduleRecords.js";
import { scheduleScopeFromSpec } from "./scheduleScopes.js";


export function requiredSpec(context: ScheduleToolContext): AgentSpec {
  if (!context.spec) throw new Error("agent spec is not available");
  return context.spec;
}

export async function resolveScopedSchedule(context: ScheduleToolContext, scheduleId: string): Promise<ScheduleRecord> {
  const schedules = await context.store.listSchedules({
    ...scheduleScopeFromSpec(context.spec),
    limit: 100
  });
  return resolveSchedule(schedules, scheduleId);
}

export function boundedLimit(value: unknown): number {
  const limit = Number(value || 50);
  return Number.isFinite(limit) ? Math.max(1, Math.min(100, limit)) : 50;
}
