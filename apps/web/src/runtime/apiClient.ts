import { apiEnvelope, chatResponse, runListResponse, traceResponse, profilesResponse, taskResponse, taskListResponse, taskDetailResponse, taskRunResponse, healthResponse, eventResponse } from "./apiValidation";
import type {
  AgentChatPayload,
  RunApprovalPayload,
  SseEventFrame,
  TaskCreatePayload
} from "../types/runtimeTypes";

type AuthConfig = {
  baseUrl: () => string;
  token: () => string;
};

type StreamHandler = (frame: SseEventFrame) => void;

export function createApiClient(config: AuthConfig) {
  const jsonHeaders = () => {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    const token = config.token().trim();
    if (token) headers.Authorization = `Bearer ${token}`;
    return headers;
  };

  const authHeaders = (): Record<string, string> => {
    const headers: Record<string, string> = {};
    const token = config.token().trim();
    if (token) headers.Authorization = `Bearer ${token}`;
    return headers;
  };

  return {
    chat(payload: AgentChatPayload, signal?: AbortSignal) {
      return request(chatResponse, "/api/v1/agent/chat", { method: "POST", headers: jsonHeaders(), body: JSON.stringify(payload), signal });
    },
    approve(runId: string, payload: RunApprovalPayload, signal?: AbortSignal) {
      return request(chatResponse, `/api/v1/agent/runs/${runId}/approval`, { method: "POST", headers: jsonHeaders(), body: JSON.stringify(payload), signal });
    },
    async chatStream(payload: AgentChatPayload, onEvent: StreamHandler, signal?: AbortSignal) {
      const response = await fetch(urlFor("/api/v1/agent/chat/stream"), {
        method: "POST",
        headers: jsonHeaders(),
        body: JSON.stringify(payload),
        signal,
      });
      if (!response.ok || !response.body) {
        throw new Error(`stream request failed: ${response.status} ${response.statusText}`);
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8", { fatal: true });
      let buffer = "";
      let completed = false;
      const receive: StreamHandler = frame => {
        if (completed) throw new Error("runtime event after completion");
        if (frame.payload.type !== frame.event) throw new Error("runtime event type mismatch");
        if (frame.event === "done") {
          if (typeof frame.payload.payload?.status !== "string" || typeof frame.payload.payload?.content !== "string") throw new Error("invalid completion event");
          completed = true;
        }
        onEvent(frame);
      };
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          if (buffer.length > 2 * 1024 * 1024) throw new Error("runtime event exceeds 2 MiB");
          buffer = emitFrames(buffer, receive);
        }
        buffer += decoder.decode();
        if (buffer.trim()) throw new Error("incomplete runtime event");
        if (!completed) throw new Error("runtime stream ended before completion");
      } finally { await reader.cancel().catch(() => {}); reader.releaseLock(); }
    },
    health() {
      return request(healthResponse, "/health", { method: "GET", headers: authHeaders() });
    },
    runTrace(runId: string) {
      return request(traceResponse, `/api/v1/agent/runs/${runId}/trace`, { method: "GET", headers: authHeaders() });
    },
    runs(query: { limit?: number; tenant_id?: string; user_id?: string; agent_id?: string } = {}) {
      const search = new URLSearchParams();
      if (query.limit) search.set("limit", String(query.limit));
      if (query.tenant_id) search.set("tenant_id", query.tenant_id);
      if (query.user_id) search.set("user_id", query.user_id);
      if (query.agent_id) search.set("agent_id", query.agent_id);
      const suffix = search.toString() ? `?${search}` : "";
      return request(runListResponse, `/api/v1/agent/runs${suffix}`, { method: "GET", headers: authHeaders() });
    },
    modelProfiles() {
      return request(profilesResponse, "/api/v1/agent/model-profiles", { method: "GET", headers: authHeaders() });
    },
    createTask(payload: TaskCreatePayload) {
      return request(taskResponse, "/api/v1/agent/tasks", { method: "POST", headers: jsonHeaders(), body: JSON.stringify(payload) });
    },
    tasks(query: { tenant_id?: string; user_id?: string; agent_id?: string } = {}) {
      const search = new URLSearchParams();
      if (query.tenant_id) search.set("tenant_id", query.tenant_id);
      if (query.user_id) search.set("user_id", query.user_id);
      if (query.agent_id) search.set("agent_id", query.agent_id);
      const suffix = search.toString() ? `?${search}` : "";
      return request(taskListResponse, `/api/v1/agent/tasks${suffix}`, { method: "GET", headers: authHeaders() });
    },
    task(taskId: string) {
      return request(taskDetailResponse, `/api/v1/agent/tasks/${taskId}`, { method: "GET", headers: authHeaders() });
    },
    runTask(taskId: string) {
      return request(taskRunResponse, `/api/v1/agent/tasks/${taskId}/run`, { method: "POST", headers: authHeaders() });
    },
    cancelTask(taskId: string) {
      return request(taskResponse, `/api/v1/agent/tasks/${taskId}/cancel`, { method: "POST", headers: authHeaders() });
    },
  };

  function urlFor(path: string) {
    return `${config.baseUrl().replace(/\/$/, "")}${path}`;
  }

  async function request<T>(decode: (value: unknown) => T, path: string, init: RequestInit): Promise<T> {
    const response = await fetch(urlFor(path), init);
    let envelope: unknown;
    try { envelope = await response.json(); }
    catch { throw new Error("invalid API response JSON"); }
    return decode(apiEnvelope(envelope, response.ok));
  }
}

function emitFrames(buffer: string, onEvent: StreamHandler): string {
  const chunks = buffer.split("\n\n");
  const rest = chunks.pop() ?? "";
  for (const chunk of chunks) {
    const lines = chunk.split("\n");
    const event = lines.find((line) => line.startsWith("event: "))?.slice(7).trim() || "message";
    const data = lines
      .filter((line) => line.startsWith("data: "))
      .map((line) => line.slice(6))
      .join("\n");
    onEvent({ event, data, payload: eventResponse(JSON.parse(data)) });
  }
  return rest;
}
