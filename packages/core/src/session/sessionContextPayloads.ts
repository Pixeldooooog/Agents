import { planningStateId } from "../planning/planningState.js";
import type { Message } from "../types/runtimeTypes.js";
import type { ToolExecutionContext } from "../tools/toolContracts.js";

export async function loadPlanningState(context: ToolExecutionContext) {
  if (!context.store) return undefined;
  return context.store.loadPlanningState(planningStateId({ spec: context.spec, runId: context.runId }));
}

export function workspacePayload(context: ToolExecutionContext): Record<string, string> {
  return {
    tenant_id: context.spec?.tenant_id || "",
    user_id: context.spec?.user_id || "",
    agent_id: context.spec?.agent_id || "",
    workspace_id: context.spec?.workspace_id || "",
    path: context.repoRoot
  };
}

export function filteredMessages(messages: Message[], includeSystem: boolean): Message[] {
  return includeSystem ? [...messages] : messages.filter((message) => message.role !== "system");
}

export function roleCounts(messages: Message[]): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const message of messages) counts[message.role] = (counts[message.role] || 0) + 1;
  return counts;
}
