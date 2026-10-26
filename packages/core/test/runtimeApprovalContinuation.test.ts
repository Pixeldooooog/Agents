import { describe, expect, test } from "bun:test";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { AgentRunService } from "../src/runtime/agentRunService.js";
import { AgentRuntime } from "../src/runtime/agentRuntime.js";
import { JsonStateStore } from "../src/store/jsonStateStore.js";
import { loadSettings } from "../src/config/settings.js";
import type { AgentSpec } from "../src/types/agentTypes.js";
import type { PendingApproval } from "../src/types/runtimeTypes.js";

async function fixture(run: (context: {
  root: string; service: AgentRunService; reopen: () => AgentRunService; spec: AgentSpec;
  settings: Awaited<ReturnType<typeof loadSettings>>; requestCount: () => number;
}) => Promise<void>, maxIterations = 4) {
  const root = await mkdtemp(path.join(tmpdir(), "kevin-approval-continuation-"));
  let requests = 0;
  const server = Bun.serve({ port: 0, hostname: "127.0.0.1", async fetch(request) {
    const body = await request.json();
    requests++;
    if (requests > 1) {
      expect(body.messages.slice(-3).map((message: { tool_call_id: string }) => message.tool_call_id)).toEqual(["a", "b", "c"]);
      return Response.json({ choices: [{ message: { content: "finished" } }], usage: { prompt_tokens: 3, completion_tokens: 2 } });
    }
    return Response.json({ choices: [{ message: { content: "plan", tool_calls: [
      { id: "a", type: "function", function: { name: "filesystem__read", arguments: JSON.stringify({ path: "source.txt" }) } },
      { id: "b", type: "function", function: { name: "filesystem__write", arguments: JSON.stringify({ path: "b.txt", content: "B" }) } },
      { id: "c", type: "function", function: { name: "filesystem__write", arguments: JSON.stringify({ path: "c.txt", content: "C" }) } }
    ] } }], usage: { prompt_tokens: 3, completion_tokens: 2 } });
  } });
  try {
    await writeFile(path.join(root, "source.txt"), "source");
    const settings = await loadSettings(root);
    const reopen = () => new AgentRunService({ settings, store: new JsonStateStore(path.join(root, "state.json")) });
    const service = reopen();
    const spec = service.specFromPayload({ protocol: "openai-chat", model: "fixture", api_key: "fixture", base_url: `http://127.0.0.1:${server.port}/v1`, enabled_tools: ["filesystem.read", "filesystem.write"], approval_required_tools: ["filesystem.write"], permission_profile: "auto", runtime: { maxToolIterations: maxIterations } });
    await run({ root, service, reopen, spec, settings, requestCount: () => requests });
  } finally { await server.stop(true); await rm(root, { recursive: true, force: true }); }
}
function pending(value: { result: { pending_approval?: PendingApproval } }): PendingApproval {
  expect(value.result.pending_approval).toBeDefined();
  return value.result.pending_approval!;
}

