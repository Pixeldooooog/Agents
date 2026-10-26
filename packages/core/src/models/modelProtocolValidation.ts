import type { ToolCall } from "../types/runtimeTypes.js";
import { ModelProtocolError } from "./modelErrors.js";

export function parseProtocolJson(text: string): unknown {
  try {
    return JSON.parse(text) as unknown;
  } catch {
    // Do not expose provider bodies, tool arguments, or credentials in errors.
    throw new ModelProtocolError("model response contains invalid JSON");
  }
}

export function requireRecord(value: unknown, field: string): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new ModelProtocolError(`${field} must be an object`);
  }
  return value as Record<string, unknown>;
}

export function requireArray(value: unknown, field: string): unknown[] {
  if (!Array.isArray(value)) throw new ModelProtocolError(`${field} must be an array`);
  return value;
}

export function requireString(value: unknown, field: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new ModelProtocolError(`${field} must be a non-empty string`);
  }
  return value;
}

export function parseFunctionCall(id: unknown, name: unknown, args: unknown, encoding: "json" | "object"): ToolCall {
  const callId = requireString(id, "tool call id");
  const callName = requireString(name, "tool call name");
  const input = encoding === "json" ? parseProtocolJson(requireString(args, "tool arguments")) : args;
  return { id: callId, name: callName, arguments: requireRecord(input, "tool arguments") };
}

export function validateCallIds(calls: ToolCall[]): ToolCall[] {
  const ids = new Set<string>();
  for (const call of calls) {
    if (ids.has(call.id)) throw new ModelProtocolError("duplicate tool call id in model turn");
    ids.add(call.id);
  }
  return calls;
}
