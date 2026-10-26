import type { McpServerRecord } from "../types/mcpTypes.js";
import type { StoreScopeFilter } from "../store/storeFilters.js";

export type McpStore = {
  saveMcpServer(record: McpServerRecord): Promise<McpServerRecord>;
  listMcpServers(filters?: StoreScopeFilter): Promise<McpServerRecord[]>;
  deleteMcpServer(name: string, filters?: StoreScopeFilter): Promise<boolean>;
};
