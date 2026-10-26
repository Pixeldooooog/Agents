import { expect, test } from "bun:test";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { defineTool, type ToolRuntimeContext } from "../src/tools/toolContracts.js";
import { executeBuiltinTool, listBuiltinTools, scopedToolContext } from "../src/tools/toolRegistry.js";
import { JsonStateStore, loadSettings, specFromPayload, TaskService } from "../src/index.js";
import type { StateStore } from "../src/ports/stateStore.js";
import type { AgentRunService } from "../src/runtime/agentRunService.js";

const fullContext = (): ToolRuntimeContext => ({
  repoRoot: "/workspace",
  runId: "run_1",
  spec: specFromPayload({ message: "" }),
  store: {} as StateStore,
  taskRunner: { run: async () => ({}), cancel: async () => ({}) },
  agentRunner: { run: async () => ({ status: "completed", content: "" }) },
  commandExecutor: { start: () => { throw new Error("unused"); } },
  conversation: { messages: [], runtimeEvents: [] },
  onToolStart: () => undefined
});

test("handlers receive the invocation plus only their declared capabilities", () => {
  const tool = defineTool({ name: "probe", description: "", risk: "low", parameters: { type: "object" }, requires: ["store"], uses: ["taskRunner", "sleepWake"], handler: async () => ({}) });
  const scoped = scopedToolContext(tool, fullContext()) as Record<string, unknown>;
  expect(Object.keys(scoped).filter(key => scoped[key] !== undefined).sort()).toEqual(["repoRoot", "runId", "spec", "store", "taskRunner"]);
  for (const undeclared of ["agentRunner", "commandExecutor", "conversation", "onToolStart"]) expect(undeclared in scoped).toBe(false);
  expect("sleepWake" in scoped).toBe(false);
});

test("a missing required capability fails before the handler runs", async () => {
  let ran = false;
  const tool = defineTool({ name: "probe", description: "", risk: "low", parameters: { type: "object" }, requires: ["store"], handler: async () => { ran = true; return {}; } });
  expect(() => scopedToolContext(tool, { repoRoot: "/workspace" })).toThrow("tool capability unavailable: store");
  expect(ran).toBe(false);
  const result = await executeBuiltinTool(tmpdir(), "memory.list", {});
  expect(result.result.is_error).toBe(true);
  expect(result.result.content).toContain("tool capability unavailable: store");
});

test("every built-in tool declares its capabilities", () => {
  const tools = listBuiltinTools();
  expect(tools.length).toBeGreaterThan(100);
  for (const tool of tools) {
    expect(Array.isArray(tool.requires)).toBe(true);
    expect(Array.isArray(tool.uses)).toBe(true);
  }
  const byName = new Map(tools.map(tool => [tool.name, tool]));
  expect(byName.get("filesystem.list")).toMatchObject({ requires: [], uses: [] });
  expect(byName.get("memory.add")).toMatchObject({ requires: ["store"] });
  expect(byName.get("context.compact")).toMatchObject({ requires: ["conversation"] });
  expect(byName.get("shell.run")).toMatchObject({ requires: [], uses: ["commandExecutor"] });
});

test("tasks execute through the injected shared run service", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "kevin-task-runs-"));
  try {
    const settings = await loadSettings(root);
    const store = new JsonStateStore(path.join(root, "state.json"));
    const calls: string[] = [];
    const runs: Pick<AgentRunService, "runAgent"> = {
      runAgent: async (spec, message, options = {}) => {
        calls.push(message);
        const run = await store.startRun(spec);
        await options.afterRunStarted?.(run);
        const result = { run_id: run.run_id, status: "completed" as const, content: "done", messages: [], tool_results: [], events: [] };
        return { run, result, events: [] };
      }
    };
    const tasks = new TaskService(settings, store, runs);
    const task = await tasks.create({ message: "summarize" });
    const { task: finished, step } = await tasks.run(task.task_id);
    expect(calls).toEqual(["summarize"]);
    expect(finished.status).toBe("completed");
    expect(step.status).toBe("succeeded");
  } finally { await rm(root, { recursive: true, force: true }); }
});
