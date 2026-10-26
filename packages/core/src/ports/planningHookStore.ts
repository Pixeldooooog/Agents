import type { HookRecord } from "../types/hookTypes.js";
import type { PlanningStateRecord } from "../types/planningTypes.js";
import type { HookScopeFilter } from "../hooks/hookScopes.js";

export type PlanningHookStore = {
  loadPlanningState(stateId: string): Promise<PlanningStateRecord | undefined>;
  savePlanningState(record: PlanningStateRecord): Promise<PlanningStateRecord>;
  saveHook(hook: HookRecord): Promise<HookRecord>;
  listHooks(filters?: HookScopeFilter): Promise<HookRecord[]>;
  deleteHook(hookId: string): Promise<boolean>;
};
