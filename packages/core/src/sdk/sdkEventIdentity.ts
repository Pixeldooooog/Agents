import type { RunRecord, RuntimeEvent } from "../types/runtimeTypes.js";

export function runMatchesSdkUserMessage(run: RunRecord, userMessageId: string): boolean {
  return run.metadata.sdk_user_message_uuid === userMessageId ||
    `${run.run_id}:user` === userMessageId ||
    run.run_id === userMessageId;
}

export function eventMatchesMessageId(event: RuntimeEvent, messageId: string | undefined): boolean {
  if (!messageId) return false;
  return eventMessageIds(event).includes(messageId);
}

export function eventMessageIds(event: RuntimeEvent): string[] {
  const payload = event.payload || {};
  const raw = objectValue(event.raw);
  const ids = [
    ...idsFromRecord(payload),
    ...idsFromRecord(raw)
  ];
  const nestedMessage = payload.message;
  if (nestedMessage && typeof nestedMessage === "object" && !Array.isArray(nestedMessage)) {
    ids.push(...idsFromRecord(nestedMessage as Record<string, unknown>));
  }
  return [...new Set(ids)];
}

function idsFromRecord(payload: Record<string, unknown>): string[] {
  return ["uuid", "message_id", "messageId", "id", "tool_call_id", "toolCallId", "approval_id", "approvalId"]
    .map((key) => payload[key])
    .filter((value) => value !== undefined && value !== null && value !== "")
    .map(String);
}

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}
