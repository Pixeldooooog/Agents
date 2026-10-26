import type { RunState } from "../contracts/execution.js";
import type { EventContract } from "../contracts/events.js";
import type { PublicAgentSpec } from "./agentTypes.js";
import type { JsonObject } from "./jsonTypes.js";
import type { ModelUsage, ModelNativeContext } from "./modelTypes.js";

export type RuntimeEvent = {
  type: string;
  name?: string;
  payload?: JsonObject;
  raw?: unknown;
};

/** A runtime event after the run store assigned its contract identity; sequence is ordered within one run. */
export type PersistedRunEvent = RuntimeEvent & Pick<EventContract, "event_id" | "schema_version" | "occurred_at" | "actor"> & {
  run_id: string;
  sequence: number;
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

/** Run states a single runtime attempt can end in; a subset of the contract RunState. */
export type RunOutcome = Extract<RunState, "completed" | "waiting_approval" | "failed" | "cancelled">;

export type AgentResult = {
  run_id: string;
  status: RunOutcome;
  content: string;
  messages: Message[];
  tool_results: ToolResult[];
  events: RuntimeEvent[];
  pending_approval?: PendingApproval;
  model_usage?: ModelUsage;
};

export type ToolTurnContinuation = {
  remaining_tool_calls: ToolCall[];
  completed_tool_iterations: number;
  max_tool_iterations: number;
  model_turn_count: number;
  model_usage?: ModelUsage;
  started_at: number;
};

export type PendingApproval = {
  approval_id: string;
  continuation?: ToolTurnContinuation;
  tool_call: ToolCall;
  messages: Message[];
  tool_results: ToolResult[];
};

export type RunRecord = {
  run_id: string;
  agent_id: string;
  tenant_id: string;
  user_id: string;
  workspace_id: string;
  status: RunState;
  /** Incremented on every state transition. */
  version: number;
  events: PersistedRunEvent[];
  created_at: number;
  updated_at: number;
  metadata: Record<string, string>;
  spec: PublicAgentSpec;
  pending_approval?: PendingApproval;
};

export function runtimeEvent(type: string, payload: JsonObject = {}, name = ""): RuntimeEvent {
  return { type, name, payload };
}
