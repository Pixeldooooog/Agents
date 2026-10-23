import type { RuntimeEvent } from "../types/runtimeTypes.js";
import type { SdkMessage, SdkTaskNotificationMessage } from "./sdkMessages.js";
import { numberField, objectValue, stringField } from "./sdkEventFields.js";
import { toolCallIdFromPayload, toolResultPayloadData } from "./sdkEventPayloads.js";

export function taskMessagesFromRuntimeEvent(runId: string, sessionId: string, event: RuntimeEvent): SdkMessage[] {
  if (event.type !== "tool_result") return [];
  const payload = objectValue(event.payload);
  const data = toolResultPayloadData(payload);
  const task = objectValue(data.task);
  const toolName = String(event.name || payload.name || "");
  const toolUseId = toolCallIdFromPayload(payload);
  const messages: SdkMessage[] = [];

  if (Object.keys(task).length && isTaskStartTool(toolName)) {
    const metadata = objectValue(task.metadata);
    messages.push({
      type: "system",
      subtype: "task_started",
      runId,
      sessionId,
      taskId: stringField(task, "task_id", "taskId"),
      toolUseId,
      description: stringField(task, "title", "input"),
      taskType: stringField(metadata, "task_type", "type"),
      workflowName: stringField(metadata, "workflow_name", "workflow"),
      prompt: stringField(task, "input")
    });
  }

  if (Object.keys(task).length && isTaskProgressTool(toolName)) {
    const step = objectValue(data.step);
    messages.push({
      type: "system",
      subtype: "task_progress",
      runId,
      sessionId,
      taskId: stringField(task, "task_id", "taskId"),
      toolUseId,
      description: stringField(task, "title", "input"),
      usage: taskUsage(data),
      lastToolName: stringField(step, "name"),
      summary: taskSummary(data, task)
    });
  }

  if (Object.keys(task).length && isTaskRunTool(toolName)) {
    const notification = taskNotificationMessage(runId, sessionId, toolUseId, task, data);
    if (notification) messages.push(notification);
  }

  if (isTaskBackgroundsTool(toolName)) {
    const backgroundTasks = Array.isArray(data.background_tasks) ? data.background_tasks : [];
    for (const item of backgroundTasks) {
      const notification = backgroundTaskNotification(runId, sessionId, objectValue(item));
      if (notification) messages.push(notification);
    }
  }

  return messages;
}

export function directTaskMessageFromRuntimeEvent(
  runId: string,
  sessionId: string,
  event: RuntimeEvent
): SdkMessage | undefined {
  const payload = objectValue(event.payload);
  if (event.type === "task_started") {
    const metadata = objectValue(payload.metadata);
    return {
      type: "system",
      subtype: "task_started",
      runId,
      sessionId,
      taskId: stringField(payload, "task_id", "taskId"),
      toolUseId: stringField(payload, "tool_use_id", "toolUseId", "tool_call_id", "toolCallId"),
      description: stringField(payload, "description", "summary"),
      taskType: stringField(payload, "task_type", "taskType") || stringField(metadata, "task_type", "type"),
      workflowName: stringField(payload, "workflow_name", "workflowName") || stringField(metadata, "workflow_name", "workflow"),
      prompt: stringField(payload, "prompt", "input")
    };
  }
  if (event.type === "task_notification") {
    const status = taskNotificationStatus(stringField(payload, "status"));
    if (!status) return undefined;
    return {
      type: "system",
      subtype: "task_notification",
      runId,
      sessionId,
      taskId: stringField(payload, "task_id", "taskId"),
      toolUseId: stringField(payload, "tool_use_id", "toolUseId", "tool_call_id", "toolCallId"),
      status,
      outputFile: stringField(payload, "output_file", "outputFile"),
      summary: stringField(payload, "summary"),
      usage: taskUsage(payload)
    };
  }
  return undefined;
}

function taskNotificationMessage(
  runId: string,
  sessionId: string,
  toolUseId: string,
  task: Record<string, unknown>,
  payload: Record<string, unknown>
): SdkTaskNotificationMessage | undefined {
  const status = taskNotificationStatus(stringField(task, "status") || stringField(payload, "status"));
  if (!status) return undefined;
  return {
    type: "system",
    subtype: "task_notification",
    runId,
    sessionId,
    taskId: stringField(task, "task_id", "taskId"),
    toolUseId,
    status,
    outputFile: stringField(payload, "output_file", "outputFile"),
    summary: taskSummary(payload, task),
    usage: taskUsage(payload)
  };
}

function backgroundTaskNotification(
  runId: string,
  sessionId: string,
  item: Record<string, unknown>
): SdkTaskNotificationMessage | undefined {
  const result = objectValue(item.result);
  const task = objectValue(result.task);
  const taskId = stringField(task, "task_id", "taskId") || stringField(item, "task_id", "taskId");
  const status = taskNotificationStatus(stringField(result, "status") || stringField(task, "status"));
  if (!taskId || !status) return undefined;
  return {
    type: "system",
    subtype: "task_notification",
    runId,
    sessionId,
    taskId,
    toolUseId: "",
    status,
    outputFile: stringField(result, "output_file", "outputFile"),
    summary: taskSummary(result, task),
    usage: taskUsage(result)
  };
}

function isTaskStartTool(name: string): boolean {
  return ["task.create", "TaskCreate", "task.background", "task.run", "Agent", "Task"].includes(name);
}

function isTaskProgressTool(name: string): boolean {
  return ["task.update", "TaskUpdate"].includes(name);
}

function isTaskRunTool(name: string): boolean {
  return ["task.run", "Agent", "Task"].includes(name);
}

function isTaskBackgroundsTool(name: string): boolean {
  return ["task.backgrounds", "TaskBackgrounds"].includes(name);
}

function taskNotificationStatus(status: string): "completed" | "failed" | "stopped" | undefined {
  const normalized = status.toLowerCase();
  if (["completed", "finished", "succeeded", "success"].includes(normalized)) return "completed";
  if (["failed", "error", "timed_out", "timeout"].includes(normalized)) return "failed";
  if (["stopped", "canceled", "cancelled", "killed"].includes(normalized)) return "stopped";
  return undefined;
}

function taskUsage(payload: Record<string, unknown>): Record<string, number> {
  const result = objectValue(payload.result);
  const usage = objectValue(payload.usage);
  const totalTokens = numberField(usage.total_tokens ?? usage.totalTokens);
  const toolUses = numberField(usage.tool_uses ?? usage.toolUses ?? result.tool_results);
  const durationMs = numberField(usage.duration_ms ?? usage.durationMs);
  return {
    totalTokens,
    toolUses,
    durationMs,
    total_tokens: totalTokens,
    tool_uses: toolUses,
    duration_ms: durationMs
  };
}

function taskSummary(payload: Record<string, unknown>, task: Record<string, unknown>): string {
  const result = objectValue(payload.result);
  const step = objectValue(payload.step);
  return stringField(result, "content")
    || stringField(step, "output", "error")
    || stringField(payload, "status")
    || stringField(task, "title");
}
