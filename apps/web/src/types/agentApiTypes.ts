export const modelProtocols = ["openai-chat", "openai-responses", "claude-messages", "gemini"] as const;

export type PermissionMode = "auto" | "ask" | "deny";
export type ApprovalDecision = "allow_once" | "deny";

export type ToolImpact = {
  tool_name?: string;
  risk?: string;
  paths?: string[];
  commands?: string[];
  domains?: string[];
  diff_preview?: string;
  cost_estimate?: Record<string, unknown>;
};

export type ToolApprovalRequest = {
  approvalId: string;
  runId: string;
  toolName: string;
  arguments: Record<string, unknown>;
  reason: string;
  impact: ToolImpact;
};

export type AgentChatPayload = {
  message: string;
  previous_run_id?: string;
  protocol?: string;
  model?: string;
  base_url?: string;
  api_key?: string;
  system_prompt?: string;
  enabled_tools?: string[];
  permission_profile?: PermissionMode;
  tenant_id?: string;
  user_id?: string;
  agent_id?: string;
  workspace_id?: string;
};

export type RunApprovalPayload = {
  approved: boolean;
  decision: ApprovalDecision;
  approval_id: string;
};

export type RuntimeRun = {
  run_id: string;
  tenant_id: string;
  user_id: string;
  agent_id: string;
  workspace_id: string;
  status: string;
  events: Array<Record<string, unknown>>;
  created_at: number;
  updated_at: number;
};

export type RunListResponse = {
  runs: RuntimeRun[];
};

export type RunTraceResponse = {
  run_id: string;
  spans: Array<Record<string, any>>;
  approvals: Array<Record<string, any>>;
  artifacts: Array<Record<string, any>>;
  operation_frames?: Array<Record<string, any>>;
  sandbox_events: Array<Record<string, any>>;
  sandbox_snapshots?: Array<Record<string, any>>;
  sandbox_leases?: Array<Record<string, any>>;
};

export type ModelProfile = {
  name: string;
  protocol: string;
  model: string;
  base_url: string;
  endpoint: string;
  aliases: string[];
  source: string;
  configured: boolean;
};

export type ModelProfilesResponse = {
  active_profile: string;
  profiles: ModelProfile[];
};

export type SseEventFrame = {
  event: string;
  data: string;
  payload: { type: string; name?: string; payload?: Record<string, unknown> };
};
