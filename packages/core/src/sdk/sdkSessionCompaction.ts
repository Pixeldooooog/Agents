import type { RuntimeEvent } from "../types/runtimeTypes.js";

export type SdkSessionReplayEvent = {
  event: RuntimeEvent;
};

export function compactSdkSessionReplayEvents<T extends SdkSessionReplayEvent>(entries: T[]): T[] {
  const boundaryIndex = lastCompactBoundaryIndex(entries);
  if (boundaryIndex < 0) return entries;

  const boundary = entries[boundaryIndex];
  const segment = preservedSegment(boundary.event);
  if (!segment) return entries.slice(boundaryIndex);

  const preserved = preservedEntries(entries.slice(0, boundaryIndex), segment);
  if (!preserved) return entries;
  const preservedIds = new Set(preserved.map((entry) => eventUuid(entry.event)).filter(Boolean));
  return [
    boundary,
    ...preserved,
    ...entries.slice(boundaryIndex + 1).filter((entry) => !preservedIds.has(eventUuid(entry.event)))
  ];
}

function lastCompactBoundaryIndex(entries: SdkSessionReplayEvent[]): number {
  for (let index = entries.length - 1; index >= 0; index -= 1) {
    if (entries[index].event.type === "compact_boundary") return index;
  }
  return -1;
}

function preservedSegment(event: RuntimeEvent): { headUuid: string; tailUuid: string } | undefined {
  const payload = event.payload || {};
  const metadata = recordValue(payload.preserved_segment || payload.preservedSegment);
  const headUuid = String(metadata.head_uuid || metadata.headUuid || "");
  const tailUuid = String(metadata.tail_uuid || metadata.tailUuid || "");
  return headUuid && tailUuid ? { headUuid, tailUuid } : undefined;
}

function preservedEntries<T extends SdkSessionReplayEvent>(
  entries: T[],
  segment: { headUuid: string; tailUuid: string }
): T[] | undefined {
  const headIndex = eventIndex(entries, segment.headUuid);
  const tailIndex = eventIndex(entries, segment.tailUuid);
  if (headIndex < 0 || tailIndex < 0 || tailIndex < headIndex) return undefined;
  return entries.slice(headIndex, tailIndex + 1).filter((entry) => eventUuid(entry.event));
}

function eventIndex(entries: SdkSessionReplayEvent[], messageId: string): number {
  return entries.findIndex((entry) => eventUuid(entry.event) === messageId);
}

function eventUuid(event: RuntimeEvent): string {
  const payload = event.payload || {};
  for (const key of ["uuid", "message_id", "messageId", "id"]) {
    const value = payload[key];
    if (value) return String(value);
  }
  const message = recordValue(payload.message);
  for (const key of ["uuid", "message_id", "messageId", "id"]) {
    const value = message[key];
    if (value) return String(value);
  }
  return "";
}

function recordValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}
