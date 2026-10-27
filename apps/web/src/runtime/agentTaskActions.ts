import type { Setter } from "solid-js";
import type {
  AgentChatPayload,
  TaskRecord,
  TaskStepRecord,
} from "../types/runtimeTypes";
import type { createApiClient } from "./apiClient";
import { consumeRuntimeEvents } from "./eventHandlers";

type ApiClient = ReturnType<typeof createApiClient>;
type RuntimeEventDeps = Parameters<typeof consumeRuntimeEvents>[1];

type AgentTaskActionsOptions = {
  api: () => ApiClient;
  payload: (message: string) => AgentChatPayload;
  scopeFilter: () => Record<string, string>;
  selectedTaskId: () => string;
  setRunId: Setter<string>;
  setTasks: Setter<TaskRecord[]>;
  setTaskSteps: Setter<TaskStepRecord[]>;
  setSelectedTaskId: Setter<string>;
  refreshRuns: () => Promise<void>;
  syncOperationTrace: (runId?: string) => Promise<void>;
  eventDeps: () => RuntimeEventDeps;
};

export function createAgentTaskActions(options: AgentTaskActionsOptions) {
  const refreshTasks = async () => {
    const data = await options.api().tasks(options.scopeFilter());
    options.setTasks(data.tasks || []);
  };

  let detailRequest = 0;
  const openTask = async (taskId: string) => {
    const requestId = ++detailRequest;
    const data = await options.api().task(taskId);
    if (requestId !== detailRequest) return;
    options.setSelectedTaskId(taskId);
    options.setTaskSteps(data.steps || []);
  };

  const createTask = async (message: string, title = "") => {
    if (!message.trim()) return;
    const task = await options
      .api()
      .createTask({ ...options.payload(message), title: title || undefined });
    options.setSelectedTaskId(task.task_id);
    options.setTaskSteps([]);
    await refreshTasks();
  };

  const runTask = async (taskId: string) => {
    const data = await options.api().runTask(taskId);
    const taskRunId = data.run?.run_id || "";
    options.setRunId(taskRunId);
    consumeRuntimeEvents(
      data.result?.events || data.run?.events || [],
      options.eventDeps(),
    );
    await options.syncOperationTrace(taskRunId);
    await refreshTasks();
    await options.refreshRuns();
    await openTask(taskId);
  };

  const cancelTask = async (taskId: string) => {
    await options.api().cancelTask(taskId);
    await refreshTasks();
    if (options.selectedTaskId() === taskId) await openTask(taskId);
  };

  return { refreshTasks, openTask, createTask, runTask, cancelTask };
}
