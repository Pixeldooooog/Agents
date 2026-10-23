import type { AgentSpec } from "../types/agentTypes.js";
import type { PlanAllowedPrompt, PlanningStateRecord, TodoItem, TodoStatus } from "../types/planningTypes.js";

export const todoStatusValues: TodoStatus[] = ["pending", "in_progress", "completed"];

export function planningStateId(input: { spec?: AgentSpec; runId?: string }): string {
  if (input.runId) return `run:${input.runId}`;
  const spec = input.spec;
  return ["scope", spec?.tenant_id || "", spec?.user_id || "", spec?.agent_id || "", spec?.workspace_id || ""].join(":");
}

export function defaultPlanningState(input: { spec?: AgentSpec; runId?: string; stateId?: string }): PlanningStateRecord {
  return {
    state_id: input.stateId || planningStateId(input),
    run_id: input.runId || "",
    tenant_id: input.spec?.tenant_id || "",
    user_id: input.spec?.user_id || "",
    agent_id: input.spec?.agent_id || "",
    workspace_id: input.spec?.workspace_id || "",
    plan_mode: false,
    plan: "",
    allowed_prompts: [],
    todos: [],
    updated_at: timestamp()
  };
}

export function normalizePlanningState(value: Partial<PlanningStateRecord> & Record<string, unknown>): PlanningStateRecord {
  return {
    state_id: stringValue(value.state_id, "scope::::"),
    run_id: stringValue(value.run_id),
    tenant_id: stringValue(value.tenant_id),
    user_id: stringValue(value.user_id),
    agent_id: stringValue(value.agent_id),
    workspace_id: stringValue(value.workspace_id),
    plan_mode: Boolean(value.plan_mode),
    plan: stringValue(value.plan),
    allowed_prompts: normalizeAllowedPrompts(value.allowed_prompts),
    todos: normalizeTodos(Array.isArray(value.todos) ? value.todos : []),
    updated_at: numberValue(value.updated_at, timestamp())
  };
}

export function normalizeTodos(value: unknown): TodoItem[] {
  if (!Array.isArray(value)) throw new Error("todos must be a list");
  const todos = value.map(normalizeTodo);
  if (todos.filter((todo) => todo.status === "in_progress").length > 1) {
    throw new Error("only one todo can be in_progress");
  }
  return todos;
}

export function normalizeAllowedPrompts(value: unknown): PlanAllowedPrompt[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => {
    if (!item || typeof item !== "object") throw new Error("allowedPrompts items must be objects");
    const payload = item as Record<string, unknown>;
    return {
      tool: requiredText(payload.tool, "tool"),
      prompt: requiredText(payload.prompt, "prompt")
    };
  });
}

export function todoSummary(todos: TodoItem[]): Record<TodoStatus, number> {
  return {
    pending: todos.filter((todo) => todo.status === "pending").length,
    in_progress: todos.filter((todo) => todo.status === "in_progress").length,
    completed: todos.filter((todo) => todo.status === "completed").length
  };
}

export function requiredText(value: unknown, name: string): string {
  const text = String(value || "").trim();
  if (!text) throw new Error(`${name} is required`);
  return text;
}

function normalizeTodo(value: unknown): TodoItem {
  if (!value || typeof value !== "object") throw new Error("todo items must be objects");
  const payload = value as Record<string, unknown>;
  return {
    content: requiredText(payload.content, "content"),
    status: normalizeTodoStatus(payload.status),
    activeForm: requiredText(payload.activeForm || payload.active_form, "activeForm")
  };
}

function normalizeTodoStatus(value: unknown): TodoStatus {
  const status = String(value || "").trim();
  if (todoStatusValues.includes(status as TodoStatus)) return status as TodoStatus;
  throw new Error(`unknown todo status: ${status}`);
}

function stringValue(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function numberValue(value: unknown, fallback: number): number {
  const numericValue = Number(value);
  return Number.isFinite(numericValue) ? numericValue : fallback;
}

function timestamp(): number {
  return Date.now() / 1000;
}
