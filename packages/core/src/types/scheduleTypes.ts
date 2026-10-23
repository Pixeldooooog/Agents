export type ScheduleRecord = {
  schedule_id: string;
  short_id: string;
  title: string;
  input: string;
  schedule: string;
  enabled: boolean;
  agent_id: string;
  tenant_id: string;
  user_id: string;
  workspace_id: string;
  metadata: Record<string, string>;
  created_at: number;
  updated_at: number;
  last_run_task_id: string;
  last_run_at: number;
};
