export type HookEvent = "before_request" | "after_response" | "pre_tool_use" | "post_tool_use" | "worktree_create" | "worktree_remove";
export type HookAction = "append_system" | "append_user" | "record" | "deny_tool" | "run_command";

export type HookRecord = {
  hook_id: string;
  short_id: string;
  event: HookEvent;
  name: string;
  action: HookAction;
  content: string;
  enabled: boolean;
  agent_id: string;
  tenant_id: string;
  user_id: string;
  workspace_id: string;
  metadata: Record<string, string>;
  created_at: number;
  updated_at: number;
  last_run_at: number;
  run_count: number;
};
