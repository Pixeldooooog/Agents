import type { AgentSpec } from "../types/agentTypes.js";
import type { TaskRecord, TaskStatus, TaskStepRecord, TaskStepStatus } from "../types/taskTypes.js";
import type { TaskListFilters, TaskRecordUpdate } from "../store/storeFilters.js";

export type TaskStore = {
  createTask(spec: AgentSpec, input: string, title: string, metadata?: Record<string, string>): Promise<TaskRecord>;
  listTasks(filters?: TaskListFilters): Promise<TaskRecord[]>;
  loadTask(taskId: string): Promise<TaskRecord | undefined>;
  listSteps(taskId: string): Promise<TaskStepRecord[]>;
  createStep(task: TaskRecord, runId: string): Promise<TaskStepRecord>;
  updateTaskStatus(taskId: string, status: TaskStatus): Promise<void>;
  updateTask(taskId: string, update: TaskRecordUpdate): Promise<TaskRecord | undefined>;
  updateStep(stepId: string, status: TaskStepStatus, output?: string, error?: string): Promise<void>;
};
