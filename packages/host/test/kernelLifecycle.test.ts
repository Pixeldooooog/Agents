import { expect, test } from "bun:test";
import { mkdtemp, rm, mkdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { createInterface } from "node:readline";
import { spawn } from "node:child_process";
import { createHostServices } from "../src/services/hostServices.js";
import { createAgentHttpServer } from "../src/http/agentHttpServer.js";

function slowModel() {
  let seen!: () => void;
  const requested = new Promise<void>(resolve => { seen = resolve; });
  const server = Bun.serve({ hostname: "127.0.0.1", port: 0, fetch() {
    seen();
    return new Response(new ReadableStream({ start(controller) {
      controller.enqueue(new TextEncoder().encode('data: {"choices":[{"index":0,"delta":{"content":"waiting"},"finish_reason":null}]}\n\n'));
    } }), { headers: { "content-type": "text/event-stream" } });
  } });
  return { server, requested, baseUrl: `http://127.0.0.1:${server.port}/v1` };
}

test("disconnecting HTTP SSE cancels the actual model read and persists canceled status", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "kevin-http-cancel-"));
  const model = slowModel();
  const services = await createHostServices(root);
  services.settings.host.accessToken = "";
  const host = createAgentHttpServer(services);
  try {
    await new Promise<void>(resolve => host.listen(0, "127.0.0.1", resolve));
    const address = host.address();
    if (!address || typeof address === "string") throw new Error("missing address");
    const base = `http://127.0.0.1:${address.port}`;
    const abort = new AbortController();
    const response = await fetch(`${base}/api/v1/agent/chat/stream`, { method: "POST", headers: { "content-type": "application/json", Origin: base }, signal: abort.signal,
      body: JSON.stringify({ message: "wait", protocol: "openai-chat", model: "fixture", api_key: "fixture", base_url: model.baseUrl }) });
    const consuming = response.text().catch(() => "canceled");
    await model.requested;
    abort.abort();
    await consuming;
    let run = (await services.store.listRuns({ limit: 1 }))[0];
    for (let i = 0; i < 100 && run.status !== "cancelled"; i++) {
      await new Promise(resolve => setTimeout(resolve, 10));
      run = (await services.store.loadRun(run.run_id))!;
    }
    expect(run.status).toBe("cancelled");
    expect(run.events.at(-1)?.payload?.status).toBe("cancelled");
  } finally {
    host.closeAllConnections(); await new Promise<void>(resolve => host.close(() => resolve()));
    await model.server.stop(true); await rm(root, { recursive: true, force: true });
  }
});

test("real terminal host reads cancel while a streamed model request is pending", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "kevin-terminal-cancel-"));
  const model = slowModel();
  await mkdir(path.join(root, "config"));
  await writeFile(path.join(root, "config/defaults.toml"), `[agent]\ndefault_protocol = "openai-chat"\ndefault_model = "fixture"\n[models.openai]\nbase_url = "${model.baseUrl}"\napi_key = "fixture"\nmodel = "fixture"\n`);
  const child = spawn(process.execPath, [path.join(import.meta.dir, "../src/terminal/main.ts"), "--repo-root", root], { stdio: ["pipe", "pipe", "pipe"], env: { ...process.env, OPENAI_API_KEY: "fixture", OPENAI_BASE_URL: model.baseUrl, AGENT_DEFAULT_PROTOCOL: "openai-chat", AGENT_DEFAULT_MODEL: "fixture" } });
  const events: Record<string, unknown>[] = [];
  const lines = createInterface({ input: child.stdout });
  lines.on("line", line => { try { events.push(JSON.parse(line)); } catch {} });
  const waitFor = async (type: string) => {
    for (let i = 0; i < 300; i++) {
      const event = events.find(event => event.type === type);
      if (event) return event;
      await new Promise(resolve => setTimeout(resolve, 10));
    }
    throw new Error(`missing ${type}: ${JSON.stringify(events)}`);
  };
  try {
    await waitFor("ready");
    child.stdin.write(JSON.stringify({ type: "user_message", text: "wait for cancellation" }) + "\n");
    await model.requested;
    child.stdin.write(JSON.stringify({ type: "cancel" }) + "\n");
    expect((await waitFor("turn_finished")).status).toBe("cancelled");
    child.stdin.write(JSON.stringify({ type: "exit" }) + "\n");
    await waitFor("exit");
  } finally { child.kill(); lines.close(); await model.server.stop(true); await rm(root, { recursive: true, force: true }); }
});
