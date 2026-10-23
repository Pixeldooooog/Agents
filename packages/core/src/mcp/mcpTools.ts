import type { JsonObject } from "../types/jsonTypes.js";
import type { ToolDefinition, ToolExecutionContext } from "../tools/toolContracts.js";
import { numberArg, stringArg } from "../tools/toolInputs.js";
import { getMcpPrompt, listMcpPrompts, listMcpResources, readMcpResource } from "./mcpProviderCalls.js";
import {
  clearMcpServers,
  configureMcpServer,
  disableMcpServer,
  enableMcpServer,
  readMcpServers,
  removeMcpServer
} from "./mcpServerActions.js";
import {
  mcpConfigureSchema,
  mcpGetPromptSchema,
  mcpPromptsSchema,
  mcpReadResourceSchema,
  mcpResourcesSchema,
  mcpServerNameSchema
} from "./mcpToolSchemas.js";

export const mcpToolDefinitions: ToolDefinition[] = [
  { name: "mcp.servers", description: "Read configured and loaded MCP server status.", risk: "low", handler: readMcpServers },
  { name: "mcp.configure", description: "Configure an MCP server for this session scope.", risk: "medium", parameters: mcpConfigureSchema, handler: configureMcpServer },
  { name: "mcp.enable", description: "Enable a previously configured MCP server.", risk: "medium", parameters: mcpServerNameSchema, handler: enableMcpServer },
  { name: "mcp.disable", description: "Disable a configured MCP server without deleting it.", risk: "medium", parameters: mcpServerNameSchema, handler: disableMcpServer },
  { name: "mcp.remove", description: "Remove a saved MCP server configuration.", risk: "medium", parameters: mcpServerNameSchema, handler: removeMcpServer },
  { name: "mcp.clear", description: "Clear MCP server configuration and loaded providers.", risk: "medium", handler: clearMcpServers },
  { name: "mcp.prompts", description: "List prompt templates exposed by configured MCP servers.", risk: "low", parameters: mcpPromptsSchema, handler: mcpPrompts },
  { name: "mcp.get_prompt", description: "Render a prompt template exposed by a configured MCP server.", risk: "medium", parameters: mcpGetPromptSchema, handler: mcpGetPrompt },
  { name: "mcp.resources", description: "List resources exposed by configured MCP servers.", risk: "low", parameters: mcpResourcesSchema, handler: mcpResources },
  { name: "mcp.read_resource", description: "Read a resource exposed by a configured MCP server.", risk: "medium", parameters: mcpReadResourceSchema, handler: mcpReadResource }
];

async function mcpResources(context: ToolExecutionContext, args: JsonObject) {
  return listMcpResources(context, stringArg(args.server), stringArg(args.uri_prefix), numberArg(args.max_results, 50));
}

async function mcpReadResource(context: ToolExecutionContext, args: JsonObject) {
  return readMcpResource(context, stringArg(args.uri), stringArg(args.server));
}

async function mcpPrompts(context: ToolExecutionContext, args: JsonObject) {
  return listMcpPrompts(context, stringArg(args.server), stringArg(args.query), numberArg(args.max_results, 50));
}

async function mcpGetPrompt(context: ToolExecutionContext, args: JsonObject) {
  return getMcpPrompt(context, stringArg(args.name), stringArg(args.server), objectArg(args.arguments));
}

function objectArg(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}
