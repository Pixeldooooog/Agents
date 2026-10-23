import type { AgentSpec } from "../types/agentTypes.js";
import type { MemoryRecord, MemoryScope } from "../types/memoryTypes.js";

export const memoryScopes: MemoryScope[] = ["user", "agent", "workspace", "run"];

export type MemoryScopeFilter = {
  tenant_id?: string;
  user_id?: string;
  agent_id?: string;
  workspace_id?: string;
  scope?: MemoryScope | "";
  query?: string;
  limit?: number;
};

export function createMemoryRecord(input: {
  spec: AgentSpec;
  content: string;
  scope?: MemoryScope;
  metadata?: Record<string, string>;
  runId?: string;
}): MemoryRecord {
  const now = timestamp();
  const scope = input.scope || "workspace";
  const memoryId = newMemoryId();
  const scopedIds = memoryScopedIds(input.spec, scope);
  return {
    memory_id: memoryId,
    short_id: shortMemoryId(memoryId),
    tenant_id: input.spec.tenant_id,
    user_id: input.spec.user_id,
    ...scopedIds,
    scope,
    content: input.content,
    metadata: { ...(input.metadata || {}), ...(scope === "run" && input.runId ? { run_id: input.runId } : {}) },
    created_at: now,
    updated_at: now
  };
}

export function normalizeMemoryRecord(value: Partial<MemoryRecord> & Record<string, unknown>): MemoryRecord {
  const memoryId = stringValue(value.memory_id, newMemoryId());
  const createdAt = numberValue(value.created_at, timestamp());
  return {
    memory_id: memoryId,
    short_id: shortMemoryId(stringValue(value.short_id, memoryId)),
    tenant_id: stringValue(value.tenant_id),
    user_id: stringValue(value.user_id),
    agent_id: stringValue(value.agent_id),
    workspace_id: stringValue(value.workspace_id),
    scope: normalizeMemoryScope(value.scope),
    content: stringValue(value.content),
    metadata: stringRecord(value.metadata),
    created_at: createdAt,
    updated_at: numberValue(value.updated_at, createdAt)
  };
}

export function memoryWithContent(record: MemoryRecord, content: string): MemoryRecord {
  return { ...record, content, updated_at: timestamp() };
}

export function resolveMemory(records: MemoryRecord[], memoryId: string): MemoryRecord {
  const target = requiredText(memoryId, "memory_id");
  const exact = records.find((record) => record.memory_id === target);
  if (exact) return exact;
  const shortTarget = target.replace(/^mem_/, "");
  const matches = records.filter((record) => shortMemoryId(record.memory_id).startsWith(shortTarget));
  if (!matches.length) throw new Error(`memory not found: ${target}`);
  if (matches.length > 1) throw new Error(`memory id is ambiguous: ${target}`);
  return matches[0];
}

export function memoryMatchesContext(record: MemoryRecord, filter: MemoryScopeFilter): boolean {
  const query = String(filter.query || "").trim().toLowerCase();
  return matchesExact(record.tenant_id, filter.tenant_id)
    && matchesExact(record.user_id, filter.user_id)
    && matchesOptionalScope(record.agent_id, filter.agent_id)
    && matchesOptionalScope(record.workspace_id, filter.workspace_id)
    && (!filter.scope || record.scope === filter.scope)
    && (!query || record.content.toLowerCase().includes(query));
}

export function memoryScopeFromSpec(spec?: AgentSpec): MemoryScopeFilter {
  if (!spec) return {};
  return {
    tenant_id: spec.tenant_id,
    user_id: spec.user_id,
    agent_id: spec.agent_id,
    workspace_id: spec.workspace_id
  };
}

export function normalizeMemoryScope(value: unknown): MemoryScope {
  const scope = String(value || "workspace").trim();
  if (memoryScopes.includes(scope as MemoryScope)) return scope as MemoryScope;
  throw new Error(`unknown memory scope: ${scope}`);
}

export function memoryContextBlock(memories: MemoryRecord[], limit: number): string {
  const selectedMemories = memories.slice(-Math.max(0, limit || 0));
  if (!selectedMemories.length) return "";
  const lines = selectedMemories.map((memory) => `- [${memory.scope}] ${memory.content}`);
  return `Memory context:\n${lines.join("\n")}`;
}

export function shortMemoryId(memoryId: string): string {
  return String(memoryId || "").replace(/^mem_/, "").slice(0, 12);
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

function memoryScopedIds(spec: AgentSpec, scope: MemoryScope): { agent_id: string; workspace_id: string } {
  if (scope === "user") return { agent_id: "", workspace_id: "" };
  if (scope === "agent") return { agent_id: spec.agent_id, workspace_id: "" };
  return { agent_id: spec.agent_id, workspace_id: spec.workspace_id };
}

function matchesExact(actual: string, expected: string | undefined): boolean {
  return !expected || actual === expected;
}

function matchesOptionalScope(actual: string, expected: string | undefined): boolean {
  return !expected || actual === "" || actual === expected;
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

function newMemoryId(): string {
  return `mem_${crypto.randomUUID().replaceAll("-", "")}`;
}
