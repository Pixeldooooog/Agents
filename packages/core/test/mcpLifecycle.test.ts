import { expect, test } from "bun:test";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { executeBuiltinTool, loadSettings, specFromPayload } from "../src/index.js";
import type { McpProvider } from "../src/tools/toolContracts.js";
import type { McpToolContext } from "../src/mcp/mcpRecords.js";
import { callMcpProvider, closeMcpProviders, isMcpProviderActive } from "../src/mcp/mcpProviderLifecycle.js";
import { readMcpResource, listMcpResources } from "../src/mcp/mcpProviderResourceCalls.js";
import { getMcpPrompt, listMcpPrompts } from "../src/mcp/mcpProviderPromptCalls.js";
import { executeRuntimeToolCall } from "../src/runtime/runtimeToolExecution.js";
import { AgentRuntime } from "../src/runtime/agentRuntime.js";

async function fixture(run: (context: McpToolContext) => Promise<void>) {
  const root = await mkdtemp(path.join(tmpdir(), "kevin-mcp-lifecycle-"));
  try { await run({ repoRoot: root, settings: await loadSettings(root) }); }
  finally { await rm(root, { recursive: true, force: true }); }
}

for (const action of ["disable", "remove", "clear"]) {
  test(`${action} detaches the shared provider array and closes once`, () => fixture(async context => {
    let closes = 0;
    let reads = 0;
    const provider: McpProvider = { server: { name: "docs" }, close: async () => { closes++; }, readResource: async () => { reads++; return "secret"; } };
    const providers = [provider];
    const staleContext = { ...context, mcpProviders: [...providers] };
    context.mcpProviders = providers;
    const result = await executeBuiltinTool(context.repoRoot, `mcp.${action}`, action === "clear" ? {} : { name: "docs" }, context);
    expect(result.result.is_error).toBe(false);
    expect(providers).toHaveLength(0);
    expect(closes).toBe(1);
    await expect(readMcpResource(staleContext, "docs://secret", "docs")).rejects.toThrow("no MCP");
    await closeMcpProviders([provider]);
    expect(closes).toBe(1);
    expect(reads).toBe(0);
  }));
}

test("close failure does not keep providers reachable or skip other closes", () => fixture(async context => {
  let healthyCloses = 0;
  const bad: McpProvider = { server: { name: "bad" }, close: async () => { throw new Error("close failed"); } };
  const healthy: McpProvider = { server: { name: "healthy" }, close: async () => { healthyCloses++; } };
  const providers = [bad, healthy];
  const result = await executeBuiltinTool(context.repoRoot, "mcp.clear", {}, { ...context, mcpProviders: providers });
  expect(result.result.is_error).toBe(true);
  expect(providers).toHaveLength(0);
  expect(healthyCloses).toBe(1);
  expect(isMcpProviderActive(bad)).toBe(false);
  expect(isMcpProviderActive(healthy)).toBe(false);
}));

test("revocation interrupts an in-flight provider even when it ignores cancellation", () => fixture(async context => {
  let started!: () => void;
  const ready = new Promise<void>(resolve => { started = resolve; });
  let receivedSignal: AbortSignal | undefined;
  const provider: McpProvider = { server: { name: "docs" }, readResource: async (_uri, signal) => {
    receivedSignal = signal;
    started();
    return new Promise(() => {});
  } };
  const reading = readMcpResource({ ...context, mcpProviders: [provider] }, "docs://intro", "docs");
  const outcome = reading.then(() => undefined, (error: unknown) => error);
  await ready;
  await closeMcpProviders([provider]);
  expect(await outcome).toMatchObject({ code: "revoked" });
  expect(receivedSignal?.aborted).toBe(true);
}));

