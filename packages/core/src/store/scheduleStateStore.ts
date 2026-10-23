import {
  normalizeScheduleRecord,
  scheduleWithLastRun
} from "../schedules/scheduleRecords.js";
import { scheduleMatchesScope, type ScheduleScopeFilter } from "../schedules/scheduleScopes.js";
import type { ScheduleRecord } from "../types/scheduleTypes.js";
import type { MutateState, ReadState } from "./stateStoreAccess.js";
import { clampLimit, timestamp } from "./storeHelpers.js";

export function saveScheduleRecord(mutate: MutateState, schedule: ScheduleRecord): Promise<ScheduleRecord> {
  return mutate((state) => {
    const saved = normalizeScheduleRecord({ ...schedule, updated_at: timestamp() });
    const index = state.schedules.findIndex((item) => item.schedule_id === saved.schedule_id);
    if (index >= 0) state.schedules[index] = saved;
    else state.schedules.unshift(saved);
    return saved;
  });
}

export async function loadScheduleRecord(read: ReadState, scheduleId: string): Promise<ScheduleRecord | undefined> {
  return (await read()).schedules.map(normalizeScheduleRecord).find((item) => item.schedule_id === scheduleId);
}

export async function listScheduleRecords(read: ReadState, filters: ScheduleScopeFilter = {}): Promise<ScheduleRecord[]> {
  const limit = clampLimit(filters.limit, 100, 100);
  return (await read()).schedules
    .map(normalizeScheduleRecord)
    .filter((schedule) => scheduleMatchesScope(schedule, filters))
    .sort((a, b) => b.updated_at - a.updated_at || a.schedule_id.localeCompare(b.schedule_id))
    .slice(0, limit);
}

export function deleteScheduleRecord(mutate: MutateState, scheduleId: string): Promise<boolean> {
  return mutate((state) => {
    const before = state.schedules.length;
    state.schedules = state.schedules.filter((item) => item.schedule_id !== scheduleId);
    return state.schedules.length !== before;
  });
}

export function markScheduleRecordRun(mutate: MutateState, scheduleId: string, taskId: string): Promise<ScheduleRecord | undefined> {
  return mutate((state) => {
    const index = state.schedules.findIndex((item) => item.schedule_id === scheduleId);
    if (index < 0) return undefined;
    const updated = scheduleWithLastRun(normalizeScheduleRecord(state.schedules[index]), taskId);
    state.schedules[index] = updated;
    return updated;
  });
}
