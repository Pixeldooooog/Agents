import type { McpProvider, ToolExecutionContext } from "../tools/toolContracts.js";
import { mcpProviders } from "./mcpRecords.js";
import { clampResultLimit, normalizeList, objectRecord, requiredText } from "./mcpProviderPayloads.js";

export async function listMcpResources(context: ToolExecutionContext, server: string, uriPrefix: string, maxResults: number) {
  const resources: Record<string, unknown>[] = [];
  const errors: Record<string, string>[] = [];
  for (const provider of mcpProviders(context, server)) {
    try {
      for (const resource of await callListResources(provider)) {
        const payload = resourcePayload(provider, resource);
        if (uriPrefix && !String(payload.uri || "").startsWith(uriPrefix)) continue;
        resources.push(payload);
      }
    } catch (error) {
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
      return { server: provider.server.name, uri: targetUri, content: await callReadResource(provider, targetUri) };
    } catch (error) {
      errors.push({ server: provider.server.name, error: error instanceof Error ? error.message : String(error) });
      if (server) break;
    }
  }
  if (!providers.length) throw new Error("no MCP server resources available");
  throw new Error(`failed to read MCP resource ${targetUri}: ${JSON.stringify(errors)}`);
}

async function callListResources(provider: McpProvider): Promise<unknown[]> {
  const listResources = provider.listResources || provider.list_resources;
  if (!listResources) return [];
  return normalizeList(await listResources.call(provider));
}

async function callReadResource(provider: McpProvider, uri: string): Promise<unknown> {
  const readResource = provider.readResource || provider.read_resource;
  if (!readResource) throw new Error("provider does not support resource reads");
  return readResource.call(provider, uri);
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
