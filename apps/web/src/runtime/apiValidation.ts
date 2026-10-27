import type { ModelProfilesResponse, RunListResponse, RunTraceResponse, TaskDetailResponse, TaskListResponse, TaskRunResponse, TaskRecord } from "../types/runtimeTypes";

export type RuntimeWireEvent = { type: string; name?: string; payload?: Record<string, unknown> };
export type ChatResponse = { run_id: string; status: string; content: string; events: RuntimeWireEvent[] };

type Check = (value: unknown) => boolean;
const string: Check = value => typeof value === "string";
const number: Check = value => typeof value === "number" && Number.isFinite(value);
const boolean: Check = value => typeof value === "boolean";
export function isRecord(value: unknown): value is Record<string, unknown> { return !!value && typeof value === "object" && !Array.isArray(value); }
const array = (check: Check): Check => value => Array.isArray(value) && value.every(check);
const optional = (check: Check): Check => value => value === undefined || check(value);
const fields = (shape: Record<string, Check>): Check => value => isRecord(value) && Object.entries(shape).every(([key, check]) => check(value[key]));
const strings: Check = value => isRecord(value) && Object.values(value).every(string);
const runtimeEvent = fields({ type: string, name: optional(string), payload: optional(isRecord) });
const run = fields({ run_id: string, status: string, tenant_id: string, user_id: string, agent_id: string, workspace_id: string, created_at: number, updated_at: number, events: array(runtimeEvent) });
const task = fields({ task_id: string, title: string, input: string, status: string, tenant_id: string, user_id: string, agent_id: string, workspace_id: string, metadata: strings, created_at: number, updated_at: number });
const step = fields({ step_id: string, task_id: string, run_id: string, status: string, output: string, error: string, created_at: number, updated_at: number });
const result = fields({ status: string, content: string, events: array(runtimeEvent) });

/** The cast is restricted to this boundary after checking the returned contract's fields. */
function decoder<T>(check: Check, name: string): (value: unknown) => T {
  return value => { if (!check(value)) throw new Error(`invalid API response: ${name}`); return value as T; };
}
export const chatResponse = decoder<ChatResponse>(fields({ run_id: string, status: string, content: string, events: array(runtimeEvent) }), "chat");
export const runListResponse = decoder<RunListResponse>(fields({ runs: array(run) }), "runs");
export const traceResponse = decoder<RunTraceResponse>(fields({ run_id: string, spans: array(isRecord), approvals: array(isRecord), artifacts: array(isRecord), sandbox_events: array(isRecord), operation_frames: optional(array(isRecord)), sandbox_snapshots: optional(array(isRecord)), sandbox_leases: optional(array(isRecord)) }), "trace");
export const profilesResponse = decoder<ModelProfilesResponse>(fields({ active_profile: string, profiles: array(fields({ name: string, protocol: string, model: string, base_url: string, endpoint: string, aliases: array(string), source: string, configured: boolean })) }), "profiles");
export const taskResponse = decoder<TaskRecord>(task, "task");
export const taskListResponse = decoder<TaskListResponse>(fields({ tasks: array(task) }), "tasks");
export const taskDetailResponse = decoder<TaskDetailResponse>(fields({ task, steps: array(step) }), "task detail");
export const taskRunResponse = decoder<TaskRunResponse>(fields({ task, step, run, result }), "task run");
export const healthResponse = decoder<{ status: string }>(fields({ status: string }), "health");
export const eventResponse = decoder<RuntimeWireEvent>(runtimeEvent, "runtime event");

export function apiEnvelope(value: unknown, ok: boolean): unknown {
  if (!isRecord(value) || typeof value.success !== "boolean" || typeof value.message !== "string" || typeof value.code !== "string" || !("data" in value)) throw new Error("invalid API response envelope");
  if (!ok || !value.success) {
    const detail = isRecord(value.data) && typeof value.data.detail === "string" ? value.data.detail : value.message;
    throw new Error(detail || `API request failed: ${value.code}`);
  }
  return value.data;
}
