import type { JsonObject } from "../types/jsonTypes.js";
import type { ModelUsage } from "../types/modelTypes.js";

export function modelUsageFromOpenAIChat(raw: unknown): ModelUsage | undefined {
  const usage = objectValue(raw);
  if (!Object.keys(usage).length) return undefined;
  return compactModelUsage({
    inputTokens: integerValue(usage.prompt_tokens),
    outputTokens: integerValue(usage.completion_tokens),
    totalTokens: integerValue(usage.total_tokens),
    raw: usage
  });
}

export function modelUsageFromOpenAIResponses(raw: unknown): ModelUsage | undefined {
  const usage = objectValue(raw);
  if (!Object.keys(usage).length) return undefined;
  const inputTokens = integerValue(usage.input_tokens);
  const outputTokens = integerValue(usage.output_tokens);
  return compactModelUsage({
    inputTokens,
    outputTokens,
    totalTokens: integerValue(usage.total_tokens, inputTokens + outputTokens),
    raw: usage
  });
}

export function modelUsageFromClaude(raw: unknown): ModelUsage | undefined {
  const usage = objectValue(raw);
  if (!Object.keys(usage).length) return undefined;
  const inputTokens = integerValue(usage.input_tokens);
  const outputTokens = integerValue(usage.output_tokens);
  return compactModelUsage({
    inputTokens,
    outputTokens,
    totalTokens: inputTokens + outputTokens,
    raw: usage
  });
}

export function modelUsageFromGemini(raw: unknown): ModelUsage | undefined {
  const usage = objectValue(raw);
  if (!Object.keys(usage).length) return undefined;
  return compactModelUsage({
    inputTokens: integerValue(usage.promptTokenCount),
    outputTokens: integerValue(usage.candidatesTokenCount),
    totalTokens: integerValue(usage.totalTokenCount),
    raw: usage
  });
}

export function modelUsageFromPayload(rawPayload: unknown): ModelUsage | undefined {
  const usage = objectValue(rawPayload);
  if (!Object.keys(usage).length) return undefined;
  const inputTokens = integerValue(usage.inputTokens ?? usage.input_tokens);
  const outputTokens = integerValue(usage.outputTokens ?? usage.output_tokens);
  const totalTokens = integerValue(usage.totalTokens ?? usage.total_tokens, inputTokens + outputTokens);
  if (!inputTokens && !outputTokens && !totalTokens) return undefined;
  const rawUsage = objectValue(usage.raw);
  return {
    inputTokens,
    outputTokens,
    totalTokens,
    ...(Object.keys(rawUsage).length ? { raw: rawUsage } : {})
  };
}

export function combineModelUsage(usages: Array<ModelUsage | undefined>): ModelUsage | undefined {
  const present = usages.filter((usage): usage is ModelUsage => Boolean(usage));
  if (!present.length) return undefined;
  return {
    inputTokens: present.reduce((total, usage) => total + usage.inputTokens, 0),
    outputTokens: present.reduce((total, usage) => total + usage.outputTokens, 0),
    totalTokens: present.reduce((total, usage) => total + usage.totalTokens, 0)
  };
}

export function modelUsagePayload(usage: ModelUsage | undefined): Record<string, unknown> | undefined {
  if (!usage) return undefined;
  return {
    inputTokens: usage.inputTokens,
    outputTokens: usage.outputTokens,
    totalTokens: usage.totalTokens,
    input_tokens: usage.inputTokens,
    output_tokens: usage.outputTokens,
    total_tokens: usage.totalTokens,
    ...(usage.raw ? { raw: usage.raw } : {})
  };
}

function compactModelUsage(usage: ModelUsage): ModelUsage {
  return {
    inputTokens: Math.max(0, usage.inputTokens),
    outputTokens: Math.max(0, usage.outputTokens),
    totalTokens: Math.max(0, usage.totalTokens || usage.inputTokens + usage.outputTokens),
    raw: usage.raw
  };
}

function integerValue(value: unknown, fallback = 0): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.max(0, Math.trunc(parsed)) : fallback;
}

function objectValue(value: unknown): JsonObject {
  return value && typeof value === "object" && !Array.isArray(value) ? value as JsonObject : {};
}
