export type MemoryScope = "user" | "agent" | "workspace" | "run";

export type MemoryRecord = {
  memory_id: string;
  short_id: string;
  tenant_id: string;
  user_id: string;
  agent_id: string;
  workspace_id: string;
  scope: MemoryScope;
  content: string;
  metadata: Record<string, string>;
  created_at: number;
  updated_at: number;
};
