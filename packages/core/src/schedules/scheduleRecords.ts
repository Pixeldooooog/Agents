import type { AgentSpec } from "../types/agentTypes.js";
import type { ScheduleRecord } from "../types/scheduleTypes.js";

export function createScheduleRecord(input: {
  spec: AgentSpec;
  title: string;
  prompt: string;
  schedule: string;
  enabled?: boolean;
  metadata?: Record<string, string>;
  schedule_id?: string;
}): ScheduleRecord {
  const now = timestamp();
  const scheduleId = input.schedule_id || newScheduleId();
  return {
    schedule_id: scheduleId,
    short_id: shortScheduleId(scheduleId),
    title: input.title,
    input: input.prompt,
    schedule: input.schedule,
    enabled: input.enabled ?? true,
    agent_id: input.spec.agent_id,
    tenant_id: input.spec.tenant_id,
    user_id: input.spec.user_id,
    workspace_id: input.spec.workspace_id,
    metadata: { ...(input.metadata || {}) },
    created_at: now,
    updated_at: now,
    last_run_task_id: "",
    last_run_at: 0
  };
}

export function normalizeScheduleRecord(value: Partial<ScheduleRecord> & Record<string, unknown>): ScheduleRecord {
  const scheduleId = stringValue(value.schedule_id, newScheduleId());
  const createdAt = numberValue(value.created_at, timestamp());
  return {
    schedule_id: scheduleId,
    short_id: shortScheduleId(stringValue(value.short_id, scheduleId)),
    title: stringValue(value.title),
    input: stringValue(value.input),
    schedule: stringValue(value.schedule),
    enabled: booleanValue(value.enabled, true),
    agent_id: stringValue(value.agent_id),
    tenant_id: stringValue(value.tenant_id),
    user_id: stringValue(value.user_id),
    workspace_id: stringValue(value.workspace_id),
    metadata: stringRecord(value.metadata),
    created_at: createdAt,
    updated_at: numberValue(value.updated_at, createdAt),
    last_run_task_id: stringValue(value.last_run_task_id),
    last_run_at: numberValue(value.last_run_at, 0)
  };
}

export function scheduleWithLastRun(record: ScheduleRecord, taskId: string): ScheduleRecord {
  const now = timestamp();
  return { ...record, last_run_task_id: taskId, last_run_at: now, updated_at: now };
}

export function resolveSchedule(records: ScheduleRecord[], scheduleId: string): ScheduleRecord {
  const target = requiredText(scheduleId, "schedule_id");
  const exact = records.find((record) => record.schedule_id === target);
  if (exact) return exact;
  const shortTarget = target.replace(/^sched_/, "");
  const matches = records.filter((record) => shortScheduleId(record.schedule_id).startsWith(shortTarget));
  if (!matches.length) throw new Error(`schedule not found: ${target}`);
  if (matches.length > 1) throw new Error(`schedule id is ambiguous: ${target}`);
  return matches[0];
}

export function shortScheduleId(scheduleId: string): string {
  return String(scheduleId || "").replace(/^sched_/, "").slice(0, 12);
}

export function requiredText(value: unknown, name: string): string {
  const text = String(value || "").trim();
  if (!text) throw new Error(`${name} is required`);
  return text;
}

export function stringRecord(value: unknown): Record<string, string> {
  if (!value || typeof value !== "object") return {};
  return Object.fromEntries(Object.entries(value).map(([key, entryValue]) => [String(key), String(entryValue)]));
}

function stringValue(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function numberValue(value: unknown, fallback: number): number {
  const numericValue = Number(value);
  return Number.isFinite(numericValue) ? numericValue : fallback;
}

function booleanValue(value: unknown, fallback: boolean): boolean {
  return value === undefined ? fallback : Boolean(value);
}

function timestamp(): number {
  return Date.now() / 1000;
}

function newScheduleId(): string {
  return `sched_${crypto.randomUUID().replaceAll("-", "").slice(0, 12)}`;
}
