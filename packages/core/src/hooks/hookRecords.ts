import type { AgentSpec } from "../types/agentTypes.js";
import type { HookRecord } from "../types/hookTypes.js";
import { normalizeHookAction, normalizeHookEvent } from "./hookCatalog.js";

export function createHookRecord(input: {
  spec?: AgentSpec;
  event: unknown;
  name: unknown;
  action: unknown;
  content?: unknown;
  enabled?: unknown;
  tool?: unknown;
  metadata?: unknown;
}): HookRecord {
  const now = timestamp();
  const hookId = newHookId();
  const metadata = stringRecord(input.metadata);
  const tool = String(input.tool || "").trim();
  if (tool) metadata.tool = tool;
  return {
    hook_id: hookId,
    short_id: shortHookId(hookId),
    event: normalizeHookEvent(input.event),
    name: requiredText(input.name, "name"),
    action: normalizeHookAction(input.action),
    content: String(input.content || ""),
    enabled: input.enabled === undefined ? true : Boolean(input.enabled),
    agent_id: input.spec?.agent_id || "",
    tenant_id: input.spec?.tenant_id || "",
    user_id: input.spec?.user_id || "",
    workspace_id: input.spec?.workspace_id || "",
    metadata,
    created_at: now,
    updated_at: now,
    last_run_at: 0,
    run_count: 0
  };
}

export function normalizeHookRecord(value: Partial<HookRecord> & Record<string, unknown>): HookRecord {
  const hookId = stringValue(value.hook_id, newHookId());
  const createdAt = numberValue(value.created_at, timestamp());
  return {
    hook_id: hookId,
    short_id: shortHookId(stringValue(value.short_id, hookId)),
    event: normalizeHookEvent(value.event),
    name: stringValue(value.name),
    action: normalizeHookAction(value.action),
    content: stringValue(value.content),
    enabled: value.enabled === undefined ? true : Boolean(value.enabled),
    agent_id: stringValue(value.agent_id),
    tenant_id: stringValue(value.tenant_id),
    user_id: stringValue(value.user_id),
    workspace_id: stringValue(value.workspace_id),
    metadata: stringRecord(value.metadata),
    created_at: createdAt,
    updated_at: numberValue(value.updated_at, createdAt),
    last_run_at: numberValue(value.last_run_at, 0),
    run_count: numberValue(value.run_count, 0)
  };
}

export function resolveHook(records: HookRecord[], hookId: string): HookRecord {
  const target = requiredText(hookId, "hook_id");
  const exact = records.find((record) => record.hook_id === target);
  if (exact) return exact;
  const shortTarget = target.replace(/^hook_/, "");
  const matches = records.filter((record) => shortHookId(record.hook_id).startsWith(shortTarget));
  if (!matches.length) throw new Error(`hook not found: ${target}`);
  if (matches.length > 1) throw new Error(`hook id is ambiguous: ${target}`);
  return matches[0];
}

export function shortHookId(hookId: string): string {
  return String(hookId || "").replace(/^hook_/, "").slice(0, 12);
}

function requiredText(value: unknown, name: string): string {
  const text = String(value || "").trim();
  if (!text) throw new Error(`${name} is required`);
  return text;
}

function stringRecord(value: unknown): Record<string, string> {
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

function timestamp(): number {
  return Date.now() / 1000;
}

function newHookId(): string {
  return `hook_${crypto.randomUUID().replaceAll("-", "").slice(0, 12)}`;
}
