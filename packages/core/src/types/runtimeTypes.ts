import type { PublicAgentSpec } from "./agentTypes.js";
import type { JsonObject } from "./jsonTypes.js";
import type { ModelUsage, ModelNativeContext } from "./modelTypes.js";

export type RuntimeEvent = {
  type: string;
  name?: string;
  payload?: JsonObject;
  raw?: unknown;
};

export type Message = {
  role: "system" | "user" | "assistant" | "tool";
  content: string;
  name?: string;
  tool_call_id?: string;
  tool_calls?: ToolCall[];
  model_context?: ModelNativeContext;
};

export type ToolCall = {
  id: string;
  name: string;
  arguments: JsonObject;
};

export type ToolResult = {
  tool_call_id: string;
  name: string;
  content: string;
  is_error: boolean;
};

export type AgentResult = {
  run_id: string;
  status: "finished" | "awaiting_approval" | "error" | "canceled";
  content: string;
  messages: Message[];
  tool_results: ToolResult[];
  events: RuntimeEvent[];
  pending_approval?: PendingApproval;
  model_usage?: ModelUsage;
};

export type PendingApproval = {
  approval_id: string;
  tool_call: ToolCall;
  messages: Message[];
  tool_results: ToolResult[];
};

export type RunStatus = "created" | "running" | "awaiting_approval" | "finished" | "error" | "canceled";

export type RunRecord = {
  run_id: string;
  agent_id: string;
  tenant_id: string;
  user_id: string;
  workspace_id: string;
  status: RunStatus;
  events: RuntimeEvent[];
  created_at: number;
  updated_at: number;
  metadata: Record<string, string>;
  spec: PublicAgentSpec;
  pending_approval?: PendingApproval;
};

export function runtimeEvent(type: string, payload: JsonObject = {}, name = ""): RuntimeEvent {
  return { type, name, payload };
}
