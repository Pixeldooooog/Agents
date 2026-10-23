export type TodoStatus = "pending" | "in_progress" | "completed";

export type TodoItem = {
  content: string;
  status: TodoStatus;
  activeForm: string;
};

export type PlanAllowedPrompt = {
  tool: string;
  prompt: string;
};

export type PlanningStateRecord = {
  state_id: string;
  run_id: string;
  tenant_id: string;
  user_id: string;
  agent_id: string;
  workspace_id: string;
  plan_mode: boolean;
  plan: string;
  allowed_prompts: PlanAllowedPrompt[];
  todos: TodoItem[];
  updated_at: number;
};
