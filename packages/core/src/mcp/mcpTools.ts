import type { JsonObject } from "../types/jsonTypes.js";
import { defineTool, type RegisteredTool } from "../tools/toolContracts.js";
import type { McpToolContext } from "./mcpRecords.js";
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

export const mcpToolDefinitions: RegisteredTool[] = [
  defineTool({ name: "mcp.servers", parameters: { type: "object", properties: {}, additionalProperties: false }, description: "Read configured and loaded MCP server status.", risk: "low", requires: [], uses: ["store", "settings", "mcpProviders"], handler: readMcpServers }),
  defineTool({ name: "mcp.configure", description: "Configure an MCP server for this session scope.", risk: "medium", parameters: mcpConfigureSchema, requires: [], uses: ["store", "settings", "mcpProviders"], handler: configureMcpServer }),
  defineTool({ name: "mcp.enable", description: "Enable a previously configured MCP server.", risk: "medium", parameters: mcpServerNameSchema, requires: [], uses: ["store", "settings", "mcpProviders"], handler: enableMcpServer }),
  defineTool({ name: "mcp.disable", description: "Disable a configured MCP server without deleting it.", risk: "medium", parameters: mcpServerNameSchema, requires: [], uses: ["store", "settings", "mcpProviders"], handler: disableMcpServer }),
  defineTool({ name: "mcp.remove", description: "Remove a saved MCP server configuration.", risk: "medium", parameters: mcpServerNameSchema, requires: [], uses: ["store", "settings", "mcpProviders"], handler: removeMcpServer }),
  defineTool({ name: "mcp.clear", parameters: { type: "object", properties: {}, additionalProperties: false }, description: "Clear MCP server configuration and loaded providers.", risk: "medium", requires: [], uses: ["store", "settings", "mcpProviders"], handler: clearMcpServers }),
  defineTool({ name: "mcp.prompts", description: "List prompt templates exposed by configured MCP servers.", risk: "low", parameters: mcpPromptsSchema, requires: [], uses: ["store", "settings", "mcpProviders"], handler: mcpPrompts }),
  defineTool({ name: "mcp.get_prompt", description: "Render a prompt template exposed by a configured MCP server.", risk: "medium", parameters: mcpGetPromptSchema, requires: [], uses: ["store", "settings", "mcpProviders"], handler: mcpGetPrompt }),
  defineTool({ name: "mcp.resources", description: "List resources exposed by configured MCP servers.", risk: "low", parameters: mcpResourcesSchema, requires: [], uses: ["store", "settings", "mcpProviders"], handler: mcpResources }),
  defineTool({ name: "mcp.read_resource", description: "Read a resource exposed by a configured MCP server.", risk: "medium", parameters: mcpReadResourceSchema, requires: [], uses: ["store", "settings", "mcpProviders"], handler: mcpReadResource })
];

async function mcpResources(context: McpToolContext, args: JsonObject) {
  return listMcpResources(context, stringArg(args.server), stringArg(args.uri_prefix), numberArg(args.max_results, 50));
}

async function mcpReadResource(context: McpToolContext, args: JsonObject) {
  return readMcpResource(context, stringArg(args.uri), stringArg(args.server));
}

async function mcpPrompts(context: McpToolContext, args: JsonObject) {
  return listMcpPrompts(context, stringArg(args.server), stringArg(args.query), numberArg(args.max_results, 50));
}

async function mcpGetPrompt(context: McpToolContext, args: JsonObject) {
  return getMcpPrompt(context, stringArg(args.name), stringArg(args.server), objectArg(args.arguments));
}

function objectArg(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}
