export type McpTransport = "stdio" | "sse" | "sse-ide" | "http" | "ws" | "ws-ide" | "sdk" | "claudeai-proxy" | string;

export type McpServerRecord = {
  name: string;
  command: string;
  transport: McpTransport;
  url: string;
  headers: Record<string, string>;
  execution_mode: string;
  sandbox_profile: string;
  auth_required: boolean;
  auth_url: string;
  auth_status: string;
  auth_message: string;
  enabled: boolean;
  tenant_id: string;
  user_id: string;
  agent_id: string;
  workspace_id: string;
  created_at: number;
  updated_at: number;
};
