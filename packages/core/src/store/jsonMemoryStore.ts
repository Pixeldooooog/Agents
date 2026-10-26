import type { MemoryStore } from "../ports/memoryStore.js";
import type { MemoryRecord } from "../types/memoryTypes.js";
import type { MemoryScopeFilter } from "../memory/memoryRecords.js";
import {
  deleteMemoryRecord,
  listMemoryRecords,
  loadMemoryRecord,
  saveMemoryRecord
} from "./memoryStateStore.js";
import type { JsonStateAccess } from "./jsonRunStore.js";



export function jsonMemoryStoreMethods(access: JsonStateAccess): MemoryStore {
  return {
    saveMemory: (memory) => saveMemoryRecord(access.mutate, memory),
    loadMemory: (memoryId) => loadMemoryRecord(access.read, memoryId),
    listMemories: (filters = {}) => listMemoryRecords(access.read, filters),
    deleteMemory: (memoryId) => deleteMemoryRecord(access.mutate, memoryId)
  };
}
