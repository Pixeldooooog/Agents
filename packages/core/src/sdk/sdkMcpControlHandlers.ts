import type { SdkControlRequestMessage } from "./sdkControlTypes.js";
import {
  configuredMcpServerStatus,
  mcpControlScope,
  mcpRecordFromControlConfig,
  mcpRecordStatus,
  mcpStatus,
  mergeMcpServerStatuses,
  sdkMcpServerRecord,
  sdkMcpServerStatus
} from "./sdkMcpControlRecords.js";
import type { SdkControlRequestHandlerContext } from "./sdkProtocolRunner.js";

export async function mcpStatusControlResponsePayload(
  context: SdkControlRequestHandlerContext
): Promise<Record<string, unknown>> {
  const settingsServer = configuredMcpServerStatus(context.client.settings.mcp);
  const records = await context.client.listMcpServers(mcpControlScope(context));
  const servers = mergeMcpServerStatuses(
    context.client.listSdkMcpServerNames().map(sdkMcpServerStatus),
    records.map(mcpRecordStatus)
  );
  const mcpServers = mergeMcpServerStatuses(settingsServer ? [settingsServer] : [], servers)
    .map((server) => ({ name: server.name, status: server.status }));
  return {
    configured: settingsServer,
    servers,
    mcpServers,
    active: [...(settingsServer ? [settingsServer] : []), ...servers]
      .filter((server) => server.enabled)
      .map((server) => ({ name: server.name, status: server.status }))
  };
}

export async function mcpSetServersControlResponsePayload(
  message: SdkControlRequestMessage,
  context: SdkControlRequestHandlerContext
): Promise<Record<string, unknown>> {
  const request = message.request;
  if (request.subtype !== "mcp_set_servers") return {};

  const scope = mcpControlScope(context);
  const existingRecords = await context.client.listMcpServers(scope);
  const existingByName = new Map(existingRecords.map((record) => [record.name, record]));
  const wantedServers = request.servers || {};
  const wantedNames = new Set(Object.keys(wantedServers).map((name) => name.trim()).filter(Boolean));

  const removed: string[] = [];
  for (const record of existingRecords) {
    if (wantedNames.has(record.name)) continue;
    if (await context.client.deleteMcpServer(record.name, scope)) removed.push(record.name);
  }

  const added: string[] = [];
  const updated: string[] = [];
  const errors: Record<string, string> = {};
  for (const [rawName, config] of Object.entries(wantedServers)) {
    const name = rawName.trim();
    try {
      if (!name) throw new Error("MCP server name is required");
      const existing = existingByName.get(name);
      const saved = await context.client.saveMcpServer(mcpRecordFromControlConfig(name, config, scope, existing));
      if (existing) updated.push(saved.name);
      else added.push(saved.name);
    } catch (error) {
      errors[name || rawName] = errorMessage(error);
    }
  }

  return {
    added: added.sort(),
    updated: updated.sort(),
    removed: removed.sort(),
    errors,
    mcp: await mcpStatusControlResponsePayload(context)
  };
}

export async function mcpToggleControlResponsePayload(
  message: SdkControlRequestMessage,
  context: SdkControlRequestHandlerContext
): Promise<Record<string, unknown>> {
  const request = message.request;
  if (request.subtype !== "mcp_toggle") return {};

  const scope = mcpControlScope(context);
  const target = request.serverName.trim();
  const record = (await context.client.listMcpServers(scope)).find((item) => item.name === target);
  if (!record && !context.client.hasSdkMcpServer(target)) throw new Error(`mcp server not found: ${target}`);

  const saved = await context.client.saveMcpServer(record
    ? { ...record, enabled: request.enabled }
    : sdkMcpServerRecord(target, request.enabled, scope)
  );
  return {
    serverName: saved.name,
    enabled: saved.enabled,
    status: mcpStatus(saved),
    mcp: await mcpStatusControlResponsePayload(context)
  };
}

export async function mcpMessageControlResponsePayload(
  message: SdkControlRequestMessage,
  context: SdkControlRequestHandlerContext
): Promise<Record<string, unknown>> {
  const request = message.request;
  if (request.subtype !== "mcp_message") return {};

  const serverName = request.serverName.trim();
  if (!context.client.hasSdkMcpServer(serverName)) throw new Error(`SDK MCP server not registered: ${serverName}`);
  if (!await isSdkMcpServerEnabled(serverName, context)) throw new Error(`SDK MCP server is disabled: ${serverName}`);
  const mcpResponse = await context.client.callSdkMcpServer(serverName, request.message);
  return {
    serverName,
    mcpResponse,
    mcp_response: mcpResponse
  };
}

export async function mcpReconnectControlResponsePayload(
  message: SdkControlRequestMessage,
  context: SdkControlRequestHandlerContext
): Promise<Record<string, unknown>> {
  const request = message.request;
  if (request.subtype !== "mcp_reconnect") return {};

  const serverName = request.serverName.trim();
  if (!serverName) throw new Error("MCP server name is required");
  if (context.client.hasSdkMcpServer(serverName)) {
    if (!await isSdkMcpServerEnabled(serverName, context)) throw new Error(`SDK MCP server is disabled: ${serverName}`);
    return { serverName, status: "connected", reconnected: true };
  }

  const record = (await context.client.listMcpServers(mcpControlScope(context))).find((item) => item.name === serverName);
  if (!record) throw new Error(`mcp server not found: ${serverName}`);
  return {
    serverName,
    status: mcpStatus(record),
    reconnected: false,
    reason: "no active SDK turn is attached to this control handler"
  };
}

async function isSdkMcpServerEnabled(name: string, context: SdkControlRequestHandlerContext): Promise<boolean> {
  const record = (await context.client.listMcpServers(mcpControlScope(context))).find((item) => item.name === name);
  return record?.enabled !== false;
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
