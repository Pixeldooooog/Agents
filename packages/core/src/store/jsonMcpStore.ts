import type { McpServerRecord } from "../types/mcpTypes.js";
import {
  deleteMcpServerRecord,
  listMcpServerRecords,
  saveMcpServerRecord
} from "./mcpStateStore.js";
import type { JsonStateAccess } from "./jsonRunStore.js";
import type { StoreScopeFilter } from "./storeFilters.js";

export type JsonMcpStoreMethods = {
  saveMcpServer(record: McpServerRecord): Promise<McpServerRecord>;
  listMcpServers(filters?: StoreScopeFilter): Promise<McpServerRecord[]>;
  deleteMcpServer(name: string, filters?: StoreScopeFilter): Promise<boolean>;
};

export function jsonMcpStoreMethods(access: JsonStateAccess): JsonMcpStoreMethods {
  return {
    saveMcpServer: (record) => saveMcpServerRecord(access.mutate, record),
    listMcpServers: (filters = {}) => listMcpServerRecords(access.read, filters),
    deleteMcpServer: (name, filters = {}) => deleteMcpServerRecord(access.mutate, name, filters)
  };
}
