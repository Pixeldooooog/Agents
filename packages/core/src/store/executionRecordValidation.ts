import type { RunState } from "../contracts/execution.js";
import type { RunRecord } from "../types/runtimeTypes.js";
import type { TaskRecord, TaskStatus, TaskStepRecord, TaskStepStatus } from "../types/taskTypes.js";

const runStates: ReadonlySet<string> = new Set<RunState>([
  "queued", "preparing", "running", "waiting_input", "waiting_approval",
  "paused", "reconciling", "completed", "failed", "cancelled", "expired"
]);
const taskStatuses: ReadonlySet<string> = new Set<TaskStatus>(["queued", "running", "paused", "waiting_approval", "completed", "failed", "cancelled"]);
const taskStepStatuses: ReadonlySet<string> = new Set<TaskStepStatus>(["pending", "running", "waiting_approval", "succeeded", "failed", "skipped", "cancelled"]);

/** Persisted execution records must use the current state vocabulary; unknown values fail instead of passing through. */
export function validatedRunRecords(value: unknown): RunRecord[] {
  return recordList(value, "runs", (record, index) => {
    requireId(record, "run_id", "runs", index);
    requireState(record.status, runStates, `runs[${index}].status`);
    if (!Number.isSafeInteger(record.version) || (record.version as number) < 0) throw invalidState(`runs[${index}].version must be a non-negative integer`);
    if (!Array.isArray(record.events)) throw invalidState(`runs[${index}].events must be an array`);
    record.events.forEach((event: unknown, eventIndex: number) => requireEventEnvelope(event, `runs[${index}].events[${eventIndex}]`));
    return record as RunRecord;
  });
}

export function validatedTaskRecords(value: unknown): TaskRecord[] {
  return recordList(value, "tasks", (record, index) => {
    requireId(record, "task_id", "tasks", index);
    requireState(record.status, taskStatuses, `tasks[${index}].status`);
    return record as TaskRecord;
  });
}

export function validatedTaskStepRecords(value: unknown): TaskStepRecord[] {
  return recordList(value, "steps", (record, index) => {
    requireId(record, "step_id", "steps", index);
    requireState(record.status, taskStepStatuses, `steps[${index}].status`);
    return record as TaskStepRecord;
  });
}

function recordList<T>(value: unknown, field: string, validate: (record: Record<string, unknown>, index: number) => T): T[] {
  if (value === undefined) return [];
  if (!Array.isArray(value)) throw invalidState(`${field} must be an array`);
  return value.map((record, index) => {
    if (!record || typeof record !== "object" || Array.isArray(record)) throw invalidState(`${field}[${index}] must be an object`);
    return validate(record as Record<string, unknown>, index);
  });
}

function requireId(record: Record<string, unknown>, key: string, field: string, index: number): void {
  if (typeof record[key] !== "string" || !record[key]) throw invalidState(`${field}[${index}].${key} must be a non-empty string`);
}

function requireState(value: unknown, allowed: ReadonlySet<string>, location: string): void {
  if (typeof value !== "string" || !allowed.has(value)) throw invalidState(`${location} has unsupported value ${JSON.stringify(value)}`);
}

function requireEventEnvelope(event: unknown, location: string): void {
  const record = event && typeof event === "object" ? event as Record<string, unknown> : undefined;
  if (!record || typeof record.event_id !== "string" || record.schema_version !== 1 || !Number.isSafeInteger(record.sequence) || typeof record.type !== "string") {
    throw invalidState(`${location} is missing its event envelope`);
  }
}

function invalidState(detail: string): Error {
  return new Error(`invalid state file: ${detail}`);
}
