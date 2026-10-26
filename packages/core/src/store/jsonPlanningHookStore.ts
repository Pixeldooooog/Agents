import type { PlanningHookStore } from "../ports/planningHookStore.js";
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



export function jsonPlanningHookStoreMethods(access: JsonStateAccess): PlanningHookStore {
  return {
    loadPlanningState: (stateId) => loadPlanningStateRecord(access.read, stateId),
    savePlanningState: (record) => savePlanningStateRecord(access.mutate, record),
    saveHook: (hook) => saveHookRecord(access.mutate, hook),
    listHooks: (filters = {}) => listHookRecords(access.read, filters),
    deleteHook: (hookId) => deleteHookRecord(access.mutate, hookId)
  };
}
