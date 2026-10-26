import { expect, test } from "bun:test";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { createHostServices } from "../src/services/hostServices.js";
import { createAgentHttpServer } from "../src/http/agentHttpServer.js";

test("HTTP approval requires the observed ID and a boolean decision", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "kevin-approval-http-"));
  const provider = Bun.serve({ port: 0, hostname: "127.0.0.1", async fetch(request) {
    const body = await request.json();
    if (body.messages.some((message: { role: string }) => message.role === "tool")) return Response.json({ choices: [{ message: { content: "finished" } }] });
    return Response.json({ choices: [{ message: { content: "", tool_calls: [{ id: "write", type: "function", function: { name: "filesystem__write", arguments: JSON.stringify({ path: "result.txt", content: "saved" }) } }] } }] });
  } });
  const services = await createHostServices(root);
  services.settings.models.openai.apiKey = "fixture";
  services.settings.host = { ...services.settings.host, accessToken: "", bindHost: "127.0.0.1" };
  const host = createAgentHttpServer(services);
  try {
    const spec = services.runs.specFromPayload({ protocol: "openai-chat", model: "fixture", base_url: `http://127.0.0.1:${provider.port}/v1`, enabled_tools: ["filesystem.write"], permission_profile: "ask" });
    const paused = await services.runs.runAgent(spec, "write");
    const approvalId = paused.result.pending_approval!.approval_id;
    await new Promise<void>(resolve => host.listen(0, "127.0.0.1", resolve));
    const address = host.address();
    if (!address || typeof address === "string") throw new Error("missing HTTP address");
    const base = `http://127.0.0.1:${address.port}`;
    const post = (body: unknown) => fetch(`${base}/api/v1/agent/runs/${paused.run.run_id}/approval`, { method: "POST", headers: { "Content-Type": "application/json", Origin: base }, body: JSON.stringify(body) });
    expect((await post({ approved: true })).status).toBe(400);
    expect((await post({ approval_id: approvalId, approved: "false" })).status).toBe(400);
    expect((await post({ approval_id: "stale", approved: true })).status).toBe(409);
    await expect(readFile(path.join(root, "result.txt"))).rejects.toThrow();
    expect((await post({ approval_id: approvalId, approved: true })).status).toBe(200);
    expect(await readFile(path.join(root, "result.txt"), "utf8")).toBe("saved");
    expect((await post({ approval_id: approvalId, approved: true })).status).toBe(409);
  } finally {
    host.closeAllConnections();
    await new Promise<void>(resolve => host.close(() => resolve()));
    await provider.stop(true);
    await rm(root, { recursive: true, force: true });
  }
});
