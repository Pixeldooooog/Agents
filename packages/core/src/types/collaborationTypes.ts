import type { PublicAgentSpec } from "./agentTypes.js";

export type AgentProfileRecord = {
  agent_id: string;
  name: string;
  tenant_id: string;
  user_id: string;
  spec: PublicAgentSpec;
  created_at: number;
  updated_at: number;
};

export type TeamMemberRecord = {
  agent_id: string;
  name: string;
  role: string;
  system_prompt: string;
  enabled_tools: string[];
  status: string;
};

export type TeamRecord = {
  team_id: string;
  name: string;
  description: string;
  members: Record<string, TeamMemberRecord>;
  agent_id: string;
  tenant_id: string;
  user_id: string;
  workspace_id: string;
  metadata: Record<string, string>;
  created_at: number;
  updated_at: number;
};

export type TeamMessageRecord = {
  message_id: string;
  team_id: string;
  from_agent: string;
  to_agent: string;
  message_type: string;
  message: string;
  read: boolean;
  agent_id: string;
  tenant_id: string;
  user_id: string;
  workspace_id: string;
  metadata: Record<string, string>;
  created_at: number;
  updated_at: number;
};
