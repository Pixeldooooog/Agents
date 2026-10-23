import type { JsonStateStore } from "../store/jsonStateStore.js";
import { matchesScope } from "../store/storeHelpers.js";
import type { StoreScopeFilter } from "../store/storeFilters.js";
import type { TaskRecord } from "../types/taskTypes.js";

export async function resolveTaskInScope(
  store: Pick<JsonStateStore, "listTasks" | "loadTask">,
  taskId: string,
  scope: StoreScopeFilter = {}
): Promise<TaskRecord> {
  const targetTaskId = taskId.trim();
  if (!targetTaskId) throw new Error("task_id is required");

  const exactTask = await store.loadTask(targetTaskId);
  if (exactTask && matchesScope(exactTask, scope)) return exactTask;

  const scopedTasks = await store.listTasks({ ...scope, limit: 100 });
  const exactScopedTask = scopedTasks.find((task) => task.task_id === targetTaskId);
  if (exactScopedTask) return exactScopedTask;

  const shortTarget = targetTaskId.replace(/^task_/, "");
  const matchingTasks = scopedTasks.filter((task) => shortTaskId(task.task_id).startsWith(shortTarget));
  if (!matchingTasks.length) throw new Error(`task not found: ${targetTaskId}`);
  if (matchingTasks.length > 1) throw new Error(`task id is ambiguous: ${targetTaskId}`);
  return matchingTasks[0];
}

function shortTaskId(taskId: string): string {
  return String(taskId || "").replace(/^task_/, "").slice(0, 12);
}
