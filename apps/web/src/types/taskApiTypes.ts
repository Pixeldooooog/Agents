import type { AgentChatPayload, RuntimeRun } from "./agentApiTypes";

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
