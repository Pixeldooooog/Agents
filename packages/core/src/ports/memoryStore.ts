import type { MemoryRecord } from "../types/memoryTypes.js";
import type { MemoryScopeFilter } from "../memory/memoryRecords.js";

export type MemoryStore = {
  saveMemory(memory: MemoryRecord): Promise<MemoryRecord>;
  loadMemory(memoryId: string): Promise<MemoryRecord | undefined>;
  listMemories(filters?: MemoryScopeFilter): Promise<MemoryRecord[]>;
  deleteMemory(memoryId: string): Promise<boolean>;
};
