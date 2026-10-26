import type { JsonObject } from "../types/jsonTypes.js";
import type { TaskRecord } from "../types/taskTypes.js";
import { defaultTaskTitle } from "./taskTitles.js";
import { requiredSpec, requiredText, stringMetadata, type TaskToolContext } from "./taskToolInputs.js";
import { resolveTaskInScope } from "./taskResolution.js";

export async function createTaskForRun(context: TaskToolContext, args: JsonObject, sourceTool: string): Promise<TaskRecord> {
  const input = requiredText(args.input || args.title, "input");
  return context.store.createTask(
    requiredSpec(context),
    input,
    String(args.title || defaultTaskTitle(input)),
    { source: "tool", tool: sourceTool, ...stringMetadata(args.metadata) }
  );
}

export async function resolveScopedTask(context: TaskToolContext, taskId: string): Promise<TaskRecord> {
  const spec = context.spec;
  return resolveTaskInScope(context.store, requiredText(taskId, "task_id"), {
    tenant_id: spec?.tenant_id,
    user_id: spec?.user_id,
    agent_id: spec?.agent_id,
    workspace_id: spec?.workspace_id
  });
}
