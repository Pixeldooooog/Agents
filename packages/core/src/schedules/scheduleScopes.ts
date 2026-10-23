import type { AgentSpec } from "../types/agentTypes.js";
import type { ScheduleRecord } from "../types/scheduleTypes.js";

export type ScheduleScopeFilter = {
  tenant_id?: string;
  user_id?: string;
  agent_id?: string;
  workspace_id?: string;
  enabled?: boolean;
  limit?: number;
};

export function scheduleMatchesScope(record: ScheduleRecord, filter: ScheduleScopeFilter): boolean {
  return matchesExact(record.tenant_id, filter.tenant_id)
    && matchesOptionalScope(record.user_id, filter.user_id)
    && matchesOptionalScope(record.agent_id, filter.agent_id)
    && matchesOptionalScope(record.workspace_id, filter.workspace_id)
    && (filter.enabled === undefined || record.enabled === filter.enabled);
}

export function scheduleScopeFromSpec(spec?: AgentSpec): ScheduleScopeFilter {
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
