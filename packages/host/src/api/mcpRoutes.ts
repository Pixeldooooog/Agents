import type { ServerResponse } from "node:http";
import type { HostServices } from "../services/hostServices.js";
import { fail, ok, sendJson } from "../http/envelope.js";

export async function handleMcpRoute(services: HostServices, method: string, url: URL, _request: AsyncIterable<unknown>, response: ServerResponse): Promise<boolean> {
  if (method === "GET" && url.pathname === "/api/v1/agent/mcp") {
    sendJson(response, 200, ok({ servers: services.mcp.status() }));
    return true;
  }
  const match = url.pathname.match(/^\/api\/v1\/agent\/mcp\/([^/]+)\/reconnect$/);
  if (method !== "POST" || !match) return false;
  const controller = new AbortController();
  const cancel = () => controller.abort();
  response.on("close", cancel);
  try {
    await services.mcp.reconnect(decodeURIComponent(match[1]), controller.signal);
    sendJson(response, 200, ok({ servers: services.mcp.status() }));
  } catch (error) {
    sendJson(response, 400, fail("mcp_connection_failed", error instanceof Error ? error.message : "MCP connection failed", 400).body);
  } finally { response.off("close", cancel); }
  return true;
}
