import type { RuntimeEvent } from "../types/runtimeTypes.js";
import type { SdkMessage, SdkToolProgressStatus } from "./sdkMessages.js";
import { assistantMessageFromModelEvent } from "./sdkAssistantMessages.js";
import { filesPersistedMessageFromRuntimeEvent } from "./sdkEventArtifacts.js";
import { newSdkMessageUuid, numberField, objectValue, stringField } from "./sdkEventFields.js";
import { toolCallIdFromPayload, toolCallIdFromToolCall, toolCallIdFromToolStartPayload } from "./sdkEventPayloads.js";
import { userMessageFromRuntimeEvent } from "./sdkUserMessages.js";
import {
  explicitSdkMessagesFromRuntimeEvent,
  sideChannelSdkMessagesFromRuntimeEvent,
  toolProgressContractFields
} from "./sdkEventMessages.js";
import { directTaskMessageFromRuntimeEvent, taskMessagesFromRuntimeEvent } from "./sdkEventTasks.js";

export function sdkMessagesFromRuntimeEvent(runId: string, sessionId: string, event: RuntimeEvent): SdkMessage[] {
  const projected = primaryMessagesFromRuntimeEvent(runId, sessionId, event);
  const sideChannelMessages = sideChannelSdkMessagesFromRuntimeEvent(runId, sessionId, event);
  const filesPersisted = filesPersistedMessageFromRuntimeEvent(runId, sessionId, event);
  return [
    ...projected,
    ...sideChannelMessages,
    ...taskMessagesFromRuntimeEvent(runId, sessionId, event),
    ...(filesPersisted ? [filesPersisted] : [])
  ];
}

function primaryMessagesFromRuntimeEvent(runId: string, sessionId: string, event: RuntimeEvent): SdkMessage[] {
  const payload = objectValue(event.payload);
  const explicitMessages = explicitSdkMessagesFromRuntimeEvent(runId, sessionId, event);
  if (explicitMessages.length) return explicitMessages;
  if (event.type === "user_message") {
    return [userMessageFromRuntimeEvent(runId, sessionId, payload)];
  }
  if (event.type === "model_message") {
    return [assistantMessageFromModelEvent(runId, sessionId, payload)];
  }
  if (event.type === "text_delta" || event.type === "reasoning_delta") {
    return [{
      type: "stream_event",
      runId,
      sessionId,
      event: streamDeltaPayload(event.type, payload),
      parentToolUseId: stringField(payload, "parent_tool_use_id", "parentToolUseId") || undefined,
      uuid: stringField(payload, "uuid", "message_id", "messageId") || newSdkMessageUuid()
    }];
  }
  if (event.type === "session_state_changed") {
    return [{
      type: "system",
      subtype: "session_state_changed",
      runId,
      sessionId,
      state: sessionState(payload.state)
    }];
  }
  if (event.type === "task_started" || event.type === "task_notification") {
    const message = directTaskMessageFromRuntimeEvent(runId, sessionId, event);
    return message ? [message] : [];
  }
  if (event.type === "compact_boundary") {
    return [{
      type: "system",
      subtype: "compact_boundary",
      runId,
      sessionId,
      compactMetadata: compactBoundaryMetadata(payload),
      uuid: stringField(payload, "uuid", "message_id", "messageId") || newSdkMessageUuid()
    }];
  }
  if (event.type === "tool_start") {
    return [{
      type: "tool_progress",
      runId,
      sessionId,
      toolCallId: toolCallIdFromToolStartPayload(payload),
      name: stringField(payload, "name") || event.name || "",
      status: "started",
      input: objectValue(payload.arguments),
      result: {},
      ...toolProgressContractFields(payload),
      error: ""
    }];
  }
  if (event.type === "tool_result") {
    const isError = toolResultIsError(payload);
    const error = toolResultError(payload);
    return [
      {
        type: "tool_progress",
        runId,
        sessionId,
        toolCallId: toolCallIdFromPayload(payload),
        name: stringField(payload, "name") || event.name || "",
        status: toolResultProgressStatus(payload),
        input: {},
        result: payload,
        ...toolProgressContractFields(payload),
        error
      },
      {
        type: "tool_result",
        runId,
        sessionId,
        toolName: stringField(payload, "name") || event.name || "",
        toolCallId: toolCallIdFromPayload(payload),
        content: stringField(payload, "content") || error,
        isError
      }
    ];
  }
  if (event.type === "tool_approval_required") {
    const toolCall = objectValue(payload.tool_call);
    const permission = objectValue(payload.permission);
    const toolCallId = toolCallIdFromToolCall(toolCall);
    return [
      {
        type: "tool_progress",
        runId,
        sessionId,
        toolCallId,
        name: stringField(toolCall, "name") || event.name || "",
        status: "awaiting_approval",
        input: objectValue(toolCall.arguments),
        result: payload,
        ...toolProgressContractFields(payload),
        error: ""
      },
      {
        type: "approval_required",
        runId,
        sessionId,
        approvalId: stringField(payload, "approval_id", "approvalId") || toolCallId,
        toolName: String(toolCall.name || event.name || ""),
        arguments: objectValue(toolCall.arguments),
        reason: String(permission.reason || "")
      }
    ];
  }
  if (event.type === "error") {
    return [{
      type: "system",
      subtype: "status",
      runId,
      sessionId,
      status: null
    }];
  }
  if (event.type === "status" || payload.status === "compacting") {
    return [{
      type: "system",
      subtype: "status",
      runId,
      sessionId,
      status: payload.status === "compacting" ? "compacting" : null,
      permissionMode: stringField(payload, "permissionMode", "permission_mode") || undefined,
      uuid: stringField(payload, "uuid", "message_id", "messageId") || newSdkMessageUuid()
    }];
  }
  return [{ type: "runtime_event", runId, sessionId, event }];
}

