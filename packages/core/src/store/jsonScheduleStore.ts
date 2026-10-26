import type { ScheduleStore } from "../ports/scheduleStore.js";
import type { ScheduleRecord } from "../types/scheduleTypes.js";
import type { ScheduleScopeFilter } from "../schedules/scheduleScopes.js";
import {
  deleteScheduleRecord,
  listScheduleRecords,
  loadScheduleRecord,
  markScheduleRecordRun,
  saveScheduleRecord
} from "./scheduleStateStore.js";
import type { JsonStateAccess } from "./jsonRunStore.js";



export function jsonScheduleStoreMethods(access: JsonStateAccess): ScheduleStore {
  return {
    saveSchedule: (schedule) => saveScheduleRecord(access.mutate, schedule),
    loadSchedule: (scheduleId) => loadScheduleRecord(access.read, scheduleId),
    listSchedules: (filters = {}) => listScheduleRecords(access.read, filters),
    deleteSchedule: (scheduleId) => deleteScheduleRecord(access.mutate, scheduleId),
    markScheduleRun: (scheduleId, taskId) => markScheduleRecordRun(access.mutate, scheduleId, taskId)
  };
}
