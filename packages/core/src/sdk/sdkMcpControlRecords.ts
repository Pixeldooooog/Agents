import type { McpSettings } from "../config/settings.js";
import { normalizeMcpTransport } from "../mcp/mcpRecords.js";
import type { StoreScopeFilter } from "../store/storeFilters.js";
import type { McpServerRecord } from "../types/mcpTypes.js";
import type { SdkMcpServerConfig } from "./sdkControlTypes.js";
import { sdkOptionScope } from "./sdkProtocolOptionAccess.js";
import type { SdkControlRequestHandlerContext } from "./sdkProtocolRunner.js";

const ideAuthHeader = "X-Claude-Code-Ide-Authorization";

export function mcpControlScope(context: SdkControlRequestHandlerContext): StoreScopeFilter {
  return sdkOptionScope(context.options);
}

export function configuredMcpServerStatus(settings: McpSettings): Record<string, unknown> | undefined {
  const hasEndpoint = settings.serverTransport === "stdio" ? settings.serverCommand : settings.serverUrl;
  if (!settings.serverName && !hasEndpoint) return undefined;
  return {
    name: settings.serverName || "default",
    transport: settings.serverTransport,
    url: settings.serverUrl,
    enabled: Boolean(hasEndpoint),
    authRequired: false,
    status: hasEndpoint ? "connected" : "disabled"
  };
}

export function sdkMcpServerStatus(name: string): Record<string, unknown> {
  return {
    name,
    transport: "sdk",
    url: "",
    enabled: true,
    authRequired: false,
    authStatus: "",
    status: "connected"
  };
}

export function sdkMcpServerRecord(name: string, enabled: boolean, scope: StoreScopeFilter): McpServerRecord {
  const now = Date.now() / 1000;
  return {
    name,
    command: "",
    transport: "sdk",
    url: "",
    headers: {},
    execution_mode: "trusted_control_plane",
    sandbox_profile: "",
    auth_required: false,
    auth_url: "",
    auth_status: "",
    auth_message: "",
    enabled,
    tenant_id: stringField(scope.tenant_id),
    user_id: stringField(scope.user_id),
    agent_id: stringField(scope.agent_id),
    workspace_id: stringField(scope.workspace_id),
    created_at: now,
    updated_at: now
  };
}

export function mergeMcpServerStatuses(
  base: Array<Record<string, unknown>>,
  extra: Array<Record<string, unknown>>
): Array<Record<string, unknown>> {
  const merged = new Map<string, Record<string, unknown>>();
  for (const item of [...base, ...extra]) {
    const name = stringField(item.name);
    if (name) merged.set(name, { ...item, name });
  }
  return [...merged.values()].sort((a, b) => stringField(a.name).localeCompare(stringField(b.name)));
}

export function mcpRecordFromControlConfig(
  name: string,
  config: SdkMcpServerConfig,
  scope: StoreScopeFilter,
  existing?: McpServerRecord
): McpServerRecord {
  const transport = normalizeMcpTransport(stringField(config.transport || config.type, "stdio"));
  const command = commandFromConfig(config);
  const url = stringField(config.url);
  if (transport === "stdio" && !command) throw new Error("command is required for stdio MCP servers");
  if (transport !== "stdio" && transport !== "sdk" && !url) throw new Error(`url is required for ${transport} MCP servers`);

  const now = Date.now() / 1000;
  return {
    name,
    command,
    transport,
    url,
    headers: headersWithIdeAuth(coerceHeaders(config.headers), transport, stringField(config.authToken)),
    execution_mode: stringField(config.executionMode, "trusted_control_plane"),
    sandbox_profile: stringField(config.sandboxProfile),
    auth_required: booleanField(config.authRequired),
    auth_url: stringField(config.authUrl),
    auth_status: stringField(config.authStatus),
    auth_message: stringField(config.authMessage),
    enabled: config.enabled !== false,
    tenant_id: stringField(scope.tenant_id),
    user_id: stringField(scope.user_id),
    agent_id: stringField(scope.agent_id),
    workspace_id: stringField(scope.workspace_id),
    created_at: existing?.created_at || now,
    updated_at: existing?.updated_at || now
  };
}

export function mcpRecordStatus(record: McpServerRecord): Record<string, unknown> {
  return {
    name: record.name,
    transport: record.transport,
    url: record.url,
    enabled: record.enabled,
    authRequired: record.auth_required,
    authStatus: record.auth_status,
    status: mcpStatus(record)
  };
}

export function mcpStatus(record: McpServerRecord): string {
  if (!record.enabled) return "disabled";
  const status = record.auth_status.trim().toLowerCase();
  if (record.auth_required && !["authenticated", "connected", "ok", "ready"].includes(status)) return "needs-auth";
  if (["failed", "error"].includes(status)) return "failed";
  if (status === "pending") return "pending";
  return "connected";
}

function commandFromConfig(config: SdkMcpServerConfig): string {
  return [stringField(config.command), ...stringArray(config.args)]
    .filter(Boolean)
    .join(" ")
    .trim();
}

function coerceHeaders(value: unknown): Record<string, string> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, String(item)]));
}

function headersWithIdeAuth(headers: Record<string, string>, transport: string, authToken: string): Record<string, string> {
  if (transport !== "ws-ide" || !authToken || hasHeader(headers, ideAuthHeader)) return headers;
  return { ...headers, [ideAuthHeader]: authToken };
}

function hasHeader(headers: Record<string, string>, name: string): boolean {
  const wanted = name.toLowerCase();
  return Object.keys(headers).some((key) => key.toLowerCase() === wanted);
}

function stringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => String(item)).filter(Boolean);
}

function stringField(value: unknown, fallback = ""): string {
  return typeof value === "string" && value.trim() ? value.trim() : fallback;
}

function booleanField(value: unknown): boolean {
  return value === true;
}
