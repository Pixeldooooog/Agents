import {
  memoryMatchesContext,
  normalizeMemoryRecord,
  type MemoryScopeFilter
} from "../memory/memoryRecords.js";
import type { MemoryRecord } from "../types/memoryTypes.js";
import type { MutateState, ReadState } from "./stateStoreAccess.js";
import { clampLimit, timestamp } from "./storeHelpers.js";

export function saveMemoryRecord(mutate: MutateState, memory: MemoryRecord): Promise<MemoryRecord> {
  return mutate((state) => {
    const saved = normalizeMemoryRecord({ ...memory, updated_at: timestamp() });
    const index = state.memories.findIndex((item) => item.memory_id === saved.memory_id);
    if (index >= 0) state.memories[index] = saved;
    else state.memories.push(saved);
    return saved;
  });
}

export async function loadMemoryRecord(read: ReadState, memoryId: string): Promise<MemoryRecord | undefined> {
  return (await read()).memories.map(normalizeMemoryRecord).find((item) => item.memory_id === memoryId);
}

export async function listMemoryRecords(read: ReadState, filters: MemoryScopeFilter = {}): Promise<MemoryRecord[]> {
  const limit = clampLimit(filters.limit, 100, 100);
  return (await read()).memories
    .map(normalizeMemoryRecord)
    .filter((memory) => memoryMatchesContext(memory, filters))
    .sort((a, b) => a.created_at - b.created_at || a.memory_id.localeCompare(b.memory_id))
    .slice(-limit);
}

export function deleteMemoryRecord(mutate: MutateState, memoryId: string): Promise<boolean> {
  return mutate((state) => {
    const before = state.memories.length;
    state.memories = state.memories.filter((item) => item.memory_id !== memoryId);
    return state.memories.length !== before;
  });
}
