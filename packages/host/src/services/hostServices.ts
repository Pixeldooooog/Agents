import { AgentRunService, JsonStateStore, TaskService, loadSettings, statePath, McpConnectionManager, type McpConnectionConfig } from "@kevin/core";

export type HostServices = Awaited<ReturnType<typeof createHostServices>>;

export async function createHostServices(repoRoot = process.cwd()) {
  const settings = await loadSettings(repoRoot);
  const store = new JsonStateStore(statePath(settings.repoRoot, settings.agent.statePath));
  const config = settings.mcp;
  const connections: McpConnectionConfig[] = [];
  if (config.serverCommand || config.serverUrl) {
    const common = { name: config.serverName || "default", timeoutMs: config.clientTimeout * 1000 };
    if (config.serverTransport === "stdio") connections.push({ ...common, transport: "stdio", command: config.serverCommand, args: config.serverArgs, cwd: settings.repoRoot });
    else if (config.serverTransport === "http") connections.push({ ...common, transport: "http", url: config.serverUrl, headers: config.serverHeaders });
    else throw new Error(`MCP transport not implemented: ${config.serverTransport}`);
  }
  const mcp = new McpConnectionManager(connections);
  // Connections are explicit via the authenticated reconnect endpoint; host startup never launches a configured process.
  const tasks = new TaskService(settings, store, { mcpProviders: mcp.providers });
  const runs = new AgentRunService({ settings, store, taskRunner: tasks, mcpProviders: mcp.providers });
  return {
    mcp,
    close: () => mcp.close(),
    settings,
    store,
    tasks,
    runs
  };
}
