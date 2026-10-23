import type { TaskStatus } from "../types/taskTypes.js";

export type StoreScopeFilter = {
  tenant_id?: string;
  user_id?: string;
  agent_id?: string;
  workspace_id?: string;
};

export type RunListFilters = Omit<StoreScopeFilter, "workspace_id"> & {
  limit?: number;
};

export type TaskListFilters = StoreScopeFilter & {
  status?: TaskStatus;
  limit?: number;
};

export type TaskRecordUpdate = {
  title?: string;
  input?: string;
  status?: TaskStatus;
  metadata?: Record<string, string>;
};

export type AgentProfileFilters = Pick<StoreScopeFilter, "tenant_id" | "user_id">;

export type TeamMessageFilters = StoreScopeFilter & {
  team_id?: string;
  to_agent?: string;
  unread_only?: boolean;
  limit?: number;
};
