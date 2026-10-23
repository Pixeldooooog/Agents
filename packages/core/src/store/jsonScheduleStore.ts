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

export type JsonScheduleStoreMethods = {
  saveSchedule(schedule: ScheduleRecord): Promise<ScheduleRecord>;
  loadSchedule(scheduleId: string): Promise<ScheduleRecord | undefined>;
  listSchedules(filters?: ScheduleScopeFilter): Promise<ScheduleRecord[]>;
  deleteSchedule(scheduleId: string): Promise<boolean>;
  markScheduleRun(scheduleId: string, taskId: string): Promise<ScheduleRecord | undefined>;
};

export function jsonScheduleStoreMethods(access: JsonStateAccess): JsonScheduleStoreMethods {
  return {
    saveSchedule: (schedule) => saveScheduleRecord(access.mutate, schedule),
    loadSchedule: (scheduleId) => loadScheduleRecord(access.read, scheduleId),
    listSchedules: (filters = {}) => listScheduleRecords(access.read, filters),
    deleteSchedule: (scheduleId) => deleteScheduleRecord(access.mutate, scheduleId),
    markScheduleRun: (scheduleId, taskId) => markScheduleRecordRun(access.mutate, scheduleId, taskId)
  };
}
