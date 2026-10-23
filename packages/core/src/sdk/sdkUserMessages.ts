import type { RuntimeEvent } from "../types/runtimeTypes.js";
import { objectValue, stringField } from "./sdkEventFields.js";
import type { SdkUserMessage } from "./sdkMessages.js";
import { newSdkUserMessageUuid } from "./sdkUserMessageIds.js";

export function runtimeEventFromSdkUserMessage(
  message: SdkUserMessage,
  options: { runId: string; sessionId: string; prompt: string }
): RuntimeEvent {
  const messagePayload = sdkUserApiMessage(message, options.prompt);
  const content = message.content || sdkUserMessageContent(messagePayload) || options.prompt;
  return {
    type: "user_message",
    name: "user",
    payload: {
      uuid: message.uuid,
      message_id: message.uuid,
      session_id: options.sessionId,
      run_id: options.runId,
      message: messagePayload,
      content,
      ...(message.parentToolUseId ? { parent_tool_use_id: message.parentToolUseId } : {}),
      timestamp: message.timestamp || new Date().toISOString(),
      isSynthetic: Boolean(message.isSynthetic),
      ...(message.toolUseResult !== undefined ? { tool_use_result: message.toolUseResult } : {}),
      ...(message.priority ? { priority: message.priority } : {}),
      isReplay: message.isReplay ?? true
    }
  };
}

export function userMessageFromRuntimeEvent(
  runId: string,
  sessionId: string,
  payload: Record<string, unknown>
): SdkUserMessage {
  const message = objectValue(payload.message);
  const uuid = stringField(payload, "uuid", "message_id", "messageId") || newSdkUserMessageUuid();
  const content = stringField(payload, "content") || sdkUserMessageContent(message);
  return {
    type: "user_message",
    uuid,
    sessionId: stringField(payload, "session_id", "sessionId") || sessionId,
    content,
    ...(Object.keys(message).length ? { message } : {}),
    ...optionalStringProperty("parentToolUseId", payload.parent_tool_use_id ?? payload.parentToolUseId),
    ...optionalBooleanProperty("isSynthetic", payload.isSynthetic ?? payload.is_synthetic),
    ...(payload.tool_use_result !== undefined || payload.toolUseResult !== undefined
      ? { toolUseResult: payload.tool_use_result ?? payload.toolUseResult }
      : {}),
    ...optionalPriorityProperty(payload.priority),
    ...optionalStringProperty("timestamp", payload.timestamp),
    isReplay: booleanValue(payload.isReplay ?? payload.is_replay) ?? true
  };
}

function sdkUserApiMessage(message: SdkUserMessage, fallbackContent: string): Record<string, unknown> {
  const existingMessage = objectValue(message.message);
  if (Object.keys(existingMessage).length) return existingMessage;
  const content = message.content || fallbackContent;
  return {
    role: "user",
    content: content ? [{ type: "text", text: content }] : []
  };
}

function sdkUserMessageContent(message: Record<string, unknown>): string {
  const content = message.content;
  if (typeof content === "string") return content;
  if (!Array.isArray(content)) return "";
  return content
    .map((item) => {
      const block = objectValue(item);
      return block.type === "text" ? stringField(block, "text") : "";
    })
    .join("");
}

function optionalStringProperty(key: string, value: unknown): Record<string, string> {
  const text = typeof value === "string" ? value : "";
  return text ? { [key]: text } : {};
}

function optionalBooleanProperty(key: string, value: unknown): Record<string, boolean> {
  const bool = booleanValue(value);
  return bool === undefined ? {} : { [key]: bool };
}

function optionalPriorityProperty(value: unknown): Pick<SdkUserMessage, "priority"> {
  return value === "now" || value === "next" || value === "later" ? { priority: value } : {};
}

function booleanValue(value: unknown): boolean | undefined {
  return typeof value === "boolean" ? value : undefined;
}
