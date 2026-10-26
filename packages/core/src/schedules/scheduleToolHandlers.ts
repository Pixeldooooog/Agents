import type { JsonObject } from "../types/jsonTypes.js";
import {
  createScheduleRecord,
  requiredText,
  stringRecord
} from "./scheduleRecords.js";
import { scheduleScopeFromSpec } from "./scheduleScopes.js";
import { boundedLimit, requiredSpec, resolveScopedSchedule, type ScheduleToolContext } from "./scheduleToolContext.js";

export async function scheduleCreate(context: ScheduleToolContext, args: JsonObject): Promise<Record<string, unknown>> {
  const record = createScheduleRecord({
    spec: requiredSpec(context),
    title: requiredText(args.title, "title"),
    prompt: String(args.input || args.title || ""),
    schedule: requiredText(args.schedule, "schedule"),
    enabled: args.enabled === undefined ? true : Boolean(args.enabled),
    metadata: { source: "tool", ...stringRecord(args.metadata) }
  });
  return { schedule: await context.store.saveSchedule(record) };
}

export async function scheduleList(context: ScheduleToolContext, args: JsonObject = {}): Promise<Record<string, unknown>> {
  const limit = boundedLimit(args.limit);
  const scopeFilter = scheduleScopeFromSpec(context.spec);
  const enabled = typeof args.enabled === "boolean" ? args.enabled : undefined;
  const schedules = await context.store.listSchedules({ ...scopeFilter, enabled, limit });
  return { schedules, count: schedules.length, total: schedules.length };
}

export async function scheduleDelete(context: ScheduleToolContext, args: JsonObject): Promise<Record<string, unknown>> {
  const schedule = await resolveScopedSchedule(context, requiredText(args.schedule_id, "schedule_id"));
  await context.store.deleteSchedule(schedule.schedule_id);
  return { schedule, deleted: true };
}

export async function scheduleRun(context: ScheduleToolContext, args: JsonObject): Promise<Record<string, unknown>> {
  const schedule = await resolveScopedSchedule(context, requiredText(args.schedule_id, "schedule_id"));
  const task = await context.store.createTask(
    requiredSpec(context),
    schedule.input,
    schedule.title,
    { ...schedule.metadata, source: "schedule", schedule_id: schedule.schedule_id }
  );
  const updatedSchedule = await context.store.markScheduleRun(schedule.schedule_id, task.task_id);
  return {
    schedule: updatedSchedule || schedule,
    task,
    background: { requested: args.background !== false, task_created: true, running: false }
  };
}
