import type { Settings } from "../config/settings.js";
import { profileDefaults } from "../models/modelProfiles.js";
import { AgentRunService, type AgentRunServiceOptions } from "../runtime/agentRunService.js";
import type { StateStore } from "../ports/stateStore.js";
import type { AgentChatPayload } from "../types/agentTypes.js";
import type { AgentResult, RunOutcome } from "../types/runtimeTypes.js";
import type { TaskRecord, TaskStepRecord, TaskStepStatus } from "../types/taskTypes.js";
import { specFromPayload } from "../types/agentTypes.js";
import { defaultTaskTitle } from "./taskTitles.js";

const taskStepStatusForOutcome: Record<RunOutcome, TaskStepStatus> = {
  completed: "succeeded",
  waiting_approval: "waiting_approval",
  failed: "failed",
  cancelled: "cancelled"
};

export class TaskService {
  private readonly active = new Map<string, AbortController>();
  constructor(private readonly settings: Settings, private readonly store: StateStore, private readonly runtimeOptions: Pick<AgentRunServiceOptions, "mcpProviders"> = {}) {}

  async create(payload: AgentChatPayload): Promise<TaskRecord> {
    const spec = specFromPayload(payload, profileDefaults(this.settings));
    return this.store.createTask(spec, payload.message, defaultTaskTitle(payload.message), payload.metadata);
  }

  async run(taskId: string): Promise<{ task: TaskRecord; step: TaskStepRecord; result: AgentResult }> {
    const task = await this.store.loadTask(taskId);
    if (!task) throw new Error(`task not found: ${taskId}`);
    if (this.active.has(taskId)) throw new Error(`task already running: ${taskId}`);
    const controller = new AbortController();
    this.active.set(taskId, controller);
    try {
      await this.store.updateTaskStatus(taskId, "running");

      const spec = specFromPayload({ message: task.input, ...task.spec }, profileDefaults(this.settings));
      let step: TaskStepRecord | undefined;
      const runs = new AgentRunService({
        ...this.runtimeOptions,
        settings: this.settings,
        store: this.store,
        taskRunner: this
      });
      const { result } = await runs.runAgent(spec, task.input, {
        signal: controller.signal,
        afterRunStarted: async (run) => {
          step = await this.store.createStep(task, run.run_id);
        }
      });
      if (!step) throw new Error(`task step was not created: ${taskId}`);
      const failed = result.status === "failed";
      await this.store.updateStep(step.step_id, taskStepStatusForOutcome[result.status], result.content, failed ? taskErrorMessage(result) : "");
      await this.store.updateTaskStatus(taskId, result.status);

      return { task: (await this.store.loadTask(taskId)) || task, step: (await this.store.listSteps(taskId)).at(-1) || step, result };
    } finally { this.active.delete(taskId); }
  }

  async cancel(taskId: string): Promise<TaskRecord> {
    const task = await this.store.loadTask(taskId);
    if (!task) throw new Error(`task not found: ${taskId}`);
    this.active.get(taskId)?.abort();
    await this.store.updateTaskStatus(taskId, "cancelled");
    return (await this.store.loadTask(taskId)) || task;
  }
}

function taskErrorMessage(result: AgentResult): string {
  const errorEvent = result.events.find((event) => event.type === "error");
  return String(errorEvent?.payload?.message || "");
}