function compactBoundaryMetadata(payload: Record<string, unknown>): Record<string, unknown> {
  const preservedSegment = objectValue(payload.preserved_segment || payload.preservedSegment);
  return {
    trigger: stringField(payload, "trigger") || "auto",
    preTokens: numberField(payload.pre_tokens ?? payload.preTokens),
    postTokens: numberField(payload.post_tokens ?? payload.postTokens),
    beforeMessages: numberField(payload.before_messages ?? payload.beforeMessages),
    afterMessages: numberField(payload.after_messages ?? payload.afterMessages),
    droppedMessages: numberField(payload.dropped_messages ?? payload.droppedMessages),
    ...(Object.keys(preservedSegment).length ? { preservedSegment } : {})
  };
}

function toolResultProgressStatus(payload: Record<string, unknown>): SdkToolProgressStatus {
  if (toolResultIsError(payload)) return "failed";
  return "completed";
}

function toolResultIsError(payload: Record<string, unknown>): boolean {
  return booleanLike(payload.is_error ?? payload.isError)
    || (payload.error !== undefined && payload.error !== null && payload.error !== "");
}

function toolResultError(payload: Record<string, unknown>): string {
  const directError = stringFromUnknown(payload.error);
  if (directError) return directError;
  return toolResultIsError(payload) ? stringField(payload, "content") : "";
}

function booleanLike(value: unknown): boolean {
  if (typeof value === "boolean") return value;
  if (typeof value === "number") return value !== 0;
  if (typeof value === "string") return ["true", "1", "yes"].includes(value.trim().toLowerCase());
  return Boolean(value);
}

function stringFromUnknown(value: unknown): string {
  if (value === undefined || value === null || value === "") return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function sessionState(value: unknown): "idle" | "running" | "requires_action" {
  const state = String(value || "");
  return state === "running" || state === "requires_action" ? state : "idle";
}

function streamDeltaPayload(eventType: string, payload: Record<string, unknown>): Record<string, unknown> {
  const rawEvent = objectValue(payload.event);
  if (Object.keys(rawEvent).length) return rawEvent;
  const delta = String(payload.delta || "");
  if (eventType === "reasoning_delta") {
    return { type: "content_block_delta", delta: { type: "thinking_delta", thinking: delta } };
  }
  return { type: "content_block_delta", delta: { type: "text_delta", text: delta } };
}
