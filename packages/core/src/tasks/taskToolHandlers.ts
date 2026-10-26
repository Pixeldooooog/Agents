import type { JsonObject } from "../types/jsonTypes.js";
import { defaultTaskTitle } from "./taskTitles.js";
import {
  boundedLimit,
  metadataPatch,
  normalizeTaskStatus,
  optionalText,
  requiredSpec,
  type TaskToolContext,
  requiredText,
  stringMetadata,
  truncateText
} from "./taskToolInputs.js";
import { createTaskForRun, resolveScopedTask } from "./taskToolScope.js";

export async function handleTaskCreate(context: TaskToolContext, args: JsonObject): Promise<Record<string, unknown>> {
  const input = requiredText(args.input || args.title, "input");
  const task = await context.store.createTask(
    requiredSpec(context),
    input,
    String(args.title || defaultTaskTitle(input)),
    { source: "tool", ...stringMetadata(args.metadata) }
  );
  return { task };
}

export async function handleTaskList(context: TaskToolContext, args: JsonObject = {}): Promise<Record<string, unknown>> {
  const spec = context.spec;
  const tasks = await context.store.listTasks({
    tenant_id: spec?.tenant_id,
    user_id: spec?.user_id,
    agent_id: String(args.agent_id || spec?.agent_id || ""),
    workspace_id: spec?.workspace_id,
    status: args.status ? normalizeTaskStatus(args.status) : undefined,
    limit: boundedLimit(args.limit, 50)
  });
  return { tasks, count: tasks.length, total: tasks.length };
}

export async function handleTaskGet(context: TaskToolContext, args: JsonObject): Promise<Record<string, unknown>> {
  const task = await resolveScopedTask(context, requiredText(args.task_id, "task_id"));
  return { task, steps: await context.store.listSteps(task.task_id) };
}

export async function handleTaskUpdate(context: TaskToolContext, args: JsonObject): Promise<Record<string, unknown>> {
  const task = await resolveScopedTask(context, requiredText(args.task_id, "task_id"));
  const metadata = metadataPatch(task.metadata, args.metadata);
  const updated = await context.store.updateTask(task.task_id, {
    title: optionalText(args.title),
    input: optionalText(args.input),
    status: args.status ? normalizeTaskStatus(args.status) : undefined,
    metadata
  });
  if (!updated) throw new Error(`task not found: ${task.task_id}`);
  return { task: updated };
}

export async function handleTaskStop(context: TaskToolContext, args: JsonObject): Promise<Record<string, unknown>> {
  const task = await resolveScopedTask(context, requiredText(args.task_id, "task_id"));
  const canceledTask = context.taskRunner ? await context.taskRunner.cancel(task.task_id) : await context.store.updateTask(task.task_id, { status: "cancelled" });
  return { task: canceledTask };
}

export async function handleTaskOutput(context: TaskToolContext, args: JsonObject): Promise<Record<string, unknown>> {
  const task = await resolveScopedTask(context, requiredText(args.task_id, "task_id"));
  const steps = await context.store.listSteps(task.task_id);
  const output = truncateText(steps.map((step) => step.output || step.error).filter(Boolean).join("\n\n"), boundedLimit(args.max_bytes, 20000, 200000));
  return { task, output, steps };
}

export async function handleTaskRun(context: TaskToolContext, args: JsonObject): Promise<Record<string, unknown>> {
  const task = args.task_id
    ? await resolveScopedTask(context, requiredText(args.task_id, "task_id"))
    : await createTaskForRun(context, args, "task.run");
  if (!context.taskRunner) return { task, result: { status: task.status, content: "", runner_available: false } };
  return await context.taskRunner.run(task.task_id) as Record<string, unknown>;
}

export async function handleTaskBackground(context: TaskToolContext, args: JsonObject): Promise<Record<string, unknown>> {
  const task = args.task_id
    ? await resolveScopedTask(context, requiredText(args.task_id, "task_id"))
    : await createTaskForRun(context, args, "task.background");
  return { task, background: { running: false, done: false, runner_available: Boolean(context.taskRunner) } };
}

export async function handleTaskBackgrounds(): Promise<Record<string, unknown>> {
  return { background_tasks: [], count: 0 };
}
