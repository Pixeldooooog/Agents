import { executeBuiltinTool } from "../src/tools/toolRegistry.js";
import type { Message } from "../src/types/runtimeTypes.js";
import { expect, test } from "bun:test";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { AgentRunService } from "../src/runtime/agentRunService.js";
import { JsonStateStore } from "../src/store/jsonStateStore.js";
import { loadSettings } from "../src/config/settings.js";
import { conversationHistory } from "../src/session/conversationHistory.js";

test("continued runs replay persisted history after reopening, and reject different scopes", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "kevin-conversation-"));
  const requests: Array<{ messages: Array<{ role: string; content: string }> }> = [];
  const server = Bun.serve({ port: 0, hostname: "127.0.0.1", async fetch(request) {
    requests.push(await request.json());
    return Response.json({ choices: [{ message: { content: `answer ${requests.length}` } }] });
  } });
  try {
    const settings = await loadSettings(root);
    const store = new JsonStateStore(path.join(root, "state.json"));
    const service = () => new AgentRunService({ settings, store: new JsonStateStore(path.join(root, "state.json")) });
    const spec = service().specFromPayload({ model: "fixture", api_key: "secret-not-persisted", base_url: server.url.toString(), tenant_id: "one", message: "" });
    const first = await service().runAgent(spec, "remember blue");
    expect(first.result.status).toBe("completed");
    const second = await service().runAgent(spec, "what color?", { previousRunId: first.run.run_id });
    expect(second.result.status).toBe("completed");
    expect(requests[1]!.messages.filter(item => item.role !== "system").map(item => item.content)).toEqual(["remember blue", "answer 1", "what color?"]);
    expect(JSON.stringify(await store.loadRun(second.run.run_id))).not.toContain("secret-not-persisted");
    await expect(service().runAgent({ ...spec, tenant_id: "two" }, "steal", { previousRunId: first.run.run_id })).rejects.toThrow("scope");
    const old = await store.startRun(spec);
    await store.transitionRun(old.run_id, ["preparing", "running", "completed"]);
    await expect(service().conversationForRun(old.run_id, spec)).rejects.toThrow("snapshot");
    expect(requests).toHaveLength(2);
  } finally { await server.stop(true); await rm(root, { recursive: true, force: true }); }
});

test("history rejects incomplete and orphaned tool groups but preserves native context", () => {
  expect(() => conversationHistory([{ role: "tool", tool_call_id: "a", content: "x" }])).toThrow("orphaned");
  const assistant = { role: "assistant", content: "", tool_calls: [{ id: "a", name: "read", arguments: {} }] };
  expect(() => conversationHistory([assistant, { role: "user", content: "next" }])).toThrow("incomplete");
  const native = { protocol: "openai-responses", model: "m", baseUrl: "http://local", items: [{ type: "reasoning", encrypted_content: "opaque" }] };
  const messages = [assistant, { role: "tool", tool_call_id: "a", content: "ok" }, { role: "assistant", content: "done", model_context: native }];
  expect(conversationHistory(messages)).toEqual(messages);
});

test("context mutation keeps complete call groups and the active tool's pending result", async () => {
  for (const tool of ["context.compact", "context.rewind"]) {
    const messages: Message[] = [
      { role: "user", content: "first" },
      { role: "assistant", content: "", tool_calls: [{ id: "read", name: "filesystem.read", arguments: {} }] },
      { role: "tool", tool_call_id: "read", content: "file" },
      { role: "user", content: "next" },
      { role: "assistant", content: "", tool_calls: [{ id: "edit-context", name: tool, arguments: {} }] }
    ];
    const execution = await executeBuiltinTool("/tmp", tool, { tool_call_id: "edit-context", ...(tool === "context.rewind" ? { drop_last: 2 } : {}) }, { conversation: { messages, runtimeEvents: [] } });
    expect(execution.result.is_error).toBe(false);
    messages.push({ role: "tool", tool_call_id: "edit-context", content: execution.result.content });
    expect(() => conversationHistory(messages)).not.toThrow();
    expect(messages.some(message => message.tool_calls?.some(call => call.id === "edit-context"))).toBe(true);
  }
});
