import type { ServerResponse } from "node:http";
import { createMemoryRecord, memoryScopeFromSpec, memoryWithContent, normalizeMemoryScope, resolveMemory, type JsonObject } from "@kevin/core";
import type { HostServices } from "../services/hostServices.js";
import { queryNumber, queryValue, readJson } from "../http/body.js";
import { fail, ok, sendJson } from "../http/envelope.js";

export async function handleMemoryRoute(services: HostServices, method: string, url: URL, request: AsyncIterable<unknown>, response: ServerResponse): Promise<boolean> {
  const path = url.pathname;
  if (method === "POST" && path === "/api/v1/agent/memory") return addMemory(services, await readJson(request as any), response);
  if (method === "GET" && path === "/api/v1/agent/memory") return listMemory(services, url, response);
  if (method === "PATCH" && /^\/api\/v1\/agent\/memory\/[^/]+$/.test(path)) return editMemory(services, url, path.split("/").at(-1) || "", await readJson(request as any), response);
  if (method === "DELETE" && /^\/api\/v1\/agent\/memory\/[^/]+$/.test(path)) return forgetMemory(services, url, path.split("/").at(-1) || "", response);
  return false;
}

async function addMemory(services: HostServices, payload: JsonObject, response: ServerResponse): Promise<true> {
  try {
    const spec = services.runs.specFromPayload({ message: String(payload.content || ""), ...payload });
    const memory = createMemoryRecord({
      spec,
      content: requiredString(payload.content, "content"),
      scope: normalizeMemoryScope(payload.scope || "workspace"),
      metadata: { source: "api", ...stringMetadata(payload.metadata) }
    });
    sendJson(response, 200, ok({ memory: await services.store.saveMemory(memory) }));
  } catch (error) {
    sendJson(response, 400, fail("400", error instanceof Error ? error.message : String(error), 400).body);
  }
  return true;
}

async function listMemory(services: HostServices, url: URL, response: ServerResponse): Promise<true> {
  try {
    const scope = url.searchParams.get("scope") ? normalizeMemoryScope(url.searchParams.get("scope")) : "";
    const memories = await services.store.listMemories({
      ...memoryScopeFromSpec(specForUrl(services, url)),
      scope,
      query: queryValue(url, "query"),
      limit: queryNumber(url, "limit", 50)
    });
    sendJson(response, 200, ok({ memories, count: memories.length, total: memories.length }));
  } catch (error) {
    sendJson(response, 400, fail("400", error instanceof Error ? error.message : String(error), 400).body);
  }
  return true;
}

async function editMemory(services: HostServices, url: URL, memoryId: string, payload: JsonObject, response: ServerResponse): Promise<true> {
  try {
    const memory = await resolveMemoryForUrl(services, url, memoryId);
    const updatedMemory = await services.store.saveMemory(memoryWithContent(memory, requiredString(payload.content, "content")));
    sendJson(response, 200, ok({ memory: updatedMemory }));
  } catch (error) {
    const status = error instanceof Error && error.message.includes("required") ? 400 : 404;
    sendJson(response, status, fail(String(status), error instanceof Error ? error.message : String(error), status).body);
  }
  return true;
}

async function forgetMemory(services: HostServices, url: URL, memoryId: string, response: ServerResponse): Promise<true> {
  try {
    const memory = await resolveMemoryForUrl(services, url, memoryId);
    await services.store.deleteMemory(memory.memory_id);
    sendJson(response, 200, ok({ memory, forgotten: true }));
  } catch (error) {
    sendJson(response, 404, fail("404", error instanceof Error ? error.message : String(error), 404).body);
  }
  return true;
}

async function resolveMemoryForUrl(services: HostServices, url: URL, memoryId: string) {
  const memories = await services.store.listMemories({ ...memoryScopeFromSpec(specForUrl(services, url)), limit: 100 });
  return resolveMemory(memories, memoryId);
}

function specForUrl(services: HostServices, url: URL) {
  return services.runs.specFromPayload({
    message: "",
    tenant_id: queryValue(url, "tenant_id"),
    user_id: queryValue(url, "user_id"),
    agent_id: queryValue(url, "agent_id"),
    workspace_id: queryValue(url, "workspace_id")
  });
}

function requiredString(value: unknown, name: string): string {
  const text = String(value || "").trim();
  if (!text) throw new Error(`${name} is required`);
  return text;
}

function stringMetadata(value: unknown): Record<string, string> {
  if (!value || typeof value !== "object") return {};
  return Object.fromEntries(Object.entries(value).map(([key, entryValue]) => [String(key), String(entryValue)]));
}
