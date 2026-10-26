import type { JsonObject } from "../types/jsonTypes.js";
import type { PlanningStateRecord } from "../types/planningTypes.js";
import { defineTool, type RegisteredTool, type ToolContext } from "../tools/toolContracts.js";

type PlanningToolContext = ToolContext<"store">;
import { defaultPlanningState, normalizeAllowedPrompts, normalizeTodos, planningStateId, requiredText, todoSummary } from "./planningState.js";
import { planExitSchema, todoWriteSchema } from "./planningToolSchemas.js";

export const planningToolDefinitions: RegisteredTool[] = [
  defineTool({
    name: "todo.write",
    description: "Replace the current session todo list.",
    risk: "medium",
    parameters: todoWriteSchema,
    requires: ["store"],
    handler: todoWrite
  }),
  defineTool({
    name: "todo.read",
    description: "Read the current session todo list.",
    risk: "low",
    parameters: { type: "object", properties: {}, additionalProperties: false },
    requires: ["store"],
    handler: todoRead
  }),
  defineTool({
    name: "plan.enter",
    description: "Enter read-only planning mode for the current session.",
    risk: "low",
    parameters: { type: "object", properties: {} },
    requires: ["store"],
    handler: planEnter
  }),
  defineTool({
    name: "plan.status",
    description: "Read current plan mode state and todos.",
    risk: "low",
    parameters: { type: "object", properties: {} },
    requires: ["store"],
    handler: planStatus
  }),
  defineTool({
    name: "plan.exit",
    description: "Exit planning mode with a concrete plan.",
    risk: "medium",
    parameters: planExitSchema,
    requires: ["store"],
    handler: planExit
  })
];

async function todoWrite(context: PlanningToolContext, args: JsonObject): Promise<Record<string, unknown>> {
  const state = await loadPlanningState(context);
  const oldTodos = [...state.todos];
  const newTodos = normalizeTodos(args.todos);
  const activeTodos = newTodos.every((todo) => todo.status === "completed") ? [] : newTodos;
  const saved = await savePlanningState(context, { ...state, todos: activeTodos });
  return {
    oldTodos,
    newTodos,
    verificationNudgeNeeded: false,
    activeTodos: saved.todos,
    cleared: activeTodos.length === 0 && newTodos.length > 0,
    summary: todoSummary(saved.todos)
  };
}

async function todoRead(context: PlanningToolContext): Promise<Record<string, unknown>> {
  const state = await loadPlanningState(context);
  return { todos: state.todos, summary: todoSummary(state.todos) };
}

async function planEnter(context: PlanningToolContext): Promise<Record<string, unknown>> {
  const state = await loadPlanningState(context);
  await savePlanningState(context, { ...state, plan_mode: true });
  return {
    mode: "plan",
    message: "Entered plan mode. Explore and design the approach without editing files, then call plan.exit with the implementation plan when ready."
  };
}

async function planStatus(context: PlanningToolContext): Promise<Record<string, unknown>> {
  const state = await loadPlanningState(context);
  return {
    mode: state.plan_mode ? "plan" : "default",
    plan: state.plan,
    allowedPrompts: state.allowed_prompts,
    todos: state.todos
  };
}

async function planExit(context: PlanningToolContext, args: JsonObject): Promise<Record<string, unknown>> {
  const state = await loadPlanningState(context);
  if (!state.plan_mode) throw new Error("not in plan mode");
  const plan = requiredText(args.plan, "plan");
  const allowedPrompts = normalizeAllowedPrompts(args.allowedPrompts);
  const saved = await savePlanningState(context, { ...state, plan_mode: false, plan, allowed_prompts: allowedPrompts });
  const filePath = String(args.planFilePath || "").trim();
  return {
    mode: "default",
    plan: saved.plan,
    allowedPrompts: saved.allowed_prompts,
    message: "Exited plan mode. Continue only after the plan is accepted by the caller or approval policy.",
    ...(filePath ? { filePath } : {})
  };
}

async function loadPlanningState(context: PlanningToolContext): Promise<PlanningStateRecord> {
  const { store } = context;
  const stateId = planningStateId({ spec: context.spec, runId: context.runId });
  return (await store.loadPlanningState(stateId)) || defaultPlanningState({ spec: context.spec, runId: context.runId, stateId });
}

async function savePlanningState(context: PlanningToolContext, state: PlanningStateRecord): Promise<PlanningStateRecord> {
  return context.store.savePlanningState(state);
}

