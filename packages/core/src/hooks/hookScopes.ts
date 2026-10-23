import type { AgentSpec } from "../types/agentTypes.js";
import type { HookRecord } from "../types/hookTypes.js";
import { normalizeHookEvent } from "./hookCatalog.js";

export type HookScopeFilter = {
  tenant_id?: string;
  user_id?: string;
  agent_id?: string;
  workspace_id?: string;
  event?: string;
  enabled?: boolean;
  limit?: number;
};

export function hookMatchesScope(record: HookRecord, filter: HookScopeFilter): boolean {
  return matchesExact(record.tenant_id, filter.tenant_id)
    && matchesOptionalScope(record.user_id, filter.user_id)
    && matchesOptionalScope(record.agent_id, filter.agent_id)
    && matchesOptionalScope(record.workspace_id, filter.workspace_id)
    && (!filter.event || record.event === normalizeHookEvent(filter.event))
    && (filter.enabled === undefined || record.enabled === filter.enabled);
}

export function hookScopeFromSpec(spec?: AgentSpec): HookScopeFilter {
  if (!spec) return {};
  return {
    tenant_id: spec.tenant_id,
    user_id: spec.user_id,
    agent_id: spec.agent_id,
    workspace_id: spec.workspace_id
  };
}

function matchesExact(actual: string, expected: string | undefined): boolean {
  return !expected || actual === expected;
}

function matchesOptionalScope(actual: string, expected: string | undefined): boolean {
  return !expected || actual === "" || actual === expected;
}
