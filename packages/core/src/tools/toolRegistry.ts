import { mcpExternalTools } from "../mcp/mcpExternalTools.js";
import { prepareToolValidator } from "./toolValidation.js";
import { toolDefinitions } from "./builtinToolCatalog.js";
import { executeTool } from "./toolExecutor.js";
import type { JsonObject } from "../types/jsonTypes.js";
import type { ModelToolDefinition } from "../types/modelTypes.js";
import type { RegisteredTool, ToolExecution, ToolRuntimeContext } from "./toolContracts.js";

const toolByName = new Map<string, RegisteredTool>();
for (const definition of toolDefinitions) {
  prepareToolValidator(definition);
  toolByName.set(definition.name, definition);
  toolByName.set(modelToolName(definition.name), definition);
}

export const builtinToolNames = toolDefinitions.map((definition) => definition.name);

export function listBuiltinTools() {
  return toolDefinitions.map(({ name, description, risk, requires, uses = [] }) => ({ name, description, risk, requires: [...requires], uses: [...uses] }));
}

export function canonicalToolName(name: string): string {
  return toolByName.get(name)?.name || name;
}

export function modelToolDefinitions(enabledToolNames: string[], providers?: ToolRuntimeContext["mcpProviders"]): ModelToolDefinition[] {
  const available = new Map(toolByName);
  for (const tool of mcpExternalTools(providers)) available.set(tool.name, tool);
  const selected = enabledToolNames.length
    ? enabledToolNames.flatMap((name) => available.get(name) ? [available.get(name)!] : [])
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

export function executeBuiltinTool(repoRoot: string, name: string, args: JsonObject, context: Omit<ToolRuntimeContext, "repoRoot"> = {}): Promise<ToolExecution> {
  const definition = toolByName.get(name) || mcpExternalTools(context.mcpProviders).find(tool => tool.name === name);
  return executeTool(definition, repoRoot, name, args, context);
}

function modelToolName(name: string): string {
  return name.replace(/[^a-zA-Z0-9_-]/g, "__");
}
