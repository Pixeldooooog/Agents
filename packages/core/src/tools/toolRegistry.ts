import type { JsonObject } from "../types/jsonTypes.js";
import type { ModelToolDefinition } from "../types/modelTypes.js";
import type { ToolResult } from "../types/runtimeTypes.js";
import { runtimeEvent } from "../types/runtimeTypes.js";
import type { ToolDefinition, ToolExecution, ToolExecutionContext } from "./toolContracts.js";
import { commandToolDefinitions } from "./commandTools.js";
import { collaborationToolDefinitions } from "../collaboration/collaborationTools.js";
import { configToolDefinitions } from "../config/configTools.js";
import { extensionToolDefinitions } from "../extensions/extensionTools.js";
import { filesystemToolDefinitions } from "./filesystemTools.js";
import { gitToolDefinitions } from "./gitTools.js";
import { hookToolDefinitions } from "../hooks/hookTools.js";
import { memoryToolDefinitions } from "../memory/memoryTools.js";
import { createMetaToolDefinitions } from "./metaTools.js";
import { mcpToolDefinitions } from "../mcp/mcpTools.js";
import { patchToolDefinitions } from "./patchTools.js";
import { permissionToolDefinitions } from "./permissionTools.js";
import { planningToolDefinitions } from "../planning/planningTools.js";
import { processToolDefinitions } from "./processTools.js";
import { promptToolDefinitions } from "./promptTools.js";
import { scheduleToolDefinitions } from "../schedules/scheduleTools.js";
import { searchToolDefinitions } from "./searchTools.js";
import { sessionContextToolDefinitions } from "../session/sessionContextTools.js";
import { structuredToolDefinitions } from "./structuredTools.js";
import { taskToolDefinitions } from "../tasks/taskTools.js";
import { userInteractionToolDefinitions } from "./userInteractionTools.js";
import { browserToolDefinitions } from "../web/browserTools.js";
import { webToolDefinitions } from "../web/webTools.js";
import { lspToolDefinitions } from "../workspace/lspTools.js";
import { notebookToolDefinitions } from "../workspace/notebookTools.js";
import { worktreeToolDefinitions } from "../workspace/worktreeTools.js";
import { workflowToolDefinitions } from "../workflow/workflowTools.js";

const toolDefinitions: ToolDefinition[] = [
  ...filesystemToolDefinitions,
  ...searchToolDefinitions,
  ...patchToolDefinitions,
  ...gitToolDefinitions,
  ...processToolDefinitions,
  ...webToolDefinitions,
  ...browserToolDefinitions,
  ...notebookToolDefinitions,
  ...lspToolDefinitions,
  ...worktreeToolDefinitions,
  ...createMetaToolDefinitions(() => toolDefinitions),
  ...mcpToolDefinitions,
  ...extensionToolDefinitions,
  ...collaborationToolDefinitions,
  ...taskToolDefinitions,
  ...scheduleToolDefinitions,
  ...memoryToolDefinitions,
  ...planningToolDefinitions,
  ...sessionContextToolDefinitions,
  ...permissionToolDefinitions,
  ...hookToolDefinitions,
  ...structuredToolDefinitions,
  ...configToolDefinitions,
  ...userInteractionToolDefinitions,
  ...commandToolDefinitions,
  ...promptToolDefinitions,
  ...workflowToolDefinitions
];

const toolByName = new Map<string, ToolDefinition>();
for (const definition of toolDefinitions) {
  toolByName.set(definition.name, definition);
  toolByName.set(modelToolName(definition.name), definition);
}

export const builtinToolNames = toolDefinitions.map((definition) => definition.name);

export function listBuiltinTools() {
  return toolDefinitions.map(({ name, description, risk }) => ({ name, description, risk }));
}

export function canonicalToolName(name: string): string {
  return toolByName.get(name)?.name || name;
}

export function modelToolDefinitions(enabledToolNames: string[]): ModelToolDefinition[] {
  const selected = enabledToolNames.length
    ? enabledToolNames.flatMap((name) => toolByName.get(name) ? [toolByName.get(name)!] : [])
    : toolDefinitions;
  return [...new Set(selected)].map((definition) => ({
    name: modelToolName(definition.name),
    description: definition.description,
    parameters: {
      type: "object",
      additionalProperties: true,
      ...(definition.parameters || {})
    }
  }));
}

export async function executeBuiltinTool(repoRoot: string, name: string, args: JsonObject, context: Partial<ToolExecutionContext> = {}): Promise<ToolExecution> {
  const id = String(args.id || args.tool_call_id || `${name}:${Date.now()}`);
  const definition = toolByName.get(name);
  const canonicalName = definition?.name || name;
  const start = runtimeEvent("tool_start", { id, tool_call_id: id, name: canonicalName, requested_name: name, arguments: args }, canonicalName);
  if (!definition) return toolError(id, canonicalName, `unknown tool: ${name}`, [start]);
  try {
    const payload = await definition.handler({ ...context, repoRoot }, args);
    const content = typeof payload === "string" ? payload : JSON.stringify(payload);
    const result: ToolResult = { tool_call_id: id, name: canonicalName, content, is_error: false };
    return {
      events: [start, runtimeEvent("tool_result", { tool_call_id: id, name: canonicalName, content, is_error: false }, canonicalName)],
      result
    };
  } catch (error) {
    return toolError(id, canonicalName, error instanceof Error ? error.message : String(error), [start]);
  }
}

function modelToolName(name: string): string {
  return name.replace(/[^a-zA-Z0-9_-]/g, "__");
}

function toolError(id: string, name: string, content: string, events: ReturnType<typeof runtimeEvent>[]): ToolExecution {
  const result: ToolResult = { tool_call_id: id, name, content, is_error: true };
  return {
    events: [...events, runtimeEvent("tool_result", { tool_call_id: id, name, content, is_error: true }, name)],
    result
  };
}
