import { expect, test } from "bun:test";
import { mkdtemp, rm, readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { AgentRunService, JsonStateStore, loadSettings, createHookRecord, executeBuiltinTool } from "../src/index.js";
import { dispatchRuntimeHooks } from "../src/hooks/runtimeHooks.js";

async function fixture(run: (c: { root: string; service: AgentRunService; store: JsonStateStore; settings: Awaited<ReturnType<typeof loadSettings>>; baseUrl: string; requests: Record<string, unknown>[] }) => Promise<void>) {
  const root = await mkdtemp(path.join(tmpdir(), "kevin-runtime-hooks-"));
  const requests: Record<string, unknown>[] = [];
  const server = Bun.serve({ hostname: "127.0.0.1", port: 0, async fetch(request) {
    requests.push(await request.json());
    return Response.json({ choices: [{ message: requests.length === 1 ? {
      content: "writing", tool_calls: [{ id: "write", type: "function", function: { name: "filesystem__write", arguments: JSON.stringify({ path: "result.txt", content: "done" }) } }]
    } : { content: "finished" } }] });
  } });
  const settings = await loadSettings(root);
  const store = new JsonStateStore(path.join(root, "state.json"));
  try { await run({ root, settings, store, service: new AgentRunService({ settings, store }), baseUrl: `http://127.0.0.1:${server.port}/v1`, requests }); }
  finally { await server.stop(true); await rm(root, { recursive: true, force: true }); }
}

for (const deny of [true, false]) test(`hooks append guidance and ${deny ? "deny" : "observe"} approved execution`, () => fixture(async ({ root, service, store, baseUrl, requests }) => {
  const spec = service.specFromPayload({ model: "fixture", protocol: "openai-chat", api_key: "fixture", base_url: baseUrl, enabled_tools: ["filesystem.write"], approval_required_tools: ["filesystem.write"], permission_profile: "auto" });
  await store.saveHook(createHookRecord({ spec, event: "before_request", action: "append_system", name: "guidance", content: "Use concise results" }));
  await store.saveHook(createHookRecord({ spec, event: "post_tool_use", action: "record", name: "audit", tool: "filesystem.*" }));
  const first = await service.runAgent(spec, "write");
  expect(first.result.pending_approval).toBeDefined();
  expect(JSON.stringify(requests[0])).toContain("Use concise results");
  if (deny) await store.saveHook(createHookRecord({ spec, event: "pre_tool_use", action: "deny_tool", name: "stop", tool: "filesystem.write" }));
  const resumed = await service.resumeApproval(first.run.run_id, true, { spec, approvalId: first.result.pending_approval!.approval_id });
  expect(resumed.result.tool_results[0].is_error).toBe(deny);
  if (deny) await expect(readFile(path.join(root, "result.txt"))).rejects.toThrow();
  else expect(await readFile(path.join(root, "result.txt"), "utf8")).toBe("done");
  expect(resumed.result.events.some(event => event.type === "hook_executed")).toBe(true);
  expect((await store.loadRun(first.run.run_id))!.events.some(event => event.type === "hook_executed")).toBe(true);
}));

test("unsupported command hooks never execute; control errors fail closed and observer errors are audited", () => fixture(async ({ root, service, settings, store }) => {
  const spec = service.specFromPayload({});
  const rejected = await executeBuiltinTool(root, "hook.add", { event: "pre_tool_use", name: "command", action: "run_command", content: "touch forbidden" }, { store, spec });
  expect(rejected.result.is_error).toBe(true);
  await store.saveHook(createHookRecord({ spec, event: "pre_tool_use", action: "run_command", name: "legacy", content: "touch forbidden" }));
  await expect(dispatchRuntimeHooks({ settings, store }, spec, "pre_tool_use", "shell.run")).rejects.toThrow("control hook failed");
  await store.saveHook(createHookRecord({ spec, event: "after_response", action: "deny_tool", name: "invalid observer" }));
  const result = await dispatchRuntimeHooks({ settings, store }, spec, "after_response");
  expect(result.events[0].type).toBe("hook_error");
  await expect(readFile(path.join(root, "forbidden"))).rejects.toThrow();
}));

test("hook order is stable, scopes stay isolated and cancellation interrupts a hung hook store", () => fixture(async ({ service, settings, store }) => {
  const spec = service.specFromPayload({ tenant_id: "mine" });
  const first = createHookRecord({ spec, event: "before_request", action: "append_user", name: "first", content: "one" });
  const second = { ...createHookRecord({ spec, event: "before_request", action: "append_user", name: "second", content: "two" }), created_at: first.created_at + 1 };
  await store.saveHook(second); await store.saveHook(first);
  await store.saveHook(createHookRecord({ spec: { ...spec, tenant_id: "other" }, event: "before_request", action: "append_user", name: "foreign", content: "secret" }));
  expect((await dispatchRuntimeHooks({ settings, store }, spec, "before_request")).messages.map(message => message.content)).toEqual(["one", "two"]);
  const controller = new AbortController();
  store.listHooks = async () => new Promise(() => {});
  const result = dispatchRuntimeHooks({ settings, store, signal: controller.signal }, spec, "before_request").then(() => undefined, (error: unknown) => error);
  controller.abort();
  expect(await result).toBeInstanceOf(Error);
}));
