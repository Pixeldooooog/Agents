import { objectValue, parseJsonObject, stringField } from "./sdkEventFields.js";

export function toolResultPayloadData(payload: Record<string, unknown>): Record<string, unknown> {
  const raw = payload.raw;
  if (typeof raw === "string") {
    const parsed = parseJsonObject(raw);
    if (Object.keys(parsed).length) return parsed;
  }
  if (raw && typeof raw === "object" && !Array.isArray(raw)) {
    const rawRecord = raw as Record<string, unknown>;
    const result = parseJsonObject(rawRecord.result);
    return Object.keys(result).length ? { ...result, _meta: objectValue(rawRecord._meta) } : { ...rawRecord };
  }
  const parsedContent = parseJsonObject(payload.content);
  return Object.keys(parsedContent).length ? parsedContent : {};
}

export function toolCallIdFromPayload(payload: Record<string, unknown>): string {
  return stringField(payload, "tool_call_id", "toolCallId", "tool_use_id", "toolUseId");
}

export function toolCallIdFromToolStartPayload(payload: Record<string, unknown>): string {
  return toolCallIdFromPayload(payload) || stringField(payload, "id") || crypto.randomUUID();
}

export function toolCallIdFromToolCall(toolCall: Record<string, unknown>): string {
  return stringField(toolCall, "id", "tool_call_id", "toolCallId", "tool_use_id", "toolUseId") || crypto.randomUUID();
}
