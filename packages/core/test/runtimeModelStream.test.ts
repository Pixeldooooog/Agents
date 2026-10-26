import { expect, test } from "bun:test";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { AgentRuntime } from "../src/runtime/agentRuntime.js";
import { loadSettings } from "../src/config/settings.js";
import { profileDefaults } from "../src/models/modelProfiles.js";
import { specFromPayload } from "../src/types/agentTypes.js";
import { modelStreamResponse } from "./fixtures/modelResponse.js";

for (const scenario of ["complete", "truncated", "malformed second call", "approval", "canceled"] as const) {
  test(`runtime streamed tools: ${scenario}`, async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-stream-turn-"));
    const controller = new AbortController();
    let requests = 0;
    let sawDelta = false;
    const server = Bun.serve({ port: 0, hostname: "127.0.0.1", async fetch(request) {
      const body = await request.json();
      expect(body.stream).toBe(true);
      requests++;
      if (requests > 1) {
        expect(body.messages.at(-1)).toMatchObject({ role: "tool", tool_call_id: "write_1" });
        expect(await readFile(path.join(root, "result.txt"), "utf8")).toBe("saved");
        return modelStreamResponse({ choices: [{ message: { content: "finished" } }] });
      }
      const calls = [{ index: 0, id: "write_1", type: "function", function: { name: "filesystem__write", arguments: JSON.stringify({ path: "result.txt", content: "saved" }) } }];
      if (scenario === "malformed second call") calls.push({ index: 1, id: "write_2", type: "function", function: { name: "filesystem__write", arguments: "{" } });
      const values = [
        { choices: [{ index: 0, delta: { content: "working" }, finish_reason: null }] },
        { choices: [{ index: 0, delta: { tool_calls: calls }, finish_reason: null }] },
        { choices: [{ index: 0, delta: {}, finish_reason: "tool_calls" }] }
      ];
      return new Response(values.map(value => `data:${JSON.stringify(value)}\n\n`).join("") + (scenario === "truncated" ? "" : "data:[DONE]\n\n"), { headers: { "Content-Type": "text/event-stream" } });
    } });
    try {
      const settings = await loadSettings(root);
      const spec = specFromPayload({ protocol: "openai-chat", model: "fixture", api_key: "fixture", base_url: `http://127.0.0.1:${server.port}/v1`, enabled_tools: ["filesystem.write"], permission_profile: "auto", approval_required_tools: scenario === "approval" ? ["filesystem.write"] : [] }, profileDefaults(settings));
      const result = await new AgentRuntime({ settings, stream: true, signal: controller.signal, onEvent: async event => {
        if (event.type === "text_delta" && event.payload?.delta === "working") {
          sawDelta = true;
          await expect(readFile(path.join(root, "result.txt"))).rejects.toThrow();
          if (scenario === "canceled") controller.abort();
        }
      } }).run(spec, "write the file", "run");
      expect(sawDelta).toBe(true);
      if (scenario === "complete") {
        expect(result.status).toBe("finished");
        expect(result.tool_results).toHaveLength(1);
        expect(requests).toBe(2);
      } else {
        expect(result.status).toBe(scenario === "approval" ? "awaiting_approval" : scenario === "canceled" ? "canceled" : "error");
        expect(result.tool_results).toHaveLength(0);
        expect(result.events.some(event => event.type === "tool_start")).toBe(false);
        await expect(readFile(path.join(root, "result.txt"))).rejects.toThrow();
        expect(requests).toBe(1);
      }
    } finally { await server.stop(true); await rm(root, { recursive: true, force: true }); }
  });
}

