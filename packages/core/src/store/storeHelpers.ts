import path from "node:path";
import type { RuntimeEvent } from "../types/runtimeTypes.js";

export type StoreScope = {
  tenant_id: string;
  user_id: string;
  agent_id: string;
  workspace_id?: string;
};

export function statePath(repoRoot: string, configured: string): string {
  return path.isAbsolute(configured) ? configured : path.join(repoRoot, configured);
}

export function matchesScope(item: StoreScope, filters: Partial<StoreScope>): boolean {
  return (!filters.tenant_id || item.tenant_id === filters.tenant_id)
    && (!filters.user_id || item.user_id === filters.user_id)
    && (!filters.agent_id || item.agent_id === filters.agent_id)
    && (!filters.workspace_id || item.workspace_id === filters.workspace_id);
}

export function timestamp(): number {
  return Date.now() / 1000;
}

export function newStoreRecordId(prefix: string): string {
  return `${prefix}_${crypto.randomUUID().replaceAll("-", "")}`;
}

export function runCreatedEvent(): RuntimeEvent {
  return { type: "run_created", name: "run", payload: {} };
}

export function clampLimit(value: unknown, fallback: number, maximum: number): number {
  const limit = Number(value || fallback);
  if (!Number.isFinite(limit)) return fallback;
  return Math.max(1, Math.min(maximum, limit));
}
