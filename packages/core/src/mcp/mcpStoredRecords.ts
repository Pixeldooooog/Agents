import type { McpServerRecord } from "../types/mcpTypes.js";

export function normalizeMcpServerRecord(rawServer: Partial<McpServerRecord>): McpServerRecord {
  return {
    name: String(rawServer.name || "default"),
    command: String(rawServer.command || ""),
    transport: String(rawServer.transport || "stdio"),
    url: String(rawServer.url || ""),
    headers: coerceStringRecord(rawServer.headers),
    execution_mode: String(rawServer.execution_mode || "trusted_control_plane"),
    sandbox_profile: String(rawServer.sandbox_profile || ""),
    auth_required: Boolean(rawServer.auth_required),
    auth_url: String(rawServer.auth_url || ""),
    auth_status: String(rawServer.auth_status || ""),
    auth_message: String(rawServer.auth_message || ""),
    enabled: rawServer.enabled !== false,
    tenant_id: String(rawServer.tenant_id || ""),
    user_id: String(rawServer.user_id || ""),
    agent_id: String(rawServer.agent_id || ""),
    workspace_id: String(rawServer.workspace_id || ""),
    created_at: Number(rawServer.created_at || timestamp()),
    updated_at: Number(rawServer.updated_at || timestamp())
  };
}

export function mcpServerKey(server: McpServerRecord): string {
  return [server.tenant_id, server.user_id, server.agent_id, server.workspace_id, server.name].join("\0");
}

function coerceStringRecord(rawRecord: unknown): Record<string, string> {
  if (!rawRecord || typeof rawRecord !== "object" || Array.isArray(rawRecord)) return {};
  return Object.fromEntries(Object.entries(rawRecord).map(([key, rawValue]) => [key, String(rawValue)]));
}

function timestamp(): number {
  return Date.now() / 1000;
}
