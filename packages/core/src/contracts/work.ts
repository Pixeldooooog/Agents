import type { WorkScope } from "./execution.js";

export interface GoalContract {
  schemaVersion: 1;
  goalId: string;
  scope: WorkScope;
  objective: string;
  acceptance: string[];
  state: "active" | "waiting" | "paused" | "completed" | "cancelled";
  continuationGrantId?: string;
  evidenceRefs: string[];
}
export interface PlanContract {
  schemaVersion: 1;
  planId: string;
  version: number;
  goalId?: string;
  changeReason: string;
  steps: { stepId: string; taskId: string; dependsOn: string[] }[];
}
export interface RoutineContract {
  schemaVersion: 1;
  routineId: string;
  grantId: string;
  scope: WorkScope;
  trigger: { kind: "cron"; expression: string; timezone: string; repeatedTime: "once" | "twice" }
    | { kind: "event"; source: string; filterVersion: number };
  misfire: "skip" | "coalesce" | "bounded_replay";
  maxCatchUp: number;
  overlap: "skip" | "queue" | "coalesce";
  cooldownMs: number;
  notify: "meaningful_change" | "each_result";
}
