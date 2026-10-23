import { randomUUID } from "node:crypto";

export type SdkCcrStreamAccumulatorState = {
  byMessage: Map<string, Map<number, string[]>>;
  scopeToMessage: Map<string, string>;
};

export type SdkCcrStreamMessage = Record<string, unknown>;

export class SdkCcrStreamAccumulator {
  readonly byMessage = new Map<string, Map<number, string[]>>();
  readonly scopeToMessage = new Map<string, string>();

  snapshot(): SdkCcrStreamAccumulatorState {
    return {
      byMessage: this.byMessage,
      scopeToMessage: this.scopeToMessage
    };
  }
}

export function accumulateCcrStreamEvents(
  buffer: SdkCcrStreamMessage[],
  state: SdkCcrStreamAccumulator
): SdkCcrStreamMessage[] {
  const output: SdkCcrStreamMessage[] = [];
  const touched = new Map<string, SdkCcrStreamMessage>();
  for (const message of buffer) {
    const event = recordValue(message.event);
    if (!event) {
      output.push(message);
      continue;
    }
    if (event.type === "message_start") {
      const eventMessage = recordValue(event.message);
      const messageId = stringValue(eventMessage?.id);
      if (!messageId) {
        output.push(message);
        continue;
      }
      const scope = streamScopeKey(message);
      const previousId = state.scopeToMessage.get(scope);
      if (previousId) state.byMessage.delete(previousId);
      state.scopeToMessage.set(scope, messageId);
      state.byMessage.set(messageId, new Map());
      output.push(message);
      continue;
    }
    if (event.type !== "content_block_delta") {
      output.push(message);
      continue;
    }
    const delta = recordValue(event.delta);
    const text = stringValue(delta?.text);
    const index = numberValue(event.index);
    const messageId = state.scopeToMessage.get(streamScopeKey(message));
    const blocks = messageId ? state.byMessage.get(messageId) : undefined;
    if (!blocks || delta?.type !== "text_delta" || text === undefined || index === undefined) {
      output.push(message);
      continue;
    }
    const chunks = blocks.get(index) || [];
    chunks.push(text);
    blocks.set(index, chunks);
    const touchedKey = `${messageId}:${index}`;
    const existing = touched.get(touchedKey);
    if (existing) {
      const existingEvent = existing.event as Record<string, unknown>;
      const existingDelta = existingEvent.delta as Record<string, unknown>;
      existingDelta.text = chunks.join("");
      continue;
    }
    const scope = streamMessageScope(message);
    const useSnakeCase = hasSnakeCaseScopeFields(message);
    const snapshot = {
      type: "stream_event",
      uuid: stringValue(message.uuid) || randomUUID(),
      event: {
        type: "content_block_delta",
        index,
        delta: { type: "text_delta", text: chunks.join("") }
      }
    };
    if (useSnakeCase) {
      Object.assign(snapshot, {
        session_id: scope.sessionId,
        parent_tool_use_id: scope.parentToolUseId
      });
    } else {
      Object.assign(snapshot, {
        sessionId: scope.sessionId,
        parentToolUseId: scope.parentToolUseId
      });
    }
    touched.set(touchedKey, snapshot);
    output.push(snapshot);
  }
  return output;
}

export function clearCcrStreamAccumulatorForMessage(
  state: SdkCcrStreamAccumulator,
  assistant: SdkCcrStreamMessage
): void {
  const message = recordValue(assistant.message);
  const messageId = stringValue(message?.id);
  if (!messageId) return;
  state.byMessage.delete(messageId);
  const scope = streamScopeKey(assistant);
  if (state.scopeToMessage.get(scope) === messageId) state.scopeToMessage.delete(scope);
}

function streamScopeKey(message: SdkCcrStreamMessage): string {
  const scope = streamMessageScope(message);
  return `${scope.sessionId}:${scope.parentToolUseId || ""}`;
}

function streamMessageScope(message: SdkCcrStreamMessage): { sessionId: unknown; parentToolUseId: unknown } {
  return {
    sessionId: message.sessionId ?? message.session_id,
    parentToolUseId: message.parentToolUseId ?? message.parent_tool_use_id
  };
}

function hasSnakeCaseScopeFields(message: SdkCcrStreamMessage): boolean {
  return Object.prototype.hasOwnProperty.call(message, "session_id")
    || Object.prototype.hasOwnProperty.call(message, "parent_tool_use_id");
}

function recordValue(value: unknown): Record<string, unknown> | undefined {
  return typeof value === "object" && value !== null && !Array.isArray(value) ? value as Record<string, unknown> : undefined;
}

function stringValue(value: unknown): string | undefined {
  return typeof value === "string" ? value : undefined;
}

function numberValue(value: unknown): number | undefined {
  return Number.isInteger(value) ? value as number : undefined;
}

export const SDKCCRStreamAccumulator = SdkCcrStreamAccumulator;
export const accumulate_stream_events = accumulateCcrStreamEvents;
export const clear_stream_accumulator_for_message = clearCcrStreamAccumulatorForMessage;
