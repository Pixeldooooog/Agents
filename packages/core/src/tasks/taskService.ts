import type { Settings } from "../config/settings.js";
import { profileDefaults } from "../models/modelProfiles.js";
import { AgentRunService } from "../runtime/agentRunService.js";
import type { StateStore } from "../ports/stateStore.js";
import type { AgentChatPayload } from "../types/agentTypes.js";
import type { AgentResult } from "../types/runtimeTypes.js";
import type { TaskRecord, TaskStepRecord } from "../types/taskTypes.js";
import { specFromPayload } from "../types/agentTypes.js";
import { defaultTaskTitle } from "./taskTitles.js";

export class TaskService {
  constructor(private readonly settings: Settings, private readonly store: StateStore) {}

  async create(payload: AgentChatPayload): Promise<TaskRecord> {
    const spec = specFromPayload(payload, profileDefaults(this.settings));
    return this.store.createTask(spec, payload.message, defaultTaskTitle(payload.message), payload.metadata);
  }

  async run(taskId: string): Promise<{ task: TaskRecord; step: TaskStepRecord; result: AgentResult }> {
    const task = await this.store.loadTask(taskId);
    if (!task) throw new Error(`task not found: ${taskId}`);
    await this.store.updateTaskStatus(taskId, "running");

    const spec = specFromPayload({ message: task.input, ...task.spec }, profileDefaults(this.settings));
    let step: TaskStepRecord | undefined;
    const runs = new AgentRunService({
      settings: this.settings,
      store: this.store,
      taskRunner: this
    });
    const { result } = await runs.runAgent(spec, task.input, {
      afterRunStarted: async (run) => {
        step = await this.store.createStep(task, run.run_id);
      }
    });
    const failed = result.status === "error";
    const waiting = result.status === "awaiting_approval";
    if (!step) throw new Error(`task step was not created: ${taskId}`);
    await this.store.updateStep(step.step_id, failed ? "failed" : waiting ? "awaiting_approval" : "succeeded", result.content, failed ? taskErrorMessage(result) : "");
    await this.store.updateTaskStatus(taskId, failed ? "error" : waiting ? "awaiting_approval" : "finished");

    return { task: (await this.store.loadTask(taskId)) || task, step: (await this.store.listSteps(taskId)).at(-1) || step, result };
  }

  async cancel(taskId: string): Promise<TaskRecord> {
    const task = await this.store.loadTask(taskId);
    if (!task) throw new Error(`task not found: ${taskId}`);
    await this.store.updateTaskStatus(taskId, "canceled");
    return (await this.store.loadTask(taskId)) || task;
  }
}

function taskErrorMessage(result: AgentResult): string {
  const errorEvent = result.events.find((event) => event.type === "error");
  return String(errorEvent?.payload?.message || "");
}
