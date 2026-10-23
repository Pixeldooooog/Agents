import type { McpSettings } from "../config/settings.js";
import type { JsonObject } from "../types/jsonTypes.js";
import type { McpServerRecord } from "../types/mcpTypes.js";
import type { McpProvider, ToolExecutionContext } from "../tools/toolContracts.js";
import { booleanArg, stringArg } from "../tools/toolInputs.js";

export const supportedMcpTransports = ["stdio", "sse", "sse-ide", "http", "ws", "ws-ide", "sdk", "claudeai-proxy"];

export function configuredMcpServerPayload(settings: McpSettings | undefined) {
  const command = settings?.serverCommand || "";
  const url = settings?.serverUrl || "";
  return {
    name: settings?.serverName || "",
    command,
    transport: settings?.serverTransport || "stdio",
    url,
    headers: settings?.serverHeaders || {},
    execution_mode: settings?.executionMode || "",
    sandbox_profile: settings?.sandboxProfile || "",
    auth_required: false,
    auth_url: "",
    auth_status: "",
    auth_message: "",
    enabled: Boolean(command || url)
  };
}

export function mcpServerRecordFromArgs(context: ToolExecutionContext, args: JsonObject): McpServerRecord {
  const settings = context.settings?.mcp;
  const transport = normalizeMcpTransport(stringArg(args.transport, settings?.serverTransport || "stdio"));
  const command = stringArg(args.command);
  const url = stringArg(args.url);
  if (transport === "stdio" && !command) throw new Error("command is required for stdio MCP servers");
  if (transport !== "stdio" && !url) throw new Error(`url is required for ${transport} MCP servers`);
  const now = Date.now() / 1000;
  return {
    ...mcpScope(context),
    name: stringArg(args.name, "default"),
    command,
    transport,
    url,
    headers: headersWithIdeAuth(coerceHeaders(args.headers), transport, stringArg(args.auth_token ?? args.authToken)),
    execution_mode: stringArg(args.execution_mode, settings?.executionMode || "trusted_control_plane"),
    sandbox_profile: stringArg(args.sandbox_profile, settings?.sandboxProfile || ""),
    auth_required: booleanArg(args.auth_required),
    auth_url: stringArg(args.auth_url),
    auth_status: stringArg(args.auth_status),
    auth_message: stringArg(args.auth_message),
    enabled: true,
    created_at: now,
    updated_at: now
  };
}

export async function listMcpRecords(context: ToolExecutionContext): Promise<McpServerRecord[]> {
  if (!context.store) return [];
  return context.store.listMcpServers(mcpScope(context));
}

export async function findMcpRecord(context: ToolExecutionContext, name: string): Promise<McpServerRecord | undefined> {
  const target = name || "default";
  return (await listMcpRecords(context)).find((record) => record.name === target);
}

export async function saveMcpRecord(context: ToolExecutionContext, record: McpServerRecord): Promise<McpServerRecord> {
  applyMcpRecordToSettings(context, record);
  if (!context.store) return record;
  return context.store.saveMcpServer(record);
}

export async function deleteMcpRecord(context: ToolExecutionContext, name: string): Promise<boolean> {
  if (!context.store) return false;
  return context.store.deleteMcpServer(name || "default", mcpScope(context));
}

export async function hydrateMcpSettings(context: ToolExecutionContext): Promise<void> {
  const active = (await listMcpRecords(context)).find((record) => record.enabled);
  if (active) applyMcpRecordToSettings(context, active);
}

export function applyMcpRecordToSettings(context: ToolExecutionContext, record: McpServerRecord): void {
  if (!context.settings) return;
  context.settings.mcp.serverName = record.name;
  context.settings.mcp.serverCommand = record.command;
  context.settings.mcp.serverTransport = record.transport;
  context.settings.mcp.serverUrl = record.url;
  context.settings.mcp.serverHeaders = { ...record.headers };
  context.settings.mcp.executionMode = record.execution_mode;
  context.settings.mcp.sandboxProfile = record.sandbox_profile;
}

export function clearMcpSettings(context: ToolExecutionContext): void {
  if (!context.settings) return;
  context.settings.mcp.serverName = "";
  context.settings.mcp.serverCommand = "";
  context.settings.mcp.serverUrl = "";
  context.settings.mcp.serverHeaders = {};
}

export function mcpProviderPayload(provider: McpProvider) {
  return {
    name: provider.server.name,
    transport: provider.server.transport || "stdio",
    url: provider.server.url || "",
    headers: String(Object.keys(provider.server.headers || {}).length),
    execution_mode: provider.server.execution_mode || "",
    auth_required: String(Boolean(provider.server.auth_required)),
    tools: String((provider.tools || []).length)
  };
}

export function mcpProviders(context: ToolExecutionContext, server = ""): McpProvider[] {
  const wanted = server.trim();
  const providers = context.mcpProviders || [];
  return wanted ? providers.filter((provider) => provider.server.name === wanted) : providers;
}

export async function closeMcpProviders(providers: McpProvider[]): Promise<void> {
  for (const provider of providers) await provider.close?.();
}

export function removeMcpProviders(context: ToolExecutionContext, name: string): number {
  const before = context.mcpProviders || [];
  context.mcpProviders = before.filter((provider) => provider.server.name !== name);
  return before.length - context.mcpProviders.length;
}

export function mcpScope(context: ToolExecutionContext) {
  return {
    tenant_id: context.spec?.tenant_id || "",
    user_id: context.spec?.user_id || "",
    agent_id: context.spec?.agent_id || "",
    workspace_id: context.spec?.workspace_id || ""
  };
}

export function normalizeMcpTransport(value: string): string {
  const transport = value.trim() || "stdio";
  if (!supportedMcpTransports.includes(transport)) throw new Error(`unsupported MCP transport: ${transport}`);
  return transport;
}

function coerceHeaders(value: unknown): Record<string, string> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, String(item)]));
}

function headersWithIdeAuth(headers: Record<string, string>, transport: string, authToken: string): Record<string, string> {
  if (transport !== "ws-ide" || !authToken || hasHeader(headers, "X-Claude-Code-Ide-Authorization")) return headers;
  return { ...headers, "X-Claude-Code-Ide-Authorization": authToken };
}

function hasHeader(headers: Record<string, string>, name: string): boolean {
  const wanted = name.toLowerCase();
  return Object.keys(headers).some((key) => key.toLowerCase() === wanted);
}
