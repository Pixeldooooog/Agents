import type { Message } from "../types/runtimeTypes.js";

/** Validate replay data at the persistence boundary, including complete tool-call groups. */
export function conversationHistory(value: unknown): Message[] {
  if (!Array.isArray(value) || value.length > 10000) throw new Error("invalid conversation history");
  const pending = new Set<string>();
  for (const item of value) {
    if (!record(item) || !["system", "user", "assistant", "tool"].includes(String(item.role)) || typeof item.content !== "string") throw new Error("invalid conversation message");
    if (item.name !== undefined && typeof item.name !== "string") throw new Error("invalid message name");
    if (item.role === "tool") {
      if (typeof item.tool_call_id !== "string" || !pending.delete(item.tool_call_id)) throw new Error("orphaned tool result");
    } else if (pending.size) throw new Error("incomplete tool-call group");
    if (item.tool_calls !== undefined) {
      if (item.role !== "assistant" || !Array.isArray(item.tool_calls)) throw new Error("invalid tool calls");
      for (const call of item.tool_calls) {
        if (!record(call) || typeof call.id !== "string" || !call.id || typeof call.name !== "string" || !call.name || !record(call.arguments) || pending.has(call.id)) throw new Error("invalid tool call");
        pending.add(call.id);
      }
    }
    if (item.model_context !== undefined) {
      const native = item.model_context;
      if (item.role !== "assistant" || !record(native) || !["openai-responses", "claude-messages"].includes(String(native.protocol)) || typeof native.model !== "string" || typeof native.baseUrl !== "string" || !Array.isArray(native.items) || !native.items.every(record)) throw new Error("invalid native context");
    }
  }
  if (pending.size) throw new Error("incomplete tool-call group");
  return value as Message[];
}

function record(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object" && !Array.isArray(value);
}
