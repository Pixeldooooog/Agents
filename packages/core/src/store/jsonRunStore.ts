import type { RunStore } from "../ports/runStore.js";
import {
  claimRunPendingApproval,
  listRunRecords,
  loadRunRecord,
  recordRunEvent,
  setRunPendingApproval,
  startRunRecord,
  transitionRunRecord,
  updateRunMetadataRecord
} from "./runStateStore.js";
import type { MutateState, ReadState } from "./stateStoreAccess.js";

export type JsonStateAccess = {
  read: ReadState;
  mutate: MutateState;
};

export function jsonRunStoreMethods(access: JsonStateAccess): RunStore {
  return {
    claimPendingApproval: (runId, approvalId) => claimRunPendingApproval(access.mutate, runId, approvalId),
    startRun: (spec) => startRunRecord(access.mutate, spec),
    recordEvent: (runId, event) => recordRunEvent(access.mutate, runId, event),
    transitionRun: (runId, states) => transitionRunRecord(access.mutate, runId, states),
    setPendingApproval: (runId, pendingApproval) => setRunPendingApproval(access.mutate, runId, pendingApproval),
    updateRunMetadata: (runId, metadata) => updateRunMetadataRecord(access.mutate, runId, metadata),
    loadRun: (runId) => loadRunRecord(access.read, runId),
    listRuns: (filters = {}) => listRunRecords(access.read, filters)
  };
}
