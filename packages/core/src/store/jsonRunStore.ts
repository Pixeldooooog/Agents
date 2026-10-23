import type { AgentSpec } from "../types/agentTypes.js";
import type { PendingApproval, RunRecord, RunStatus, RuntimeEvent } from "../types/runtimeTypes.js";
import {
  finishRunRecord,
  listRunRecords,
  loadRunRecord,
  recordRunEvent,
  setRunPendingApproval,
  startRunRecord,
  updateRunMetadataRecord
} from "./runStateStore.js";
import type { MutateState, ReadState } from "./stateStoreAccess.js";
import type { RunListFilters } from "./storeFilters.js";

export type JsonStateAccess = {
  read: ReadState;
  mutate: MutateState;
};

export type JsonRunStoreMethods = {
  startRun(spec: AgentSpec): Promise<RunRecord>;
  recordEvent(runId: string, event: RuntimeEvent): Promise<void>;
  finishRun(runId: string, status: RunStatus): Promise<void>;
  setPendingApproval(runId: string, pendingApproval: PendingApproval | undefined): Promise<void>;
  updateRunMetadata(runId: string, metadata: Record<string, string>): Promise<void>;
  loadRun(runId: string): Promise<RunRecord | undefined>;
  listRuns(filters?: RunListFilters): Promise<RunRecord[]>;
};

export function jsonRunStoreMethods(access: JsonStateAccess): JsonRunStoreMethods {
  return {
    startRun: (spec) => startRunRecord(access.mutate, spec),
    recordEvent: (runId, event) => recordRunEvent(access.mutate, runId, event),
    finishRun: (runId, status) => finishRunRecord(access.mutate, runId, status),
    setPendingApproval: (runId, pendingApproval) => setRunPendingApproval(access.mutate, runId, pendingApproval),
    updateRunMetadata: (runId, metadata) => updateRunMetadataRecord(access.mutate, runId, metadata),
    loadRun: (runId) => loadRunRecord(access.read, runId),
    listRuns: (filters = {}) => listRunRecords(access.read, filters)
  };
}
