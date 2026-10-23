import { publicSpec } from "../types/agentTypes.js";
import type { AgentSpec } from "../types/agentTypes.js";
import type { PendingApproval, RunRecord, RunStatus, RuntimeEvent } from "../types/runtimeTypes.js";
import type { MutateState, ReadState } from "./stateStoreAccess.js";
import type { RunListFilters } from "./storeFilters.js";
import { matchesScope, newStoreRecordId, runCreatedEvent, timestamp } from "./storeHelpers.js";

export function startRunRecord(mutate: MutateState, spec: AgentSpec): Promise<RunRecord> {
  return mutate((state) => {
    const now = timestamp();
    const run: RunRecord = {
      run_id: newStoreRecordId("run"),
      agent_id: spec.agent_id,
      tenant_id: spec.tenant_id,
      user_id: spec.user_id,
      workspace_id: spec.workspace_id,
      status: "running",
      events: [runCreatedEvent()],
      created_at: now,
      updated_at: now,
      metadata: { ...spec.metadata },
      spec: publicSpec(spec)
    };
    run.events[0].payload = { run_id: run.run_id };
    state.runs.unshift(run);
    return run;
  });
}

export async function recordRunEvent(mutate: MutateState, runId: string, event: RuntimeEvent): Promise<void> {
  await mutate((state) => {
    const run = state.runs.find((item) => item.run_id === runId);
    if (run) {
      run.events.push(event);
      run.updated_at = timestamp();
    }
  });
}

export async function finishRunRecord(mutate: MutateState, runId: string, status: RunStatus): Promise<void> {
  await mutate((state) => {
    const run = state.runs.find((item) => item.run_id === runId);
    if (run) {
      run.status = status;
      run.updated_at = timestamp();
    }
  });
}

export async function setRunPendingApproval(mutate: MutateState, runId: string, pendingApproval: PendingApproval | undefined): Promise<void> {
  await mutate((state) => {
    const run = state.runs.find((item) => item.run_id === runId);
    if (run) {
      run.pending_approval = pendingApproval;
      run.updated_at = timestamp();
    }
  });
}

export async function updateRunMetadataRecord(mutate: MutateState, runId: string, metadata: Record<string, string>): Promise<void> {
  await mutate((state) => {
    const run = state.runs.find((item) => item.run_id === runId);
    if (run) {
      run.metadata = { ...run.metadata, ...metadata };
      run.updated_at = timestamp();
    }
  });
}

export async function loadRunRecord(read: ReadState, runId: string): Promise<RunRecord | undefined> {
  return (await read()).runs.find((item) => item.run_id === runId);
}

export async function listRunRecords(read: ReadState, filters: RunListFilters = {}): Promise<RunRecord[]> {
  const limit = Math.max(1, Math.min(200, Number(filters.limit || 50)));
  return (await read()).runs.filter((run) => matchesScope(run, filters)).slice(0, limit);
}
