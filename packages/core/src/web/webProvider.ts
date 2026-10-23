import type { WebSearchSettings } from "../config/settings.js";
import { localWebExtract, localWebMap, localWebSearch } from "./localWebProvider.js";
import { tavilyExtract, tavilyMap, tavilySearch } from "./tavilyProvider.js";
import type { WebRequestPolicy } from "./webPolicy.js";
import type { WebExtractPayload, WebExtractRequest, WebMapPayload, WebMapRequest, WebSearchPayload, WebSearchRequest } from "./webTypes.js";

export function webProviderName(settings: WebSearchSettings): string {
  return settings.provider.trim().toLowerCase();
}

export async function runWebSearch(settings: WebSearchSettings, policy: WebRequestPolicy, request: WebSearchRequest, runId: string): Promise<WebSearchPayload> {
  if (webProviderName(settings) === "tavily") return tavilySearch(settings, policy, request, runId);
  return localWebSearch(settings, policy, request, runId);
}

export async function runWebExtract(settings: WebSearchSettings, policy: WebRequestPolicy, request: WebExtractRequest, runId: string): Promise<WebExtractPayload> {
  if (webProviderName(settings) === "tavily") return tavilyExtract(settings, policy, request, runId);
  return localWebExtract(settings, policy, request, runId);
}

export async function runWebMap(settings: WebSearchSettings, policy: WebRequestPolicy, request: WebMapRequest, runId: string): Promise<WebMapPayload> {
  if (webProviderName(settings) === "tavily") return tavilyMap(settings, policy, request, runId);
  return localWebMap(settings, policy, request, runId);
}