test("all resource and prompt calls receive cancellation and do not fall back", () => fixture(async context => {
  const operations = [
    (ctx: McpToolContext) => listMcpResources(ctx, "", "", 50),
    (ctx: McpToolContext) => readMcpResource(ctx, "docs://intro", ""),
    (ctx: McpToolContext) => listMcpPrompts(ctx, "", "", 50),
    (ctx: McpToolContext) => getMcpPrompt(ctx, "release", "", {})
  ];
  for (const operation of operations) {
    const controller = new AbortController();
    let fallbackCalls = 0;
    const cancel = async (signal?: AbortSignal) => { expect(signal).toBeDefined(); controller.abort(); return []; };
    const provider: McpProvider = {
      server: { name: "first" }, listResources: cancel, listPrompts: cancel,
      readResource: async (_uri, signal) => cancel(signal), getPrompt: async (_name, _args, signal) => cancel(signal)
    };
    const fallback = async () => { fallbackCalls++; return []; };
    const second: McpProvider = { server: { name: "second" }, listResources: fallback, listPrompts: fallback, readResource: fallback, getPrompt: fallback };
    await expect(operation({ ...context, signal: controller.signal, mcpProviders: [provider, second] })).rejects.toThrow("cancelled");
    expect(fallbackCalls).toBe(0);
  }
}));

test("timeout bounds calls and shutdown; pre-cancellation avoids provider I/O", () => fixture(async context => {
  context.settings!.mcp.clientTimeout = 0.01;
  let calls = 0;
  const provider: McpProvider = { server: { name: "slow" }, close: async () => new Promise(() => {}) };
  await expect(callMcpProvider({ ...context, signal: AbortSignal.abort() }, provider, async () => { calls++; })).rejects.toThrow("cancelled");
  expect(calls).toBe(0);
  await expect(callMcpProvider(context, provider, async () => new Promise(() => {}))).rejects.toThrow("timed out");
  await expect(closeMcpProviders([provider], 10)).rejects.toThrow("failed to close");
  expect(isMcpProviderActive(provider)).toBe(false);
}));

test("runtime deny rules stop MCP resource calls before provider execution", () => fixture(async context => {
  let calls = 0;
  const provider: McpProvider = { server: { name: "docs" }, readResource: async () => { calls++; return "secret"; } };
  const spec = specFromPayload({ message: "read", enabled_tools: ["mcp.read_resource"], denied_tools: ["mcp.read_resource"], permission_profile: "auto" });
  const execution = await executeRuntimeToolCall({
    options: { settings: context.settings!, mcpProviders: [provider] }, spec, runId: "run",
    toolCall: { id: "read", name: "mcp__read_resource", arguments: { server: "docs", uri: "docs://intro" } },
    messages: [], toolResults: [], runtimeEvents: []
  });
  expect(execution.result.is_error).toBe(true);
  expect(calls).toBe(0);
}));

for (const decision of ["approve", "deny", "revoke"] as const) {
  test(`MCP resource approval ${decision} uses the runtime gate`, () => fixture(async context => {
    let requests = 0;
    let reads = 0;
    const provider: McpProvider = { server: { name: "docs" }, readResource: async () => { reads++; return "resource content"; } };
    const providers = [provider];
    const server = Bun.serve({ hostname: "127.0.0.1", port: 0, fetch() {
      requests++;
      return Response.json({ choices: [{ message: requests === 1 ? {
        content: "", tool_calls: [{ id: "resource", type: "function", function: {
          name: "mcp__read_resource", arguments: JSON.stringify({ server: "docs", uri: "docs://intro" })
        } }]
      } : { content: "finished" } }] });
    } });
    try {
      const runtime = new AgentRuntime({ settings: context.settings!, mcpProviders: providers });
      const spec = specFromPayload({
        protocol: "openai-chat", model: "fixture", api_key: "fixture", base_url: `http://127.0.0.1:${server.port}/v1`,
        enabled_tools: ["mcp.read_resource"], approval_required_tools: ["mcp.read_resource"], permission_profile: "auto"
      });
      const first = await runtime.run(spec, "read the resource", "run");
      expect(first.pending_approval).toBeDefined();
      expect(reads).toBe(0);
      if (decision === "revoke") await executeBuiltinTool(context.repoRoot, "mcp.disable", { name: "docs" }, { ...context, mcpProviders: providers });
      const resumed = await runtime.resumeWithApproval(spec, first.pending_approval!, decision !== "deny", "run");
      expect(reads).toBe(decision === "approve" ? 1 : 0);
      expect(resumed.tool_results[0].is_error).toBe(decision !== "approve");
      expect(resumed.tool_results[0].tool_call_id).toBe("resource");
    } finally { await server.stop(true); }
  }));
}
