export type EntityReference = { task_id?: string; conversation_id?: string; action_id?: string };
export type EventContract = EntityReference & {
  event_id: string;
  schema_version: 1;
  occurred_at: string;
  type: string;
  actor: "user" | "agent" | "tool" | "system";
  payload: Record<string, unknown>;
} & ({ run_id: string; sequence: number } | { run_id?: never; sequence?: never });

export interface InputCommand {
  schemaVersion: 1;
  inputId: string;
  idempotencyKey: string;
  taskId?: string;
  runId: string;
  expectedRunVersion?: number;
  kind: "user_message" | "answer" | "pause" | "resume" | "cancel";
  state: "accepted" | "applied" | "rejected";
  payload: Record<string, unknown>;
  sequence: number;
}