describe("approval turn continuation", () => {
  for (const approved of [true, false]) {
    test(`continues B (${approved ? "approved" : "denied"}) then C after reopening the store`, () => fixture(async ({ root, service, reopen, spec, requestCount }) => {
      const first = await service.runAgent(spec, "do A B C");
      expect(first.result.tool_results.map(result => result.tool_call_id)).toEqual(["a"]);
      const b = pending(first);
      expect(b.continuation?.remaining_tool_calls.map(call => call.id)).toEqual(["c"]);
      expect(b.continuation?.model_usage?.totalTokens).toBe(5);
      const second = await reopen().resumeApproval(first.run.run_id, approved, { spec, approvalId: b.approval_id });
      expect(requestCount()).toBe(1);
      expect(second.result.tool_results.map(result => result.tool_call_id)).toEqual(["a", "b"]);
      expect(second.result.tool_results[1].is_error).toBe(!approved);
      if (approved) expect(await readFile(path.join(root, "b.txt"), "utf8")).toBe("B");
      else await expect(readFile(path.join(root, "b.txt"))).rejects.toThrow();
      const c = pending(second);
      expect(c.approval_id).not.toBe(b.approval_id);
      expect(c.tool_call.id).toBe("c");
      const final = await reopen().resumeApproval(first.run.run_id, true, { spec, approvalId: c.approval_id });
      expect(final.result.status).toBe("completed");
      expect(final.result.tool_results.map(result => result.tool_call_id)).toEqual(["a", "b", "c"]);
      expect(final.result.model_usage?.totalTokens).toBe(10);
      expect(final.result.events.at(-1)?.payload?.num_turns).toBe(2);
      expect(await readFile(path.join(root, "c.txt"), "utf8")).toBe("C");
      expect(requestCount()).toBe(2);
    }));
  }

  test("concurrent store instances cannot consume the same approval twice; stale ID cannot approve C", () => fixture(async ({ service, reopen, spec }) => {
    const first = await service.runAgent(spec, "do A B C");
    const approvalId = pending(first).approval_id;
    const outcomes = await Promise.allSettled([reopen().resumeApproval(first.run.run_id, true, { spec, approvalId }), reopen().resumeApproval(first.run.run_id, true, { spec, approvalId })]);
    expect(outcomes.filter(outcome => outcome.status === "fulfilled")).toHaveLength(1);
    expect(outcomes.filter(outcome => outcome.status === "rejected")).toHaveLength(1);
    await expect(reopen().resumeApproval(first.run.run_id, true, { spec, approvalId })).rejects.toMatchObject({ statusCode: 409 });
  }));

  test("revoked permissions apply to both the approved call and remaining calls", () => fixture(async ({ service, spec, root, requestCount }) => {
    const first = await service.runAgent(spec, "do A B C");
    const final = await service.resumeApproval(first.run.run_id, true, { spec: { ...spec, denied_tools: ["filesystem.write"] }, approvalId: pending(first).approval_id });
    expect(final.result.status).toBe("completed");
    expect(final.result.tool_results.map(result => result.is_error)).toEqual([false, true, true]);
    await expect(readFile(path.join(root, "b.txt"))).rejects.toThrow();
    await expect(readFile(path.join(root, "c.txt"))).rejects.toThrow();
    expect(requestCount()).toBe(2);
  }));

  test("approval resumes cannot reset or raise the original iteration budget", () => fixture(async ({ service, spec, requestCount }) => {
    const first = await service.runAgent(spec, "do A B C");
    const raised = { ...spec, runtime: { ...spec.runtime, maxToolIterations: 20 } };
    const second = await service.resumeApproval(first.run.run_id, true, { spec: raised, approvalId: pending(first).approval_id });
    const final = await service.resumeApproval(first.run.run_id, true, { spec: raised, approvalId: pending(second).approval_id });
    expect(final.result.status).toBe("failed");
    expect(final.result.events.find(event => event.type === "error")?.payload?.message).toContain("max iterations");
    expect(final.result.model_usage?.totalTokens).toBe(5);
    expect(requestCount()).toBe(1);
  }, 1));

  test("pre-canceled requests do not consume approval, and runtime cancellation retains usage", () => fixture(async ({ service, spec, settings, root }) => {
    const first = await service.runAgent(spec, "do A B C");
    const snapshot = pending(first);
    const signal = AbortSignal.abort();
    await expect(service.resumeApproval(first.run.run_id, true, { spec, approvalId: snapshot.approval_id, signal })).rejects.toMatchObject({ name: "AbortError" });
    const canceled = await new AgentRuntime({ settings, signal }).resumeWithApproval(spec, snapshot, true, first.run.run_id);
    expect(canceled.status).toBe("cancelled");
    expect(canceled.model_usage?.totalTokens).toBe(5);
    await expect(readFile(path.join(root, "b.txt"))).rejects.toThrow();
    const resumed = await service.resumeApproval(first.run.run_id, false, { spec, approvalId: snapshot.approval_id });
    expect(resumed.result.status).toBe("waiting_approval");
  }));

  test("missing or altered continuation fails before any approved side effect", () => fixture(async ({ service, spec, settings, root }) => {
    const first = await service.runAgent(spec, "do A B C");
    for (const damaged of [
      { ...pending(first), continuation: undefined },
      { ...pending(first), tool_call: { ...pending(first).tool_call, arguments: { path: "bad.txt", content: "bad" } } }
    ]) {
      const result = await new AgentRuntime({ settings }).resumeWithApproval(spec, damaged, true, first.run.run_id);
      expect(result.status).toBe("failed");
    }
    await expect(readFile(path.join(root, "b.txt"))).rejects.toThrow();
    await expect(readFile(path.join(root, "bad.txt"))).rejects.toThrow();
  }));
});

test("a corrupt JSON store fails without silently replacing saved state", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "kevin-corrupt-store-"));
  const file = path.join(root, "state.json");
  try {
    await writeFile(file, "{broken");
    const store = new JsonStateStore(file);
    await expect(store.claimPendingApproval("run", "approval")).rejects.toThrow();
    expect(await readFile(file, "utf8")).toBe("{broken");
  } finally { await rm(root, { recursive: true, force: true }); }
});
