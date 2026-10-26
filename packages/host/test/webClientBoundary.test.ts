import { TerminalHostSession } from "../src/terminal/terminalHostSession.js";
import { expect, test } from "bun:test";
import { createApiClient } from "../../../apps/web/src/runtime/apiClient.js";
import { mkdtemp, rm } from "node:fs/promises";
import path from "node:path";
import { tmpdir } from "node:os";
import { createHostServices } from "../src/services/hostServices.js";
import { createAgentHttpServer } from "../src/http/agentHttpServer.js";

const envelope = (data: unknown) => ({ success: true, code: "200", message: "success", data });

test("web client rejects malformed JSON, invalid data, and incomplete/mismatched events", async () => {
  let body = "{";
  const server = Bun.serve({ port: 0, hostname: "127.0.0.1", fetch: () => new Response(body) });
  const api = createApiClient({ baseUrl: () => server.url.toString().replace(/\/$/, ""), token: () => "" });
  try {
    await expect(api.health()).rejects.toThrow("JSON");
    body = JSON.stringify(envelope({}));
    await expect(api.health()).rejects.toThrow("health");
    body = JSON.stringify(envelope({ runs: [{ run_id: "fake" }] }));
    await expect(api.runs()).rejects.toThrow("runs");
    body = 'event: done\ndata: {"type":"text_delta","payload":{}}\n\n';
    await expect(api.chatStream({ message: "x" }, () => {})).rejects.toThrow("mismatch");
    body = 'event: text_delta\ndata: {"type":"text_delta","payload":{"delta":"hi"}}\n\n';
    await expect(api.chatStream({ message: "x" }, () => {})).rejects.toThrow("before completion");
  } finally { await server.stop(true); }
});

test("real Host and Web client agree on envelopes, stream events and continued history", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "kevin-web-client-"));
  const received: Array<{ messages: Array<{ content: string }> }> = [];
  const model = Bun.serve({ hostname: "127.0.0.1", port: 0, async fetch(request) {
    const payload = await request.json(); received.push(payload);
    if (payload.stream) return new Response('data: {"choices":[{"index":0,"delta":{"content":"blue"},"finish_reason":null}]}\n\ndata: {"choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n', { headers: { "content-type": "text/event-stream" } });
    return Response.json({ choices: [{ message: { content: "blue" } }] });
  } });
  const services = await createHostServices(root);
  services.settings.host.accessToken = "";
  const host = createAgentHttpServer(services);
  try {
    await new Promise<void>(resolve => host.listen(0, "127.0.0.1", resolve));
    const address = host.address(); if (!address || typeof address === "string") throw new Error("missing address");
    const api = createApiClient({ baseUrl: () => `http://127.0.0.1:${address.port}`, token: () => "" });
    expect((await api.health()).status).toBe("ok");
    const payload = { message: "remember blue", model: "fixture", api_key: "fixture", protocol: "openai-chat", base_url: model.url.toString() };
    const first = await api.chat(payload);
    expect(first.status).toBe("completed");
    await expect(api.chat({ ...payload, tenant_id: "other", previous_run_id: first.run_id })).rejects.toThrow("scope");
    const frames: string[] = [];
    await api.chatStream({ ...payload, message: "which color", previous_run_id: first.run_id }, event => { frames.push(event.event); });
    expect(frames).toContain("done");
    expect(received[1]!.messages.some(item => item.content === "remember blue")).toBe(true);
    expect((await api.runs()).runs).toHaveLength(2);
    expect((await api.modelProfiles()).profiles.length).toBeGreaterThan(0);
    expect((await api.runTrace(first.run_id)).run_id).toBe(first.run_id);
    services.settings.agent.protocol = "openai-chat";
    services.settings.models.openai = { ...services.settings.models.openai, model: "fixture", apiKey: "fixture", baseUrl: model.url.toString() };
    let finished!: () => void;
    let failed!: (error: Error) => void;
    const done = new Promise<void>((resolve, reject) => { finished = resolve; failed = reject; });
    const terminal = new TerminalHostSession(root, services, {
      write(value: unknown) {
        if (!value || typeof value !== "object" || !("type" in value)) return;
        if (value.type === "turn_finished") finished();
        if (value.type === "error") failed(new Error(JSON.stringify(value)));
      },
      runtimeEvent() {}
    });
    await terminal.handleCommand({ type: "slash", text: `/resume ${first.run_id}` });
    await terminal.handleCommand({ type: "user_message", text: "continue in terminal" });
    await done;
    await terminal.close();
    expect(received[2]!.messages.some(item => item.content === "remember blue")).toBe(true);
  } finally { await new Promise<void>(resolve => host.close(() => resolve())); await services.close(); await model.stop(true); await rm(root, { recursive: true, force: true }); }
});
