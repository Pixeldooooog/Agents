import type { MemoryRecord } from "../types/memoryTypes.js";
import type { MemoryScopeFilter } from "../memory/memoryRecords.js";
import {
  deleteMemoryRecord,
  listMemoryRecords,
  loadMemoryRecord,
  saveMemoryRecord
} from "./memoryStateStore.js";
import type { JsonStateAccess } from "./jsonRunStore.js";

export type JsonMemoryStoreMethods = {
  saveMemory(memory: MemoryRecord): Promise<MemoryRecord>;
  loadMemory(memoryId: string): Promise<MemoryRecord | undefined>;
  listMemories(filters?: MemoryScopeFilter): Promise<MemoryRecord[]>;
  deleteMemory(memoryId: string): Promise<boolean>;
};

export function jsonMemoryStoreMethods(access: JsonStateAccess): JsonMemoryStoreMethods {
  return {
    saveMemory: (memory) => saveMemoryRecord(access.mutate, memory),
    loadMemory: (memoryId) => loadMemoryRecord(access.read, memoryId),
    listMemories: (filters = {}) => listMemoryRecords(access.read, filters),
    deleteMemory: (memoryId) => deleteMemoryRecord(access.mutate, memoryId)
  };
}
