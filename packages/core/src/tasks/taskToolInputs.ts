import type { ToolExecutionContext } from "../tools/toolContracts.js";
import type { AgentSpec } from "../types/agentTypes.js";
import type { TaskStatus } from "../types/taskTypes.js";
import { taskStatusValues } from "./taskToolSchemas.js";

export function requiredStore(context: ToolExecutionContext) {
  if (!context.store) throw new Error("task store is not available");
  return context.store;
}

export function requiredSpec(context: ToolExecutionContext): AgentSpec {
  if (!context.spec) throw new Error("agent spec is not available");
  return context.spec;
}

export function normalizeTaskStatus(rawStatus: unknown): TaskStatus {
  const status = String(rawStatus || "").trim();
  if (taskStatusValues.includes(status as TaskStatus)) return status as TaskStatus;
  throw new Error(`unknown task status: ${status}`);
}

export function metadataPatch(existingMetadata: Record<string, string>, rawPatch: unknown): Record<string, string> | undefined {
  if (!rawPatch || typeof rawPatch !== "object") return undefined;
  const mergedMetadata = { ...existingMetadata };
  for (const [key, value] of Object.entries(rawPatch)) {
    if (value === null) delete mergedMetadata[key];
    else mergedMetadata[key] = String(value);
  }
  return mergedMetadata;
}

export function stringMetadata(rawMetadata: unknown): Record<string, string> {
  if (!rawMetadata || typeof rawMetadata !== "object") return {};
  return Object.fromEntries(Object.entries(rawMetadata).map(([key, rawValue]) => [String(key), String(rawValue)]));
}

export function requiredText(rawText: unknown, fieldName: string): string {
  const text = String(rawText || "").trim();
  if (!text) throw new Error(`${fieldName} is required`);
  return text;
}

export function optionalText(rawText: unknown): string | undefined {
  const text = String(rawText || "").trim();
  return text ? text : undefined;
}

export function boundedLimit(rawLimit: unknown, fallback: number, maximum = 100): number {
  const limit = Number(rawLimit || fallback);
  if (!Number.isFinite(limit)) return fallback;
  return Math.max(1, Math.min(maximum, limit));
}

export function truncateText(text: string, maxLength: number): string {
  return text.length <= maxLength ? text : text.slice(0, maxLength);
}
