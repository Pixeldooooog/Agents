import { expect, test } from "bun:test";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { JsonStateStore, specFromPayload } from "../src/index.js";

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
    await writeFile(filename, JSON.stringify({ steps: [{ step_id: "step_old", status: "awaiting_approval" }] }));
    await expect(store.listSteps("task")).rejects.toThrow('steps[0].status has unsupported value "awaiting_approval"');
  });
});
