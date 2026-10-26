import type { McpProvider } from "../tools/toolContracts.js";
import { connectMcpServer, type McpConnectionConfig } from "./mcpConnection.js";
import { closeMcpProviders, isMcpProviderActive } from "./mcpProviderLifecycle.js";
import { mcpExternalTools } from "./mcpExternalTools.js";

/** One host owns connection replacement. No automatic replay of failed external actions. */
export class McpConnectionManager {
  readonly providers: McpProvider[] = [];
  private pending: Promise<void> = Promise.resolve();
  private closed = false;
  private readonly shutdown = new AbortController();
  private readonly configs: McpConnectionConfig[];

  constructor(configs: McpConnectionConfig[]) {
    this.configs = structuredClone(configs);
    if (new Set(configs.map(config => config.name)).size !== configs.length) throw new Error("duplicate MCP connection names");
  }

  status() {
    return this.configs.map(config => ({
      name: config.name, transport: config.transport,
      connected: this.providers.some(provider => provider.server.name === config.name && isMcpProviderActive(provider)),
      tools: mcpExternalTools(this.providers.filter(provider => provider.server.name === config.name)).map(({ name, description }) => ({ name, description }))
    }));
  }

  reconnect(name: string, signal?: AbortSignal): Promise<void> {
    const config = this.configs.find(item => item.name === name);
    if (!config) return Promise.reject(new Error("unknown host-configured MCP server"));
    const operation = this.pending.then(async () => {
      if (this.closed) throw new Error("MCP manager closed");
      const combined = signal ? AbortSignal.any([signal, this.shutdown.signal]) : this.shutdown.signal;
      combined.throwIfAborted();
      const removed = this.providers.filter(provider => provider.server.name === name);
      this.providers.splice(0, this.providers.length, ...this.providers.filter(provider => provider.server.name !== name));
      await closeMcpProviders(removed, config.timeoutMs);
      const provider = await connectMcpServer(config, combined);
      if (this.closed || combined.aborted) { await closeMcpProviders([provider], config.timeoutMs); combined.throwIfAborted(); throw new Error("MCP manager closed"); }
      this.providers.push(provider);
    });
    this.pending = operation.catch(() => {});
    return operation;
  }

  async close(): Promise<void> {
    this.closed = true;
    this.shutdown.abort();
    await this.pending;
    const providers = this.providers.splice(0);
    await closeMcpProviders(providers);
  }
}
