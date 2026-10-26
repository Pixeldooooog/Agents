import { expect, test } from "bun:test";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { executeBuiltinTool } from "../src/tools/toolRegistry.js";
import { boundedToolContent, MAX_TOOL_OUTPUT_BYTES } from "../src/tools/toolOutput.js";
import { MAX_TOOL_INPUT_BYTES } from "../src/tools/toolValidation.js";
import { localExecutor } from "../src/execution/localExecutor.js";
import type { ExecutionPolicy } from "../src/ports/commandExecutor.js";
import { loadSettings } from "../src/config/settings.js";
import { specFromPayload } from "../src/types/agentTypes.js";
import { profileDefaults } from "../src/models/modelProfiles.js";
import { executeRuntimeToolCall, resolvePendingApproval } from "../src/runtime/runtimeToolExecution.js";
import { AgentRuntime } from "../src/runtime/agentRuntime.js";

const isolated: ExecutionPolicy = { mode: "isolated", filesystem: { readPaths: [], writePaths: [] }, network: { mode: "deny", hosts: [] }, environment: { allowedNames: [] } };

test("invalid or oversized file writes are rejected before mutation", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "kevin-tool-validation-"));
  try {
    for (const content of [false, { nested: "not text" }, "x".repeat(MAX_TOOL_INPUT_BYTES)]) {
      const result = await executeBuiltinTool(root, "filesystem.write", { path: "blocked.txt", content });
      expect(result.result.is_error).toBe(true);
      expect(result.events[0].payload?.arguments).toBeUndefined();
      await expect(readFile(path.join(root, "blocked.txt"))).rejects.toThrow();
    }
    const shell = await executeBuiltinTool(root, "shell.run", { command: "touch should-not-exist", run_in_background: "false" });
    expect(shell.result.is_error).toBe(true);
    await expect(readFile(path.join(root, "should-not-exist"))).rejects.toThrow();
    const valid = await executeBuiltinTool(root, "filesystem.write", { path: "ok.txt", content: "hello", tool_call_id: "correlation" });
    expect(valid.result.is_error).toBe(false);
    expect(await readFile(path.join(root, "ok.txt"), "utf8")).toBe("hello");
  } finally { await rm(root, { recursive: true, force: true }); }
});

test("unavailable isolation never silently falls back to local execution", async () => {
  expect(() => localExecutor.start({ command: "exit 99", cwd: tmpdir(), timeoutMs: 1000, policy: isolated })).toThrow("isolation_unavailable");
  const result = await executeBuiltinTool(tmpdir(), "filesystem.write", { path: "never-created", content: "x" }, { executionPolicy: isolated });
  expect(result.result.content).toContain("isolated_tool_execution_unavailable");
  expect(result.result.is_error).toBe(true);
});

test("large escaped and Unicode outputs stay valid JSON within the wire byte bound", () => {
  for (const payload of ["你".repeat(MAX_TOOL_OUTPUT_BYTES), "\u0000".repeat(MAX_TOOL_OUTPUT_BYTES + 1), { content: "x".repeat(MAX_TOOL_OUTPUT_BYTES) }]) {
    const content = boundedToolContent(payload);
    expect(Buffer.byteLength(content)).toBeLessThanOrEqual(MAX_TOOL_OUTPUT_BYTES);
    expect(JSON.parse(content).truncated).toBe(true);
    expect(JSON.parse(content).original_bytes).toBeGreaterThan(MAX_TOOL_OUTPUT_BYTES);
  }
});

test("enabled-tool and revoked permission checks also apply when resuming approval", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "kevin-tool-authority-"));
  try {
    const settings = await loadSettings(root);
    const spec = specFromPayload({ message: "", enabled_tools: ["filesystem.read"], permission_profile: "auto" }, profileDefaults(settings));
    const call = { id: "write", name: "filesystem__write", arguments: { path: "blocked.txt", content: "x" } };
    const denied = await executeRuntimeToolCall({ options: { settings }, spec, runId: "run", toolCall: call, messages: [], toolResults: [], runtimeEvents: [] });
    expect(denied.result.is_error).toBe(true);
    const resolution = await resolvePendingApproval({ settings }, { ...spec, enabled_tools: ["filesystem.write"], denied_tools: ["filesystem__write"] }, { approval_id: "write", tool_call: call, messages: [], tool_results: [] }, true, "run");
    expect(resolution.toolResults[0].is_error).toBe(true);
    await expect(readFile(path.join(root, "blocked.txt"))).rejects.toThrow();
  } finally { await rm(root, { recursive: true, force: true }); }
});

test("auto mode still honors an explicitly required approval from the runtime", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "kevin-tool-approval-"));
  const server = Bun.serve({ port: 0, fetch: () => Response.json({ choices: [{ message: { content: "", tool_calls: [{ id: "write", type: "function", function: { name: "filesystem__write", arguments: JSON.stringify({ path: "blocked.txt", content: "x" }) } }] } }] }) });
  try {
    const settings = await loadSettings(root);
    const spec = specFromPayload({ message: "", protocol: "openai-chat", model: "fixture", api_key: "test", base_url: `http://127.0.0.1:${server.port}/v1`, enabled_tools: ["filesystem.write"], approval_required_tools: ["filesystem.write"], permission_profile: "auto" }, profileDefaults(settings));
    const result = await new AgentRuntime({ settings }).run(spec, "write", "run");
    expect(result.status).toBe("waiting_approval");
    await expect(readFile(path.join(root, "blocked.txt"))).rejects.toThrow();
  } finally { server.stop(true); await rm(root, { recursive: true, force: true }); }
});


test("runtime forwards cancellation to an executing shell command", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "kevin-runtime-cancel-"));
  const controller = new AbortController();
  let execution: ReturnType<typeof executeRuntimeToolCall> | undefined;
  try {
    const settings = await loadSettings(root);
    const spec = specFromPayload({ message: "", enabled_tools: ["shell.run"], permission_profile: "auto" }, profileDefaults(settings));
    execution = executeRuntimeToolCall({ options: { settings, signal: controller.signal }, spec, runId: "run",
      toolCall: { id: "shell", name: "shell.run", arguments: { command: "printf ready > ready.txt; sleep 10; printf wrong > should-not-exist" } }, messages: [], toolResults: [], runtimeEvents: [] });
    let ready = false;
    for (let i = 0; i < 100; i++) {
      try { ready = await readFile(path.join(root, "ready.txt"), "utf8") === "ready"; } catch {}
      if (ready) break;
      await new Promise(resolve => setTimeout(resolve, 10));
    }
    expect(ready).toBe(true);
    controller.abort();
    const result = await execution;
    expect(result.result.is_error).toBe(true);
    expect(result.result.content).toContain("killed");
    await expect(readFile(path.join(root, "should-not-exist"))).rejects.toThrow();
  } finally { controller.abort(); await execution; await rm(root, { recursive: true, force: true }); }
});
