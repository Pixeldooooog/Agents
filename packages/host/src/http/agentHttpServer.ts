import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import { handleAgentRoute } from "../api/agentRoutes.js";
import { fail, ok, sendJson } from "./envelope.js";
import { serveWebUi } from "./static.js";
import type { HostServices } from "../services/hostServices.js";

export function createAgentHttpServer(services: HostServices) {
  return createServer(async (request, response) => {
    await handleRequest(services, request, response);
  });
}

async function handleRequest(services: HostServices, request: IncomingMessage, response: ServerResponse): Promise<void> {
  const url = new URL(request.url || "/", services.settings.host.domain);
  const cors = corsHeaders(services);
  if (request.method === "OPTIONS") {
    response.writeHead(204, cors);
    response.end();
    return;
  }
  for (const [key, value] of Object.entries(cors)) response.setHeader(key, value);
  if (!authorized(services, request)) {
    sendJson(response, 401, fail("401", "unauthorized", 401).body);
    return;
  }
  if (request.method === "GET" && url.pathname === "/health") {
    sendJson(response, 200, ok({ status: "ok" }));
    return;
  }
  if (request.method === "POST" && url.pathname === "/callback") {
    sendJson(response, 200, ok({ status: "ok" }));
    return;
  }
  if (await handleAgentRoute(services, request.method || "GET", url, request, response)) return;
  if (request.method === "GET" && await serveWebUi(services.settings.repoRoot, url.pathname, response)) return;
  sendJson(response, 404, fail("404", "not found", 404).body);
}

function authorized(services: HostServices, request: IncomingMessage): boolean {
  const token = services.settings.host.accessToken;
  if (!token) return true;
  const header = request.headers.authorization || "";
  return header === `Bearer ${token}`;
}

function corsHeaders(services: HostServices): Record<string, string> {
  return {
    "Access-Control-Allow-Origin": services.settings.host.corsOrigins[0] || "*",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
    "Access-Control-Allow-Methods": "GET, POST, PATCH, DELETE, OPTIONS"
  };
}
