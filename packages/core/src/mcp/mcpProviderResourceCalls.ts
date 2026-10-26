import { callMcpProvider, McpCallInterruptedError } from "./mcpProviderLifecycle.js";
import type { McpProvider, ToolExecutionContext } from "../tools/toolContracts.js";
import { mcpProviders } from "./mcpRecords.js";
import { clampResultLimit, normalizeList, objectRecord, requiredText } from "./mcpProviderPayloads.js";

export async function listMcpResources(context: ToolExecutionContext, server: string, uriPrefix: string, maxResults: number) {
  const resources: Record<string, unknown>[] = [];
  const errors: Record<string, string>[] = [];
  for (const provider of mcpProviders(context, server)) {
    try {
      for (const resource of await callListResources(context, provider)) {
        const payload = resourcePayload(provider, resource);
        if (uriPrefix && !String(payload.uri || "").startsWith(uriPrefix)) continue;
        resources.push(payload);
      }
    } catch (error) {
      if (error instanceof McpCallInterruptedError) throw error;
      errors.push({ server: provider.server.name, error: error instanceof Error ? error.message : String(error) });
    }
  }
  const limit = clampResultLimit(maxResults, 50, 100);
  return { resources: resources.slice(0, limit), count: Math.min(resources.length, limit), total: resources.length, errors };
}

export async function readMcpResource(context: ToolExecutionContext, uri: string, server: string) {
  const targetUri = requiredText(uri, "uri");
  const errors: Record<string, string>[] = [];
  const providers = mcpProviders(context, server);
  for (const provider of providers) {
    try {
      return { server: provider.server.name, uri: targetUri, content: await callReadResource(context, provider, targetUri) };
    } catch (error) {
      if (error instanceof McpCallInterruptedError) throw error;
      errors.push({ server: provider.server.name, error: error instanceof Error ? error.message : String(error) });
      if (server) break;
    }
  }
  if (!providers.length) throw new Error("no MCP server resources available");
  throw new Error(`failed to read MCP resource ${targetUri}: ${JSON.stringify(errors)}`);
}

async function callListResources(context: ToolExecutionContext, provider: McpProvider): Promise<unknown[]> {
  const listResources = provider.listResources || provider.list_resources;
  if (!listResources) return [];
  return normalizeList(await callMcpProvider(context, provider, signal => listResources.call(provider, signal)));
}

async function callReadResource(context: ToolExecutionContext, provider: McpProvider, uri: string): Promise<unknown> {
  const readResource = provider.readResource || provider.read_resource;
  if (!readResource) throw new Error("provider does not support resource reads");
  return callMcpProvider(context, provider, signal => readResource.call(provider, uri, signal));
}

function resourcePayload(provider: McpProvider, resource: unknown) {
  const record = objectRecord(resource);
  return {
    server: provider.server.name,
    uri: String(record.uri || ""),
    name: String(record.name || ""),
    description: String(record.description || ""),
    mimeType: String(record.mimeType || record.mime_type || "")
  };
}
