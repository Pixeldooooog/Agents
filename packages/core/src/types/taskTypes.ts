import type { PublicAgentSpec } from "./agentTypes.js";

export type TaskStatus = "queued" | "running" | "paused" | "waiting_approval" | "completed" | "failed" | "cancelled";
export type TaskStepStatus = "pending" | "running" | "waiting_approval" | "succeeded" | "failed" | "skipped" | "cancelled";

export type TaskRecord = {
  task_id: string;
  title: string;
  input: string;
  agent_id: string;
  tenant_id: string;
  user_id: string;
  workspace_id: string;
  status: TaskStatus;
  created_at: number;
  updated_at: number;
  metadata: Record<string, string>;
  spec: PublicAgentSpec;
};

export type TaskStepRecord = {
  step_id: string;
  task_id: string;
  index: number;
  name: string;
  input: string;
  run_id: string;
  status: TaskStepStatus;
  output: string;
  error: string;
  created_at: number;
  updated_at: number;
  metadata: Record<string, string>;
};
