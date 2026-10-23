import { normalizePlanningState } from "../planning/planningState.js";
import type { PlanningStateRecord } from "../types/planningTypes.js";
import type { MutateState, ReadState } from "./stateStoreAccess.js";
import { timestamp } from "./storeHelpers.js";

export async function loadPlanningStateRecord(read: ReadState, stateId: string): Promise<PlanningStateRecord | undefined> {
  return (await read()).planning.map(normalizePlanningState).find((item) => item.state_id === stateId);
}

export function savePlanningStateRecord(mutate: MutateState, record: PlanningStateRecord): Promise<PlanningStateRecord> {
  return mutate((state) => {
    const saved = normalizePlanningState({ ...record, updated_at: timestamp() });
    const index = state.planning.findIndex((item) => item.state_id === saved.state_id);
    if (index >= 0) state.planning[index] = saved;
    else state.planning.push(saved);
    return saved;
  });
}
