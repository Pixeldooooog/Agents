import type { StoreScopeFilter } from "../store/storeFilters.js";
import type { TaskRecord } from "../types/taskTypes.js";
import type { SdkControlRequestMessage } from "./sdkControlTypes.js";
import { sdkOptionScope } from "./sdkProtocolOptionAccess.js";
import type { SdkControlRequestHandlerContext } from "./sdkProtocolRunner.js";

export async function stopTaskControlResponsePayload(
  message: SdkControlRequestMessage,
  context: SdkControlRequestHandlerContext
): Promise<Record<string, unknown>> {
  const request = message.request;
  if (request.subtype !== "stop_task") return {};
  return {
    stopped: true,
    task: sdkTaskPayload(await context.client.stopTask(request.taskId, taskControlScope(context)))
  };
}

function taskControlScope(context: SdkControlRequestHandlerContext): StoreScopeFilter {
  return sdkOptionScope(context.options);
}

function sdkTaskPayload(task: TaskRecord): Record<string, unknown> {
  return {
    task_id: task.task_id,
    short_id: task.task_id.replace(/^task_/, "").slice(0, 12),
    title: task.title,
    input: task.input,
    status: task.status,
    agent_id: task.agent_id,
    workspace_id: task.workspace_id,
    metadata: { ...task.metadata },
    created_at: task.created_at,
    updated_at: task.updated_at
  };
}
