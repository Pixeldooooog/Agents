import type { WebSearchSettings } from "../config/settings.js";
import { WebRequestPolicy } from "./webPolicy.js";
import type { WebExtractPayload, WebExtractRequest, WebMapPayload, WebMapRequest, WebSearchPayload, WebSearchRequest } from "./webTypes.js";
import { postTavily, type TavilyPayload } from "./tavilyHttp.js";
import { recordsFromRaw, requestId, responseTime, sourcesFromRaw, stringValue, stringsFromRaw, usageFromRaw, warningsFromRaw } from "./tavilyResponses.js";

export async function tavilySearch(settings: WebSearchSettings, policy: WebRequestPolicy, request: WebSearchRequest, runId: string): Promise<WebSearchPayload> {
  ensureTavilyKey(settings);
  const depth = policy.validateDepth(request.search_depth, "search_depth");
  const includeRawContent = policy.validateRawContent(request.include_raw_content);
  const payload: TavilyPayload = {
    query: request.query,
    topic: request.topic || "general",
    search_depth: depth,
    max_results: policy.normalizeMaxResults(request.max_results),
    include_answer: Boolean(request.include_answer),
    include_raw_content: includeRawContent,
    include_favicon: true,
    include_usage: true
  };
  addSearchFields(payload, request, policy);
  policy.reserveCredits(runId, estimateSearchCredits(depth, includeRawContent));
  const raw = await postTavily(settings, "/search", payload);
  return {
    query: request.query,
    provider: "tavily",
    request_id: requestId(raw),
    usage: usageFromRaw(raw),
    response_time: responseTime(raw),
    sources: sourcesFromRaw(raw.results),
    provider_answer: stringValue(raw.answer),
    warnings: warningsFromRaw(raw),
    cached: false
  };
}

export async function tavilyExtract(settings: WebSearchSettings, policy: WebRequestPolicy, request: WebExtractRequest, runId: string): Promise<WebExtractPayload> {
  ensureTavilyKey(settings);
  const urls = policy.validateUrls(request.urls);
  const depth = policy.validateDepth(request.extract_depth, "extract_depth");
  const payload: TavilyPayload = {
    urls,
    extract_depth: depth,
    format: request.format || "markdown",
    include_favicon: true,
    include_usage: true
  };
  if (request.query) payload.query = request.query;
  if (request.chunks_per_source) payload.chunks_per_source = Math.max(1, Math.min(10, Number(request.chunks_per_source)));
  policy.reserveCredits(runId, estimateExtractCredits(depth, urls.length));
  const raw = await postTavily(settings, "/extract", payload);
  return {
    provider: "tavily",
    request_id: requestId(raw),
    usage: usageFromRaw(raw),
    response_time: responseTime(raw),
    sources: sourcesFromRaw(raw.results),
    failed_results: recordsFromRaw(raw.failed_results),
    warnings: warningsFromRaw(raw),
    cached: false
  };
}

export async function tavilyMap(settings: WebSearchSettings, policy: WebRequestPolicy, request: WebMapRequest, runId: string): Promise<WebMapPayload> {
  ensureTavilyKey(settings);
  const [url] = policy.validateUrls([request.url]);
  const payload: TavilyPayload = {
    url,
    max_depth: Math.max(1, Math.min(5, Number(request.max_depth || 1))),
    limit: Math.max(1, Math.min(500, Number(request.limit || 50))),
    include_usage: true
  };
  if (request.instructions) payload.instructions = request.instructions;
  const includeDomains = policy.includeDomainsForRequest(request.include_domains);
  const excludeDomains = policy.excludeDomainsForRequest(request.exclude_domains);
  if (includeDomains.length) payload.include_domains = includeDomains;
  if (excludeDomains.length) payload.exclude_domains = excludeDomains;
  policy.reserveCredits(runId, 1);
  const raw = await postTavily(settings, "/map", payload);
  return {
    provider: "tavily",
    url,
    request_id: requestId(raw),
    usage: usageFromRaw(raw),
    response_time: responseTime(raw),
    urls: stringsFromRaw(raw.results || raw.urls),
    warnings: warningsFromRaw(raw)
  };
}

function addSearchFields(payload: TavilyPayload, request: WebSearchRequest, policy: WebRequestPolicy): void {
  if (request.time_range) payload.time_range = request.time_range;
  if (request.country) payload.country = request.country;
  if (request.chunks_per_source) payload.chunks_per_source = Math.max(1, Math.min(10, Number(request.chunks_per_source)));
  const includeDomains = policy.includeDomainsForRequest(request.include_domains);
  const excludeDomains = policy.excludeDomainsForRequest(request.exclude_domains);
  if (includeDomains.length) payload.include_domains = includeDomains;
  if (excludeDomains.length) payload.exclude_domains = excludeDomains;
}

function ensureTavilyKey(settings: WebSearchSettings): void {
  if (!settings.tavilyApiKey) throw new Error("Tavily API key is not configured");
}

function estimateSearchCredits(depth: string, includeRawContent: boolean): number {
  return (depth === "advanced" ? 2 : 1) + (includeRawContent ? 1 : 0);
}

function estimateExtractCredits(depth: string, urlCount: number): number {
  return (depth === "advanced" ? 2 : 1) * Math.max(1, urlCount);
}
