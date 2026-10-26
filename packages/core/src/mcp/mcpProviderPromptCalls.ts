import { callMcpProvider, McpCallInterruptedError } from "./mcpProviderLifecycle.js";
import type { McpProvider } from "../tools/toolContracts.js";
import type { McpToolContext } from "./mcpRecords.js";
import { mcpProviders } from "./mcpRecords.js";
import { clampResultLimit, normalizeList, objectRecord, requiredText } from "./mcpProviderPayloads.js";

export async function listMcpPrompts(context: McpToolContext, server: string, query: string, maxResults: number) {
  const prompts: Record<string, unknown>[] = [];
  const errors: Record<string, string>[] = [];
  const needle = query.trim().toLowerCase();
  for (const provider of mcpProviders(context, server)) {
    try {
      for (const prompt of await callListPrompts(context, provider)) {
        const payload = promptPayload(provider, prompt);
        if (needle && !promptHaystack(payload).includes(needle)) continue;
        prompts.push(payload);
      }
    } catch (error) {
      if (error instanceof McpCallInterruptedError) throw error;
      errors.push({ server: provider.server.name, error: error instanceof Error ? error.message : String(error) });
    }
  }
  const limit = clampResultLimit(maxResults, 50, 100);
  return { prompts: prompts.slice(0, limit), count: Math.min(prompts.length, limit), total: prompts.length, errors };
}

export async function getMcpPrompt(context: McpToolContext, name: string, server: string, args: Record<string, unknown>) {
  const promptName = requiredText(name, "name");
  const errors: Record<string, string>[] = [];
  const providers = mcpProviders(context, server);
  for (const provider of providers) {
    try {
      return { server: provider.server.name, name: promptName, content: await callGetPrompt(context, provider, promptName, args) };
    } catch (error) {
      if (error instanceof McpCallInterruptedError) throw error;
      errors.push({ server: provider.server.name, error: error instanceof Error ? error.message : String(error) });
      if (server) break;
    }
  }
  if (!providers.length) throw new Error("no MCP prompt servers available");
  throw new Error(`failed to get MCP prompt ${promptName}: ${JSON.stringify(errors)}`);
}

async function callListPrompts(context: McpToolContext, provider: McpProvider): Promise<unknown[]> {
  const listPrompts = provider.listPrompts || provider.list_prompts;
  if (!listPrompts) return [];
  return normalizeList(await callMcpProvider(context, provider, signal => listPrompts.call(provider, signal)));
}

async function callGetPrompt(context: McpToolContext, provider: McpProvider, name: string, args: Record<string, unknown>): Promise<unknown> {
  const getPrompt = provider.getPrompt || provider.get_prompt;
  if (!getPrompt) throw new Error("provider does not support prompt rendering");
  return callMcpProvider(context, provider, signal => getPrompt.call(provider, name, args, signal));
}

function promptPayload(provider: McpProvider, prompt: unknown) {
  const record = objectRecord(prompt);
  return {
    server: provider.server.name,
    name: String(record.name || ""),
    description: String(record.description || ""),
    arguments: normalizeList(record.arguments).map((argument) => {
      const item = objectRecord(argument);
      return {
        name: String(item.name || ""),
        description: String(item.description || ""),
        required: Boolean(item.required)
      };
    })
  };
}

function promptHaystack(payload: Record<string, unknown>): string {
  const args = Array.isArray(payload.arguments) ? payload.arguments : [];
  return [
    payload.name,
    payload.description,
    args.map((argument) => objectRecord(argument).name).join(" ")
  ].join(" ").toLowerCase();
}
