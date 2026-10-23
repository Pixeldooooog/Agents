import type { Settings } from "../config/settings.js";
import { combineModelUsage, modelUsageFromPayload, modelUsagePayload } from "../models/modelUsage.js";
import type { JsonStateStore } from "../store/jsonStateStore.js";
import type { ModelUsage } from "../types/modelTypes.js";
import type { RunRecord, RuntimeEvent } from "../types/runtimeTypes.js";
import { listSdkSessionRuns } from "./sdkSessionRecords.js";

export type SdkContextUsageOptions = {
  sessionId?: string;
  model?: string;
};

export type SdkContextUsageInput = {
  settings: Settings;
  store: JsonStateStore;
  options: SdkContextUsageOptions;
};

type UsageItem = {
  category: UsageCategoryName;
  label: string;
  text: string;
  runId?: string;
};

type UsageCategoryName = "system" | "user" | "assistant" | "tool_calls" | "tool_results";

type UsageCategorySummary = {
  name: UsageCategoryName;
  label: string;
  tokens: number;
  characters: number;
  items: number;
  runs: string[];
};

export async function sdkContextUsagePayload(input: SdkContextUsageInput): Promise<Record<string, unknown>> {
  const runs = await contextRuns(input.store, input.options.sessionId);
  const items = runs.flatMap(usageItemsForRun);
  const categories = categoryUsage(items);
  const totalTokens = categories.reduce((total, category) => total + category.tokens, 0);
  const maxTokens = input.settings.agent.maxTokens;
  const apiUsage = apiUsageFromRuns(runs);
  return {
    categories,
    totalTokens,
    maxTokens,
    rawMaxTokens: maxTokens,
    percentage: maxTokens > 0 ? Math.min(100, Math.round((totalTokens / maxTokens) * 1000) / 10) : 0,
    gridRows: categories.map((category) => ({
      type: category.name,
      label: category.label,
      tokens: category.tokens,
      characters: category.characters,
      items: category.items
    })),
    model: input.options.model || latestModel(runs),
    memoryFiles: [],
    mcpTools: [],
    isAutoCompactEnabled: true,
    agents: [],
    apiUsage: modelUsagePayload(apiUsage) || null,
    estimated: true,
    source: "sdk_session_events",
    sessionId: input.options.sessionId || "",
    runCount: runs.length,
    messageCount: items.filter((item) => item.category === "user" || item.category === "assistant").length,
    toolCallCount: items.filter((item) => item.category === "tool_calls").length,
    toolResultCount: items.filter((item) => item.category === "tool_results").length
  };
}

async function contextRuns(store: JsonStateStore, sessionId = ""): Promise<RunRecord[]> {
  if (!sessionId.trim()) return [];
  return (await listSdkSessionRuns(store, sessionId)).sort((left, right) => left.created_at - right.created_at);
}

function usageItemsForRun(run: RunRecord): UsageItem[] {
  const items: UsageItem[] = [];
  const systemPrompt = run.spec.system_prompt;
  if (systemPrompt) items.push({ category: "system", label: "System prompt", text: systemPrompt, runId: run.run_id });
  const prompt = String(run.metadata.sdk_prompt || run.metadata.first_prompt || run.metadata.prompt || "");
  if (prompt) items.push({ category: "user", label: "User message", text: prompt, runId: run.run_id });
  for (const event of run.events) items.push(...usageItemsForEvent(run.run_id, event));
  return items;
}

function usageItemsForEvent(runId: string, event: RuntimeEvent): UsageItem[] {
  if (event.type === "model_message") {
    const content = stringValue(event.payload?.content);
    return content ? [{ category: "assistant", label: "Assistant message", text: content, runId }] : [];
  }
  if (event.type === "tool_start") {
    const toolName = stringValue(event.payload?.name || event.name);
    const args = event.payload?.arguments;
    return [{
      category: "tool_calls",
      label: toolName ? `Tool call: ${toolName}` : "Tool call",
      text: stringifyForUsage(args),
      runId
    }];
  }
  if (event.type === "tool_result") {
    const toolName = stringValue(event.payload?.name || event.name);
    return [{
      category: "tool_results",
      label: toolName ? `Tool result: ${toolName}` : "Tool result",
      text: stringValue(event.payload?.content),
      runId
    }];
  }
  return [];
}

function apiUsageFromRuns(runs: RunRecord[]): ModelUsage | undefined {
  return combineModelUsage(runs.map(apiUsageForRun));
}

function apiUsageForRun(run: RunRecord): ModelUsage | undefined {
  const doneUsage = [...run.events]
    .reverse()
    .find((event) => event.type === "done")
    ?.payload?.modelUsage;
  const parsedDoneUsage = modelUsageFromPayload(doneUsage);
  if (parsedDoneUsage) return parsedDoneUsage;
  return combineModelUsage(run.events
    .filter((event) => event.type === "model_message")
    .map((event) => modelUsageFromPayload(event.payload?.modelUsage)));
}

function categoryUsage(items: UsageItem[]): UsageCategorySummary[] {
  const grouped = new Map<UsageCategoryName, UsageItem[]>();
  for (const item of items) grouped.set(item.category, [...(grouped.get(item.category) || []), item]);
  return categoryOrder()
    .map((category) => usageCategory(category, grouped.get(category) || []))
    .filter((category) => category.items > 0);
}

function usageCategory(category: UsageCategoryName, items: UsageItem[]): UsageCategorySummary {
  const characters = items.reduce((total, item) => total + item.text.length, 0);
  return {
    name: category,
    label: categoryLabel(category),
    tokens: approximateTokenCount(items.map((item) => item.text).join("\n")),
    characters,
    items: items.length,
    runs: [...new Set(items.flatMap((item) => item.runId ? [item.runId] : []))]
  };
}

function categoryOrder(): UsageCategoryName[] {
  return ["system", "user", "assistant", "tool_calls", "tool_results"];
}

function categoryLabel(category: UsageCategoryName): string {
  switch (category) {
    case "system":
      return "System";
    case "user":
      return "User";
    case "assistant":
      return "Assistant";
    case "tool_calls":
      return "Tool calls";
    case "tool_results":
      return "Tool results";
  }
}

function approximateTokenCount(text: string): number {
  if (!text) return 0;
  return Math.max(1, Math.ceil(Buffer.byteLength(text, "utf8") / 4));
}

function latestModel(runs: RunRecord[]): string {
  return runs.at(-1)?.spec.model || "";
}

function stringValue(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function stringifyForUsage(value: unknown): string {
  if (value === undefined) return "";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}
