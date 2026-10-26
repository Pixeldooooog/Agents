import { publicSpec } from "../types/agentTypes.js";
import type { AgentSpec } from "../types/agentTypes.js";
import type { TaskRecord, TaskStatus, TaskStepRecord, TaskStepStatus } from "../types/taskTypes.js";
import type { MutateState, ReadState } from "./stateStoreAccess.js";
import type { TaskListFilters, TaskRecordUpdate } from "./storeFilters.js";
import { clampLimit, matchesScope, newStoreRecordId, timestamp } from "./storeHelpers.js";

export function createTaskRecord(mutate: MutateState, spec: AgentSpec, input: string, title: string, metadata: Record<string, string> = {}): Promise<TaskRecord> {
  return mutate((state) => {
    const now = timestamp();
    const task: TaskRecord = {
      task_id: newStoreRecordId("task"),
      title,
      input,
      agent_id: spec.agent_id,
      tenant_id: spec.tenant_id,
      user_id: spec.user_id,
      workspace_id: spec.workspace_id,
      status: "queued",
      created_at: now,
      updated_at: now,
      metadata,
      spec: publicSpec(spec)
    };
    state.tasks.unshift(task);
    return task;
  });
}

export async function listTaskRecords(read: ReadState, filters: TaskListFilters = {}): Promise<TaskRecord[]> {
  const limit = clampLimit(filters.limit, 100, 100);
  return (await read()).tasks
    .filter((task) => matchesScope(task, filters) && (!filters.status || task.status === filters.status))
    .slice(0, limit);
}

export async function loadTaskRecord(read: ReadState, taskId: string): Promise<TaskRecord | undefined> {
  return (await read()).tasks.find((item) => item.task_id === taskId);
}

export async function listTaskStepRecords(read: ReadState, taskId: string): Promise<TaskStepRecord[]> {
  return (await read()).steps.filter((item) => item.task_id === taskId).sort((a, b) => a.index - b.index);
}

export function createTaskStepRecord(mutate: MutateState, task: TaskRecord, runId: string): Promise<TaskStepRecord> {
  return mutate((state) => {
    const now = timestamp();
    const existing = state.steps.filter((item) => item.task_id === task.task_id).length;
    const step: TaskStepRecord = {
      step_id: newStoreRecordId("step"),
      task_id: task.task_id,
      index: existing,
      name: task.title,
      input: task.input,
      run_id: runId,
      status: "running",
      output: "",
      error: "",
      created_at: now,
      updated_at: now,
      metadata: {}
    };
    state.steps.push(step);
    return step;
  });
}

export async function updateTaskRecordStatus(mutate: MutateState, taskId: string, status: TaskStatus): Promise<void> {
  await mutate((state) => {
    const task = state.tasks.find((item) => item.task_id === taskId);
    if (task) {
      task.status = status;
      task.updated_at = timestamp();
    }
  });
}

export function updateTaskRecord(mutate: MutateState, taskId: string, update: TaskRecordUpdate): Promise<TaskRecord | undefined> {
  return mutate((state) => {
    const task = state.tasks.find((item) => item.task_id === taskId);
    if (!task) return undefined;
    task.title = update.title ?? task.title;
    task.input = update.input ?? task.input;
    task.status = update.status ?? task.status;
    task.metadata = update.metadata ?? task.metadata;
    task.updated_at = timestamp();
    return task;
  });
}

export async function updateTaskStepRecord(mutate: MutateState, stepId: string, status: TaskStepStatus, output = "", error = ""): Promise<void> {
  await mutate((state) => {
    const step = state.steps.find((item) => item.step_id === stepId);
    if (step) {
      step.status = status;
      step.output = output || step.output;
      step.error = error || step.error;
      step.updated_at = timestamp();
    }
  });
}
