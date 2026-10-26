import { expect, test } from "bun:test";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { AgentRunService, JsonStateStore, loadSettings, specFromPayload } from "../src/index.js";
import type { RuntimeEvent } from "../src/types/runtimeTypes.js";
import { modelStreamResponse } from "./fixtures/modelResponse.js";

async function withStore(run: (store: JsonStateStore, filename: string) => Promise<void>): Promise<void> {
  const root = await mkdtemp(path.join(tmpdir(), "kevin-run-state-"));
  const filename = path.join(root, "state.json");
  try { await run(new JsonStateStore(filename), filename); }
  finally { await rm(root, { recursive: true, force: true }); }
}

const spec = () => specFromPayload({ message: "hello", model: "test" });

test("runs start queued and advance through contract transitions with a version per step", async () => {
  await withStore(async (store) => {
    const queued = await store.startRun(spec());
    expect(queued.status).toBe("queued");
    expect(queued.version).toBe(0);
    const running = await store.transitionRun(queued.run_id, ["preparing", "running"]);
    expect(running.status).toBe("running");
    expect(running.version).toBe(2);
    const completed = await store.transitionRun(queued.run_id, ["completed"]);
    expect(completed.status).toBe("completed");
    expect(completed.version).toBe(3);
  });
});

test("an invalid step rejects the whole sequence and leaves the stored run untouched", async () => {
  await withStore(async (store) => {
    const { run_id } = await store.startRun(spec());
    await expect(store.transitionRun(run_id, ["preparing", "running", "completed", "running"])).rejects.toThrow("invalid_run_transition:completed:running");
    const stored = await store.loadRun(run_id);
    expect(stored?.status).toBe("queued");
    expect(stored?.version).toBe(0);
    await expect(store.transitionRun(run_id, ["completed"])).rejects.toThrow("invalid_run_transition:queued:completed");
    await expect(store.transitionRun("run_missing", ["preparing"])).rejects.toThrow("run not found");
  });
});

test("claiming an approval returns the run to queued exactly once", async () => {
  await withStore(async (store) => {
    const { run_id } = await store.startRun(spec());
    await store.transitionRun(run_id, ["preparing", "running"]);
    const pending = { approval_id: "approval-1", tool_call: { id: "call", name: "fs.write", arguments: {} }, messages: [], tool_results: [] };
    await store.setPendingApproval(run_id, pending);
    await store.transitionRun(run_id, ["waiting_approval"]);
    expect(await store.claimPendingApproval(run_id, "other")).toBeUndefined();
    expect((await store.claimPendingApproval(run_id, "approval-1"))?.approval_id).toBe("approval-1");
    expect(await store.claimPendingApproval(run_id, "approval-1")).toBeUndefined();
    const claimed = await store.loadRun(run_id);
    expect(claimed?.status).toBe("queued");
    expect(claimed?.version).toBe(4);
    expect(claimed?.pending_approval).toBeUndefined();
  });
});

test("state files with unsupported execution statuses fail to load instead of passing through", async () => {
  await withStore(async (store, filename) => {
    await writeFile(filename, JSON.stringify({ runs: [{ run_id: "run_old", status: "finished", version: 1, events: [] }] }));
    await expect(store.listRuns()).rejects.toThrow('invalid state file: runs[0].status has unsupported value "finished"');
    await writeFile(filename, JSON.stringify({ runs: [{ run_id: "run_new", status: "completed", events: [] }] }));
    await expect(store.listRuns()).rejects.toThrow("runs[0].version must be a non-negative integer");
    await writeFile(filename, JSON.stringify({ tasks: [{ task_id: "task_old", status: "canceled" }] }));
    await expect(store.listTasks()).rejects.toThrow('tasks[0].status has unsupported value "canceled"');
    await writeFile(filename, JSON.stringify({ runs: [{ run_id: "run_bare", status: "completed", version: 1, events: [{ type: "done", payload: {} }] }] }));
    await expect(store.listRuns()).rejects.toThrow("runs[0].events[0] is missing its event envelope");
    await writeFile(filename, JSON.stringify({ steps: [{ step_id: "step_old", status: "awaiting_approval" }] }));
    await expect(store.listSteps("task")).rejects.toThrow('steps[0].status has unsupported value "awaiting_approval"');
  });
});

test("persisted events carry contract envelopes with a contiguous per-run sequence", async () => {
  await withStore(async (store) => {
    const { run_id, events: [created] } = await store.startRun(spec());
    expect(created).toMatchObject({ type: "run_created", actor: "system", run_id, sequence: 0, schema_version: 1, payload: { run_id } });
    const tool = await store.recordEvent(run_id, { type: "tool_start", name: "fs.read", payload: {} });
    const message = await store.recordEvent(run_id, { type: "model_message", payload: { content: "hi" } });
    expect([tool.sequence, tool.actor, message.sequence, message.actor]).toEqual([1, "tool", 2, "agent"]);
    expect(Number.isNaN(Date.parse(message.occurred_at))).toBe(false);
    const stored = (await store.loadRun(run_id))!.events;
    expect(stored.map(event => event.sequence)).toEqual([0, 1, 2]);
    expect(new Set(stored.map(event => event.event_id)).size).toBe(3);
    await expect(store.recordEvent("run_missing", { type: "done" })).rejects.toThrow("run not found");
  });
});

test("run subscribers receive the persisted envelope while text deltas stay transient", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "kevin-run-events-"));
  const server = Bun.serve({ port: 0, hostname: "127.0.0.1", fetch: () => modelStreamResponse({ choices: [{ message: { content: "hello" } }] }) });
  try {
    const service = new AgentRunService({ settings: await loadSettings(root), store: new JsonStateStore(path.join(root, "state.json")) });
    const spec = service.specFromPayload({ protocol: "openai-chat", model: "fixture", api_key: "fixture", base_url: `http://127.0.0.1:${server.port}/v1`, permission_profile: "auto" });
    const live: RuntimeEvent[] = [];
    const { run } = await service.runAgent(spec, "hello", { stream: true, onEvent: event => { live.push(event); } });
    const delta = live.find(event => event.type === "text_delta");
    expect(delta && "event_id" in delta).toBe(false);
    const persistedLive = live.filter(event => event.type !== "text_delta");
    expect(persistedLive.map(event => (event as { event_id?: string }).event_id)).toEqual(run.events.slice(1).map(event => event.event_id));
    expect(run.events.at(-1)).toMatchObject({ type: "done", payload: { status: "completed" } });
  } finally { await server.stop(true); await rm(root, { recursive: true, force: true }); }
});
