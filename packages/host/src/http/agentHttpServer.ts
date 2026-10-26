import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import { handleAgentRoute } from "../api/agentRoutes.js";
import { fail, ok, sendJson } from "./envelope.js";
import { serveWebUi } from "./static.js";
import type { HostServices } from "../services/hostServices.js";
import { createHostAccessPolicy, corsHeaders, requestAuthorized, requestOriginAllowed, type HostAccessPolicy } from "./hostAccessPolicy.js";

export function createAgentHttpServer(services: HostServices) {
  const policy = createHostAccessPolicy(services.settings.host);
  return createServer(async (request, response) => {
    try {
      await handleRequest(services, policy, request, response);
    } catch {
      if (!response.headersSent) sendJson(response, 500, fail("500", "internal server error").body);
      else response.destroy();
    }
  });
}

async function handleRequest(services: HostServices, policy: HostAccessPolicy, request: IncomingMessage, response: ServerResponse): Promise<void> {
  if (!requestOriginAllowed(policy, request)) {
    sendJson(response, 403, fail("403", "origin or host not allowed").body);
    return;
  }
  if (!request.url?.startsWith("/") || request.url.startsWith("//")) {
    sendJson(response, 400, fail("400", "invalid request target").body);
    return;
  }
  const url = new URL(request.url || "/", services.settings.host.domain);
  const cors = corsHeaders(request);
  if (request.method === "OPTIONS") {
    response.writeHead(204, cors);
    response.end();
    return;
  }
  for (const [key, value] of Object.entries(cors)) response.setHeader(key, value);
  if (request.method === "GET" && url.pathname === "/health") {
    sendJson(response, 200, ok({ status: "ok" }));
    return;
  }
  // Static UI contains no credentials and must be reachable to enter a bearer token.
  if (request.method === "GET" && await serveWebUi(services.settings.repoRoot, url.pathname, response)) return;
  if (!requestAuthorized(policy, request)) {
    sendJson(response, 401, fail("401", "unauthorized", 401).body);
    return;
  }
  if (request.method === "POST" && url.pathname === "/callback") {
    sendJson(response, 200, ok({ status: "ok" }));
    return;
  }
  if (await handleAgentRoute(services, request.method || "GET", url, request, response)) return;
  sendJson(response, 404, fail("404", "not found", 404).body);
}
