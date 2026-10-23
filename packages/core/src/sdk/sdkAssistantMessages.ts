import type { SdkAssistantError, SdkAssistantMessage } from "./sdkMessages.js";
import { newSdkMessageUuid, objectValue, stringField } from "./sdkEventFields.js";

export function assistantMessageFromModelEvent(
  runId: string,
  sessionId: string,
  payload: Record<string, unknown>
): SdkAssistantMessage {
  const message = assistantApiMessage(payload);
  const modelUsage = objectValue(payload.modelUsage ?? payload.model_usage);
  const parentToolUseId = stringField(payload, "parent_tool_use_id", "parentToolUseId");
  const error = assistantError(payload.error);
  return {
    type: "assistant_message",
    runId,
    sessionId,
    content: assistantMessageContent(message),
    message,
    uuid: sdkAssistantMessageUuid(payload),
    ...(parentToolUseId ? { parentToolUseId } : {}),
    ...(error ? { error } : {}),
    ...(Object.keys(modelUsage).length ? { modelUsage } : {})
  };
}

function assistantApiMessage(payload: Record<string, unknown>): Record<string, unknown> {
  const message = objectValue(payload.message);
  if (Object.keys(message).length) return message;
  const rawMessage = objectValue(objectValue(payload.raw).message);
  if (Object.keys(rawMessage).length) return rawMessage;
  const content = stringField(payload, "content");
  return {
    id: stringField(payload, "message_id", "messageId", "id") || `msg_${crypto.randomUUID().replaceAll("-", "")}`,
    type: "message",
    role: "assistant",
    content: content ? [{ type: "text", text: content }] : [],
    model: stringField(payload, "model"),
    stop_reason: payload.stop_reason ?? payload.stopReason ?? null,
    stop_sequence: payload.stop_sequence ?? payload.stopSequence ?? null,
    usage: objectValue(payload.usage)
  };
}

function assistantMessageContent(message: Record<string, unknown>): string {
  const content = message.content;
  if (typeof content === "string") return content;
  if (!Array.isArray(content)) return "";
  return content
    .map((item) => {
      const part = objectValue(item);
      return part.type === "text" ? stringField(part, "text") : "";
    })
    .join("");
}

function assistantError(value: unknown): SdkAssistantError | undefined {
  const error = String(value || "");
  if ([
    "authentication_failed",
    "billing_error",
    "rate_limit",
    "invalid_request",
    "server_error",
    "unknown",
    "max_output_tokens"
  ].includes(error)) {
    return error as SdkAssistantError;
  }
  return undefined;
}

function sdkAssistantMessageUuid(payload: Record<string, unknown>): string {
  return stringField(payload, "uuid", "message_id", "messageId") || newSdkMessageUuid();
}
