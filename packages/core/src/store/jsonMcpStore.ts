import type { McpStore } from "../ports/mcpStore.js";
import type { McpServerRecord } from "../types/mcpTypes.js";
import {
  deleteMcpServerRecord,
  listMcpServerRecords,
  saveMcpServerRecord
} from "./mcpStateStore.js";
import type { JsonStateAccess } from "./jsonRunStore.js";
import type { StoreScopeFilter } from "./storeFilters.js";



export function jsonMcpStoreMethods(access: JsonStateAccess): McpStore {
  return {
    saveMcpServer: (record) => saveMcpServerRecord(access.mutate, record),
    listMcpServers: (filters = {}) => listMcpServerRecords(access.read, filters),
    deleteMcpServer: (name, filters = {}) => deleteMcpServerRecord(access.mutate, name, filters)
  };
}
