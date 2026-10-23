import type { AgentSpec } from "../types/agentTypes.js";
import type { TaskRecord, TaskStatus, TaskStepRecord, TaskStepStatus } from "../types/taskTypes.js";
import {
  createTaskRecord,
  createTaskStepRecord,
  listTaskRecords,
  listTaskStepRecords,
  loadTaskRecord,
  updateTaskRecord,
  updateTaskRecordStatus,
  updateTaskStepRecord
} from "./taskStateStore.js";
import type { JsonStateAccess } from "./jsonRunStore.js";
import type { TaskListFilters, TaskRecordUpdate } from "./storeFilters.js";

export type JsonTaskStoreMethods = {
  createTask(spec: AgentSpec, input: string, title: string, metadata?: Record<string, string>): Promise<TaskRecord>;
  listTasks(filters?: TaskListFilters): Promise<TaskRecord[]>;
  loadTask(taskId: string): Promise<TaskRecord | undefined>;
  listSteps(taskId: string): Promise<TaskStepRecord[]>;
  createStep(task: TaskRecord, runId: string): Promise<TaskStepRecord>;
  updateTaskStatus(taskId: string, status: TaskStatus): Promise<void>;
  updateTask(taskId: string, update: TaskRecordUpdate): Promise<TaskRecord | undefined>;
  updateStep(stepId: string, status: TaskStepStatus, output?: string, error?: string): Promise<void>;
};

export function jsonTaskStoreMethods(access: JsonStateAccess): JsonTaskStoreMethods {
  return {
    createTask: (spec, input, title, metadata = {}) => createTaskRecord(access.mutate, spec, input, title, metadata),
    listTasks: (filters = {}) => listTaskRecords(access.read, filters),
    loadTask: (taskId) => loadTaskRecord(access.read, taskId),
    listSteps: (taskId) => listTaskStepRecords(access.read, taskId),
    createStep: (task, runId) => createTaskStepRecord(access.mutate, task, runId),
    updateTaskStatus: (taskId, status) => updateTaskRecordStatus(access.mutate, taskId, status),
    updateTask: (taskId, update) => updateTaskRecord(access.mutate, taskId, update),
    updateStep: (stepId, status, output = "", error = "") => updateTaskStepRecord(access.mutate, stepId, status, output, error)
  };
}
