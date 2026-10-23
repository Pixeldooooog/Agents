import type { McpServerRecord } from "../types/mcpTypes.js";
import {
  mcpServerKey,
  normalizeMcpServerRecord
} from "../mcp/mcpStoredRecords.js";
import type { MutateState, ReadState } from "./stateStoreAccess.js";
import type { StoreScopeFilter } from "./storeFilters.js";
import { matchesScope, timestamp } from "./storeHelpers.js";

export function saveMcpServerRecord(mutate: MutateState, record: McpServerRecord): Promise<McpServerRecord> {
  return mutate((state) => {
    const saved = normalizeMcpServerRecord({ ...record, updated_at: timestamp() });
    const index = state.mcpServers.findIndex((item) => mcpServerKey(item) === mcpServerKey(saved));
    if (index >= 0) state.mcpServers[index] = saved;
    else state.mcpServers.unshift(saved);
    return saved;
  });
}

export async function listMcpServerRecords(read: ReadState, filters: StoreScopeFilter = {}): Promise<McpServerRecord[]> {
  return (await read()).mcpServers
    .map(normalizeMcpServerRecord)
    .filter((server) => matchesScope(server, filters))
    .sort((a, b) => b.updated_at - a.updated_at || a.name.localeCompare(b.name));
}

export function deleteMcpServerRecord(mutate: MutateState, name: string, filters: StoreScopeFilter = {}): Promise<boolean> {
  return mutate((state) => {
    const target = name || "default";
    const before = state.mcpServers.length;
    state.mcpServers = state.mcpServers.filter((server) => server.name !== target || !matchesScope(server, filters));
    return state.mcpServers.length !== before;
  });
}
