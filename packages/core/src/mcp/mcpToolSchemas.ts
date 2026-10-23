import { supportedMcpTransports } from "./mcpRecords.js";

export const mcpConfigureSchema = {
  type: "object",
  properties: {
    name: { type: "string" },
    command: { type: "string" },
    transport: { type: "string", enum: supportedMcpTransports },
    url: { type: "string" },
    headers: { type: "object", additionalProperties: { type: "string" } },
    auth_token: { type: "string" },
    authToken: { type: "string" },
    execution_mode: { type: "string" },
    sandbox_profile: { type: "string" },
    auth_required: { type: "boolean" },
    auth_url: { type: "string" },
    auth_status: { type: "string" },
    auth_message: { type: "string" }
  }
};

export const mcpServerNameSchema = {
  type: "object",
  properties: {
    name: { type: "string", description: "MCP server name. Defaults to current server." }
  }
};

export const mcpPromptsSchema = {
  type: "object",
  properties: {
    server: { type: "string" },
    query: { type: "string" },
    max_results: { type: "integer", minimum: 1, maximum: 100 }
  }
};

export const mcpGetPromptSchema = {
  type: "object",
  properties: {
    name: { type: "string" },
    server: { type: "string" },
    arguments: { type: "object", additionalProperties: true }
  },
  required: ["name"]
};

export const mcpResourcesSchema = {
  type: "object",
  properties: {
    server: { type: "string" },
    uri_prefix: { type: "string" },
    max_results: { type: "integer", minimum: 1, maximum: 100 }
  }
};

export const mcpReadResourceSchema = {
  type: "object",
  properties: {
    uri: { type: "string" },
    server: { type: "string" }
  },
  required: ["uri"]
};
