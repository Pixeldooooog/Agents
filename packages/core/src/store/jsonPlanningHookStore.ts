import type { HookRecord } from "../types/hookTypes.js";
import type { PlanningStateRecord } from "../types/planningTypes.js";
import type { HookScopeFilter } from "../hooks/hookScopes.js";
import {
  deleteHookRecord,
  listHookRecords,
  saveHookRecord
} from "./hookStateStore.js";
import {
  loadPlanningStateRecord,
  savePlanningStateRecord
} from "./planningStateStore.js";
import type { JsonStateAccess } from "./jsonRunStore.js";

export type JsonPlanningHookStoreMethods = {
  loadPlanningState(stateId: string): Promise<PlanningStateRecord | undefined>;
  savePlanningState(record: PlanningStateRecord): Promise<PlanningStateRecord>;
  saveHook(hook: HookRecord): Promise<HookRecord>;
  listHooks(filters?: HookScopeFilter): Promise<HookRecord[]>;
  deleteHook(hookId: string): Promise<boolean>;
};

export function jsonPlanningHookStoreMethods(access: JsonStateAccess): JsonPlanningHookStoreMethods {
  return {
    loadPlanningState: (stateId) => loadPlanningStateRecord(access.read, stateId),
    savePlanningState: (record) => savePlanningStateRecord(access.mutate, record),
    saveHook: (hook) => saveHookRecord(access.mutate, hook),
    listHooks: (filters = {}) => listHookRecords(access.read, filters),
    deleteHook: (hookId) => deleteHookRecord(access.mutate, hookId)
  };
}
