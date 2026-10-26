import { closeMcpProviders, mcpTimeoutMilliseconds } from "./mcpProviderLifecycle.js";
import type { JsonObject } from "../types/jsonTypes.js";
import type { McpServerRecord } from "../types/mcpTypes.js";
import type { ToolExecutionContext } from "../tools/toolContracts.js";
import { stringArg } from "../tools/toolInputs.js";
import {
  clearMcpSettings,
  configuredMcpServerPayload,
  deleteMcpRecord,
  findMcpRecord,
  hydrateMcpSettings,
  listMcpRecords,
  mcpProviderPayload,
  mcpProviders,
  mcpServerRecordFromArgs,
  removeMcpProviders,
  saveMcpRecord
} from "./mcpRecords.js";

export async function readMcpServers(context: ToolExecutionContext): Promise<Record<string, unknown>> {
  await hydrateMcpSettings(context);
  const providers = mcpProviders(context);
  return {
    configured: configuredMcpServerPayload(context.settings?.mcp),
    servers: (await listMcpRecords(context)).map(publicMcpRecord),
    providers: providers.map(mcpProviderPayload),
    count: providers.length
  };
}

export async function configureMcpServer(context: ToolExecutionContext, args: JsonObject): Promise<Record<string, unknown>> {
  await saveMcpRecord(context, mcpServerRecordFromArgs(context, args));
  return readMcpServers(context);
}

export async function enableMcpServer(context: ToolExecutionContext, args: JsonObject): Promise<Record<string, unknown>> {
  const target = targetServerName(context, args);
  const record = await findMcpRecord(context, target);
  if (!record) throw new Error(`mcp server not found: ${target}`);
  const enabled = await saveMcpRecord(context, { ...record, enabled: true });
  return { enabled: enabled.name, configured: (await readMcpServers(context)).configured };
}

export async function disableMcpServer(context: ToolExecutionContext, args: JsonObject): Promise<Record<string, unknown>> {
  const timeoutMs = mcpTimeoutMilliseconds(context);
  const target = targetServerName(context, args);
  const record = await findMcpRecord(context, target);
  if (record) await saveMcpRecord(context, { ...record, enabled: false });
  const removedProviders = removeMcpProviders(context, target);
  if (context.settings?.mcp.serverName === target) clearMcpSettings(context);
  await closeMcpProviders(removedProviders, timeoutMs);
  return { disabled: target, removed_providers: removedProviders.length, configured: (await readMcpServers(context)).configured };
}

export async function removeMcpServer(context: ToolExecutionContext, args: JsonObject): Promise<Record<string, unknown>> {
  const timeoutMs = mcpTimeoutMilliseconds(context);
  const target = targetServerName(context, args);
  await deleteMcpRecord(context, target);
  const removedProviders = removeMcpProviders(context, target);
  if (context.settings?.mcp.serverName === target) clearMcpSettings(context);
  await closeMcpProviders(removedProviders, timeoutMs);
  return { removed: target, removed_providers: removedProviders.length, configured: (await readMcpServers(context)).configured };
}

export async function clearMcpServers(context: ToolExecutionContext): Promise<Record<string, unknown>> {
  const timeoutMs = mcpTimeoutMilliseconds(context);
  const records = await listMcpRecords(context);
  for (const record of records) await deleteMcpRecord(context, record.name);
  const providers = removeMcpProviders(context);
  clearMcpSettings(context);
  await closeMcpProviders(providers, timeoutMs);
  return { cleared: true, removed_providers: providers.length, configured: (await readMcpServers(context)).configured };
}

function targetServerName(context: ToolExecutionContext, args: JsonObject): string {
  return stringArg(args.name, context.settings?.mcp.serverName || "default");
}

function publicMcpRecord(record: McpServerRecord): Record<string, unknown> {
  return {
    name: record.name,
    command: record.command,
    transport: record.transport,
    url: record.url,
    headers: record.headers,
    execution_mode: record.execution_mode,
    sandbox_profile: record.sandbox_profile,
    auth_required: record.auth_required,
    auth_url: record.auth_url,
    auth_status: record.auth_status,
    auth_message: record.auth_message,
    enabled: record.enabled,
    created_at: record.created_at,
    updated_at: record.updated_at
  };
}
