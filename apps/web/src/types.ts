export type Role = "user" | "assistant" | "system" | "event" | "error";

export type ChatMessage = {
  id: number;
  role: Role;
  content: string;
};

export type ActivityEventKind = "system" | "stream" | "tool" | "approval" | "code" | "search" | "browser" | "error";
export type ActivityEventStatus = "queued" | "running" | "waiting" | "done" | "error";

export type ActivityEvent = {
  id: number;
  kind: ActivityEventKind;
  title: string;
  detail: string;
  status: ActivityEventStatus;
  time: string;
};

export type OperationSceneKind = "workspace" | "edit" | "web" | "browser" | "terminal" | "git" | "document" | "summary";
export type OperationPhase = "opening" | "running" | "closing" | "done" | "error";

export type OperationEvent = {
  id: string;
  runId: string;
  toolCallId: string;
  toolName: string;
  scene: OperationSceneKind;
  phase: OperationPhase;
  title: string;
  target?: string;
  detail?: string;
  argsPreview?: Record<string, unknown>;
  resultPreview?: unknown;
  diffPreview?: unknown;
  artifacts?: unknown[];
  sources?: OperationSource[];
  files?: OperationFile[];
  stats?: Record<string, unknown>;
  sequence?: number;
  source?: string;
  step?: OperationStep;
  startedAt?: number;
  endedAt?: number;
};

export type OperationStep = {
  label: string;
  detail?: string;
};

export type OperationSource = {
  title: string;
  url: string;
  domain?: string;
  content?: string;
  score?: number;
};

export type OperationFile = {
  path: string;
  kind?: string;
  status?: string;
};

export const modelProtocols = ["openai-chat", "openai-responses", "claude-messages", "gemini"] as const;

export type PermissionMode = "auto" | "ask" | "deny";
export type ApprovalDecision = "allow_once" | "allow_for_run" | "deny";
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
  tool_call_ids: string[];
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

export type TaskRecord = {
  task_id: string;
  tenant_id: string;
  user_id: string;
  agent_id: string;
  workspace_id: string;
  title: string;
  input: string;
  status: string;
  metadata: Record<string, string>;
  created_at: number;
  updated_at: number;
  last_run_id: string;
};

export type TaskStepRecord = {
  step_id: string;
  task_id: string;
  run_id: string;
  status: string;
  output: string;
  error: string;
  created_at: number;
  updated_at: number;
};

export type TaskListResponse = {
  tasks: TaskRecord[];
};

export type TaskDetailResponse = {
  task: TaskRecord;
  steps: TaskStepRecord[];
};

export type TaskRunResponse = {
  task: TaskRecord;
  step: TaskStepRecord;
  run: RuntimeRun;
  result: {
    status: string;
    content: string;
    events: Array<Record<string, any>>;
  };
};

export type TaskCreatePayload = AgentChatPayload & {
  title?: string;
  metadata?: Record<string, string>;
};

export type SseEventFrame = {
  event: string;
  data: string;
  payload: any;
};
