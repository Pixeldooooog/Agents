import { expect, test } from "bun:test";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { createHostServices } from "../src/services/hostServices.js";
import { createAgentHttpServer } from "../src/http/agentHttpServer.js";
import { createHostAccessPolicy } from "../src/http/hostAccessPolicy.js";

test("HTTP boundary rejects foreign browser writes and enforces bearer authentication", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "kevin-access-"));
  const services = await createHostServices(root);
  services.settings.host = { ...services.settings.host, bindHost: "127.0.0.1", accessToken: "test-token", corsOrigins: ["http://localhost:5173"] };
  const server = createAgentHttpServer(services);
  try {
    await new Promise<void>(resolve => server.listen(0, "127.0.0.1", resolve));
    const address = server.address() as { port: number };
    const base = `http://127.0.0.1:${address.port}`;
    const endpoint = `${base}/api/v1/agent/tasks`;
    for (const origin of ["https://evil.example", "null"]) {
      expect((await fetch(endpoint, { method: "POST", headers: { Origin: origin, Authorization: "Bearer test-token", "Content-Type": "application/json" }, body: JSON.stringify({ message: "must not save" }) })).status).toBe(403);
    }
    expect((await fetch(endpoint, { headers: { Host: "evil.example" } })).status).toBe(403);
    expect((await fetch(endpoint)).status).toBe(401);
    expect((await fetch(endpoint, { headers: { Authorization: "Bearer wrong" } })).status).toBe(401);
    const headers = { Authorization: "Bearer test-token", Origin: base };
    const before = await (await fetch(endpoint, { headers })).json();
    expect(JSON.stringify(before)).not.toContain("must not save");
    expect((await fetch(endpoint, { headers })).status).toBe(200);
    expect((await fetch(endpoint, { method: "POST", headers: { ...headers, "Content-Type": "application/json" }, body: JSON.stringify({ message: "allowed task" }) })).status).toBe(200);
    const preflight = await fetch(endpoint, { method: "OPTIONS", headers: { Origin: "http://localhost:5173" } });
    expect(preflight.status).toBe(204);
    expect(preflight.headers.get("access-control-allow-origin")).toBe("http://localhost:5173");
    expect((await fetch(`${base}/health`)).status).toBe(200);
    expect(() => createHostAccessPolicy({ ...services.settings.host, bindHost: "0.0.0.0", accessToken: "" })).toThrow("ACCESS_TOKEN");
    expect(() => createHostAccessPolicy({ ...services.settings.host, corsOrigins: ["*"] })).toThrow();
  } finally {
    server.closeAllConnections();
    await new Promise<void>(resolve => server.close(() => resolve()));
    await rm(root, { recursive: true, force: true });
  }
});