test("stream deltas are delivered live without per-token persistence", async () => {
  const { AgentRunService } = await import("../src/runtime/agentRunService.js");
  const { JsonStateStore } = await import("../src/store/jsonStateStore.js");
  const root = await mkdtemp(path.join(tmpdir(), "kevin-stream-store-"));
  const server = Bun.serve({ port: 0, hostname: "127.0.0.1", fetch: () => modelStreamResponse({ choices: [{ message: { content: "hello" } }] }) });
  try {
    const settings = await loadSettings(root);
    const store = new JsonStateStore(path.join(root, "state.json"));
    const service = new AgentRunService({ settings, store });
    const spec = service.specFromPayload({ protocol: "openai-chat", model: "fixture", api_key: "fixture", base_url: `http://127.0.0.1:${server.port}/v1`, permission_profile: "auto" });
    const live: string[] = [];
    const { result, run } = await service.runAgent(spec, "hello", { stream: true, onEvent: event => { live.push(event.type); } });
    expect(result.status).toBe("finished");
    expect(live).toContain("text_delta");
    expect(run.events.some(event => event.type === "text_delta")).toBe(false);
    expect(run.events.find(event => event.type === "model_message")?.payload?.content).toBe("hello");
  } finally { await server.stop(true); await rm(root, { recursive: true, force: true }); }
});

test("Responses context survives persisted approval and replays to the same provider", async () => {
  const { AgentRunService } = await import("../src/runtime/agentRunService.js");
  const { JsonStateStore } = await import("../src/store/jsonStateStore.js");
  const root = await mkdtemp(path.join(tmpdir(), "kevin-stream-replay-"));
  const reasoning = { type: "reasoning", id: "rs_1", summary: [], encrypted_content: "opaque" };
  const call = { type: "function_call", id: "fc_1", call_id: "call_1", name: "filesystem__write", arguments: JSON.stringify({ path: "result.txt", content: "saved" }), status: "completed" };
  let requests = 0;
  const server = Bun.serve({ port: 0, hostname: "127.0.0.1", async fetch(request) {
    const body = await request.json();
    requests++;
    let frames: unknown[];
    if (requests === 1) {
      frames = [
        { type: "response.output_item.added", output_index: 0, item: reasoning },
        { type: "response.output_item.done", output_index: 0, item: reasoning },
        { type: "response.output_item.added", output_index: 1, item: { ...call, status: "in_progress", arguments: "" } },
        { type: "response.function_call_arguments.delta", output_index: 1, item_id: "fc_1", delta: call.arguments },
        { type: "response.output_item.done", output_index: 1, item: call },
        { type: "response.completed", response: { status: "completed", output: [reasoning, call] } }
      ];
    } else {
      expect(body.input.slice(-3)).toEqual([reasoning, call, expect.objectContaining({ type: "function_call_output", call_id: "call_1" })]);
      expect(body).toMatchObject({ store: false, include: ["reasoning.encrypted_content"] });
      const item = { type: "message", id: "msg_1", role: "assistant", content: [{ type: "output_text", text: "finished" }] };
      frames = [
        { type: "response.output_item.added", output_index: 0, item: { ...item, content: [] } },
        { type: "response.output_text.delta", output_index: 0, item_id: "msg_1", content_index: 0, delta: "finished" },
        { type: "response.output_item.done", output_index: 0, item },
        { type: "response.completed", response: { status: "completed", output: [item] } }
      ];
    }
    return new Response(frames.map(frame => `data:${JSON.stringify(frame)}\n\n`).join(""), { headers: { "Content-Type": "text/event-stream" } });
  } });
  try {
    const settings = await loadSettings(root);
    const file = path.join(root, "state.json");
    const service = new AgentRunService({ settings, store: new JsonStateStore(file) });
    const spec = service.specFromPayload({ protocol: "openai-responses", model: "fixture", api_key: "fixture", base_url: `http://127.0.0.1:${server.port}/v1`, enabled_tools: ["filesystem.write"], approval_required_tools: ["filesystem.write"], permission_profile: "auto" });
    const paused = await service.runAgent(spec, "write", { stream: true });
    expect(paused.result.status).toBe("awaiting_approval");
    await expect(readFile(path.join(root, "result.txt"))).rejects.toThrow();
    const restarted = new AgentRunService({ settings, store: new JsonStateStore(file) });
    const resumed = await restarted.resumeApproval(paused.run.run_id, true, { stream: true, spec, approvalId: paused.result.pending_approval!.approval_id });
    expect(resumed.result.status).toBe("finished");
    expect(resumed.result.content).toBe("finished");
    expect(requests).toBe(2);
  } finally { await server.stop(true); await rm(root, { recursive: true, force: true }); }
});
