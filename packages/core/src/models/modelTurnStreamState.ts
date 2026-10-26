import type { ModelStreamEvent, ModelTurn } from "../types/modelTypes.js";
import type { SseEvent } from "./modelSse.js";
import { ModelProtocolError } from "./modelErrors.js";
import { parseProtocolJson, requireRecord } from "./modelProtocolValidation.js";

export type TurnStreamStep = { events: ModelStreamEvent[]; turn?: ModelTurn };
export type TurnStreamDecoder = (event: SseEvent) => TurnStreamStep;

export function streamRecord(event: SseEvent): Record<string, unknown> {
  const record = requireRecord(parseProtocolJson(event.data), "stream payload");
  if (event.event === "error" || record.type === "error" || record.error) throw new ModelProtocolError("model stream returned an error");
  return record;
}

export function streamIndex(value: unknown): number {
  if (typeof value !== "number" || !Number.isInteger(value) || value < 0 || value >= 1024) {
    throw new ModelProtocolError("invalid stream item index");
  }
  return value;
}

export function streamString(value: unknown): string {
  if (typeof value !== "string") throw new ModelProtocolError("stream delta must be a string");
  return value;
}

export function immutableField(previous: string | undefined, value: unknown): string | undefined {
  if (value === undefined) return previous;
  const next = streamString(value);
  if (!next || (previous !== undefined && previous !== next)) throw new ModelProtocolError("stream item identity changed");
  return next;
}
