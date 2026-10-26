import type { ScheduleRecord } from "../types/scheduleTypes.js";
import type { ScheduleScopeFilter } from "../schedules/scheduleScopes.js";

export type ScheduleStore = {
  saveSchedule(schedule: ScheduleRecord): Promise<ScheduleRecord>;
  loadSchedule(scheduleId: string): Promise<ScheduleRecord | undefined>;
  listSchedules(filters?: ScheduleScopeFilter): Promise<ScheduleRecord[]>;
  deleteSchedule(scheduleId: string): Promise<boolean>;
  markScheduleRun(scheduleId: string, taskId: string): Promise<ScheduleRecord | undefined>;
};
