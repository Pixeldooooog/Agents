import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";
import type { McpProvider } from "../tools/toolContracts.js";
import { closeMcpProviders } from "./mcpProviderLifecycle.js";
import { mcpExternalTools } from "./mcpExternalTools.js";
import { collectMcpPages } from "./mcpPagination.js";
import { boundedMcpFetch } from "./mcpHttpTransport.js";

/** Host-owned configuration. Never populate this from model-produced tool arguments. */
export type McpConnectionConfig = {
  name: string;
  timeoutMs?: number;
} & ({ transport: "stdio"; command: string; args?: string[]; cwd?: string; env?: Record<string, string> }
  | { transport: "http"; url: string; headers?: Record<string, string> });

export async function connectMcpServer(config: McpConnectionConfig, signal?: AbortSignal): Promise<McpProvider> {
  const timeout = config.timeoutMs ?? 30_000;
  if (!config.name.trim() || !Number.isFinite(timeout) || timeout <= 0 || timeout > 2147483647) throw new Error("invalid MCP connection configuration");
  signal?.throwIfAborted();
  if (config.transport === "stdio" && (!config.command.trim() || config.command.includes("\0") || config.args?.some(arg => typeof arg !== "string" || arg.includes("\0")))) throw new Error("invalid MCP executable or arguments");
  if (config.transport !== "stdio" && config.transport !== "http") throw new Error("unsupported MCP transport");
  const transport = config.transport === "stdio"
    ? new StdioClientTransport({ command: config.command, args: config.args, cwd: config.cwd, env: config.env, stderr: "ignore", maxBufferSize: 8 * 1024 * 1024 })
    : new StreamableHTTPClientTransport(mcpUrl(config.url), {
      requestInit: { headers: config.headers, redirect: "error" }, fetch: boundedMcpFetch,
      reconnectionOptions: { maxRetries: 0, initialReconnectionDelay: 1000, maxReconnectionDelay: 1000, reconnectionDelayGrowFactor: 1 }
    });
  const connectionDeadline = new AbortController();
  const timer = setTimeout(() => connectionDeadline.abort(new Error("MCP connection timed out")), timeout);
  const connectionSignal = signal ? AbortSignal.any([signal, connectionDeadline.signal]) : connectionDeadline.signal;
  const client = new Client({ name: "kevin", version: "0.1.0" }, { capabilities: {} });
  const requestOptions = (requestSignal?: AbortSignal) => ({ signal: requestSignal, timeout, maxTotalTimeout: timeout });
  const provider: McpProvider = {
    server: { name: config.name, transport: config.transport },
    tools: [],
    callTool: (name, args, requestSignal) => client.callTool({ name, arguments: args }, undefined, requestOptions(requestSignal)),
    close: async () => {
      const forceClose = setTimeout(() => { void client.close().catch(() => {}); }, timeout);
      try {
        if (transport instanceof StreamableHTTPClientTransport) await transport.terminateSession();
      } finally { clearTimeout(forceClose); await client.close(); }
    }
  };
  client.onclose = () => { void closeMcpProviders([provider], timeout).catch(() => {}); };
  try {
    await client.connect(transport, requestOptions(connectionSignal));
    const capabilities = client.getServerCapabilities();
    if (capabilities?.tools) provider.tools = await collectMcpPages(async cursor => {
      const page = await client.listTools({ cursor }, requestOptions(connectionSignal));
      return { items: page.tools, nextCursor: page.nextCursor };
    });
    if (capabilities?.resources) {
      provider.listResources = requestSignal => collectMcpPages(async cursor => {
        const page = await client.listResources({ cursor }, requestOptions(requestSignal));
        return { items: page.resources, nextCursor: page.nextCursor };
      });
      provider.readResource = (uri, requestSignal) => client.readResource({ uri }, requestOptions(requestSignal));
    }
    if (capabilities?.prompts) {
      provider.listPrompts = requestSignal => collectMcpPages(async cursor => {
        const page = await client.listPrompts({ cursor }, requestOptions(requestSignal));
        return { items: page.prompts, nextCursor: page.nextCursor };
      });
      provider.getPrompt = (name, args, requestSignal) => {
        const entries = Object.entries(args);
        if (entries.some(([, value]) => typeof value !== "string")) throw new Error("MCP prompt arguments must be strings");
        const strings = Object.fromEntries(entries.map(([key, value]) => [key, String(value)]));
        return client.getPrompt({ name, arguments: strings }, requestOptions(requestSignal));
      };
    }
    // Reject invalid schemas and duplicate names before exposing any external tool.
    mcpExternalTools([provider]);
    connectionSignal.throwIfAborted();
    return provider;
  } catch (error) {
    await closeMcpProviders([provider], timeout).catch(() => {});
    throw error;
  } finally { clearTimeout(timer); }
}

function mcpUrl(value: string): URL {
  const url = new URL(value);
  if (!["http:", "https:"].includes(url.protocol) || url.username || url.password || url.hash) throw new Error("MCP requires an HTTP(S) URL without credentials or fragment");
  return url;
}
