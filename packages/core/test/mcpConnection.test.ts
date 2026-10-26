import { expect, test } from "bun:test";
import { connectMcpServer } from "../src/mcp/mcpConnection.js";
import { closeMcpProviders } from "../src/mcp/mcpProviderLifecycle.js";
import { mcpExternalTools } from "../src/mcp/mcpExternalTools.js";
import { collectMcpPages } from "../src/mcp/mcpPagination.js";
import { McpConnectionManager } from "../src/mcp/mcpConnectionManager.js";
import { executeBuiltinTool, modelToolDefinitions } from "../src/tools/toolRegistry.js";
import { requiresApproval } from "../src/runtime/runtimeToolPermissions.js";
import { specFromPayload } from "../src/types/agentTypes.js";
import path from "node:path";

const stdio = { name: "stdio-fixture", transport: "stdio" as const, command: process.execPath, args: [path.join(import.meta.dir, "fixtures/mcpStdioServer.ts")], timeoutMs: 2000 };

test("stdio initializes, discovers capabilities and calls validated external tools", async () => {
  const provider = await connectMcpServer(stdio);
  try {
    const [tool] = mcpExternalTools([provider]);
    expect(modelToolDefinitions([tool.name], [provider])[0].name).toBe(tool.name);
    expect(modelToolDefinitions([], [provider]).some(item => item.name === tool.name)).toBe(false);
    expect(requiresApproval(specFromPayload({ permission_profile: "auto" }), tool.name)).toBe(true);
    const context = { mcpProviders: [provider] };
    expect((await executeBuiltinTool(process.cwd(), tool.name, { text: "hello" }, context)).result.content).toContain("hello");
    expect((await executeBuiltinTool(process.cwd(), tool.name, { text: 42 }, context)).result.is_error).toBe(true);
    expect((await executeBuiltinTool(process.cwd(), tool.name, { text: "fail" }, context)).result.is_error).toBe(true);
    expect(await provider.listResources!()).toHaveLength(1);
    expect(JSON.stringify(await provider.readResource!("fixture://intro"))).toContain("resource body");
    expect(await provider.listPrompts!()).toHaveLength(1);
    expect(JSON.stringify(await provider.getPrompt!("greet", {}))).toContain("hello");
  } finally { await closeMcpProviders([provider]); }
  expect(mcpExternalTools([provider])).toEqual([]);
});

test("explicit reconnect replaces a revoked provider without replaying actions", async () => {
  const manager = new McpConnectionManager([stdio]);
  try {
    await manager.reconnect(stdio.name);
    const first = manager.providers[0];
    const name = mcpExternalTools([first])[0].name;
    await manager.reconnect(stdio.name);
    expect(manager.providers[0]).not.toBe(first);
    expect(mcpExternalTools([first])).toEqual([]);
    expect(manager.status()[0].tools[0].name).toBe(name);
  } finally { await manager.close(); }
  await expect(manager.reconnect(stdio.name)).rejects.toThrow("closed");
});

test("discovery rejects repeated cursors, excessive items and duplicate tool identities", async () => {
  await expect(collectMcpPages(async () => ({ items: [], nextCursor: "same" }))).rejects.toThrow("repeated");
  await expect(collectMcpPages(async () => ({ items: new Array(1025) }))).rejects.toThrow("1024");
  expect(() => mcpExternalTools([{ server: { name: "bad" }, tools: [{ name: "x", inputSchema: { type: "array" } }] }])).toThrow("object schema");
  const raw = { name: "x", inputSchema: { type: "object" } };
  expect(() => mcpExternalTools([{ server: { name: "bad" }, tools: [raw, raw] }])).toThrow("duplicate");
  const first = mcpExternalTools([{ server: { name: "same" }, tools: [raw] }])[0];
  const second = mcpExternalTools([{ server: { name: "same" }, tools: [{ ...raw, description: "changed" }] }])[0];
  expect(first.name).not.toBe(second.name);
});

test("HTTP initializes a session, paginates, forwards cancellation and terminates", async () => {
  let initialized = false;
  let deleted = false;
  let cancelled = false;
  let called!: () => void;
  const ready = new Promise<void>(resolve => { called = resolve; });
  const server = Bun.serve({ hostname: "127.0.0.1", port: 0, async fetch(request) {
    if (request.method === "GET") return new Response(null, { status: 405 });
    if (request.method === "DELETE") { deleted = true; return new Response(null, { status: 204 }); }
    const message = await request.json();
    if (message.method === "notifications/initialized") { initialized = true; return new Response(null, { status: 202 }); }
    if (message.method === "notifications/cancelled") { cancelled = true; return new Response(null, { status: 202 }); }
    const headers = { "mcp-session-id": "fixture-session" };
    let result: unknown;
    if (message.method === "initialize") result = { protocolVersion: "2025-03-26", capabilities: { tools: {} }, serverInfo: { name: "http-fixture", version: "1" } };
    else if (message.method === "tools/list") {
      expect(request.headers.get("mcp-session-id")).toBe("fixture-session");
      result = message.params?.cursor ? { tools: [{ name: "slow", inputSchema: { type: "object" } }] } : { tools: [], nextCursor: "next" };
    } else if (message.method === "tools/call") {
      called();
      return new Response("", { status: 202 });
    } else return new Response(null, { status: 400 });
    return Response.json({ jsonrpc: "2.0", id: message.id, result }, { headers });
  } });
  const provider = await connectMcpServer({ name: "http", transport: "http", url: `http://127.0.0.1:${server.port}/mcp`, timeoutMs: 1000 });
  try {
    expect(initialized).toBe(true);
    expect(mcpExternalTools([provider])).toHaveLength(1);
    const controller = new AbortController();
    const result = provider.callTool!("slow", {}, controller.signal).then(() => undefined, (error: unknown) => error);
    await ready;
    controller.abort();
    expect(await result).toBeInstanceOf(Error);
    // Drain the actual cancellation notification rather than asserting only a local AbortSignal.
    for (let i = 0; i < 50 && !cancelled; i++) await new Promise(resolve => setTimeout(resolve, 10));
    expect(cancelled).toBe(true);
  } finally { await closeMcpProviders([provider]); await server.stop(true); }
  expect(deleted).toBe(true);
});
