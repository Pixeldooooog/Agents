import type { WebSearchSettings } from "../config/settings.js";
import { domainFromUrl, domainMatches, looksLikeHttpUrl, WebRequestPolicy } from "./webPolicy.js";
import { extractLinks, fetchWebResource, sourceFromFetchedResource } from "./webFetch.js";
import type { WebExtractPayload, WebExtractRequest, WebMapPayload, WebMapRequest, WebSearchPayload, WebSearchRequest, WebSource } from "./webTypes.js";

export async function localWebSearch(settings: WebSearchSettings, policy: WebRequestPolicy, request: WebSearchRequest, runId: string): Promise<WebSearchPayload> {
  if (!looksLikeHttpUrl(request.query)) throw new Error("web search provider is not configured");
  ensureRequestDomainAllowed(request.query, request.include_domains, request.exclude_domains);
  const startedAt = performance.now();
  policy.reserveCredits(runId, 1);
  const [url] = policy.validateUrls([request.query]);
  const resource = await fetchWebResource(url, 500000, settings.timeout);
  return {
    query: request.query,
    provider: "local",
    request_id: newRequestId("web_search"),
    usage: { credits: 1 },
    response_time: elapsedSeconds(startedAt),
    sources: [sourceFromFetchedResource(resource, 1, request.include_raw_content)],
    provider_answer: "",
    warnings: ["No web search provider configured; treated URL query as direct extraction."],
    cached: false
  };
}

export async function localWebExtract(settings: WebSearchSettings, policy: WebRequestPolicy, request: WebExtractRequest, runId: string): Promise<WebExtractPayload> {
  const startedAt = performance.now();
  const urls = policy.validateUrls(request.urls);
  policy.reserveCredits(runId, urls.length);
  const sources: WebSource[] = [];
  const failedResults: Record<string, unknown>[] = [];
  for (const [index, url] of urls.entries()) {
    try {
      const resource = await fetchWebResource(url, 1000000, settings.timeout);
      if (resource.status >= 400) throw new Error(`${resource.status} ${resource.statusText}`.trim());
      sources.push(sourceFromFetchedResource(resource, index + 1, false));
    } catch (error) {
      failedResults.push({ url, error: error instanceof Error ? error.message : String(error) });
    }
  }
  return {
    provider: "local",
    request_id: newRequestId("web_extract"),
    usage: { credits: urls.length },
    response_time: elapsedSeconds(startedAt),
    sources,
    failed_results: failedResults,
    warnings: settings.provider === "none" ? ["Using local fetch because web search provider is not configured."] : [],
    cached: false
  };
}

export async function localWebMap(settings: WebSearchSettings, policy: WebRequestPolicy, request: WebMapRequest, runId: string): Promise<WebMapPayload> {
  const startedAt = performance.now();
  const [rootUrl] = policy.validateUrls([request.url]);
  const includeDomains = policy.includeDomainsForRequest(request.include_domains);
  const excludeDomains = policy.excludeDomainsForRequest(request.exclude_domains);
  const limit = Math.max(1, Math.min(500, Number(request.limit || 50)));
  const maxDepth = Math.max(1, Math.min(5, Number(request.max_depth || 1)));
  policy.reserveCredits(runId, 1);
  return {
    provider: "local",
    url: rootUrl,
    request_id: newRequestId("web_map"),
    usage: { credits: 1 },
    response_time: elapsedSeconds(startedAt),
    urls: await localMapUrls(rootUrl, limit, maxDepth, includeDomains, excludeDomains, policy, settings.timeout),
    warnings: settings.provider === "none" ? ["Using local link extraction because web search provider is not configured."] : []
  };
}

async function localMapUrls(
  rootUrl: string,
  limit: number,
  maxDepth: number,
  includeDomains: string[],
  excludeDomains: string[],
  policy: WebRequestPolicy,
  timeoutSeconds: number
): Promise<string[]> {
  const rootDomain = domainFromUrl(rootUrl);
  const queue: { url: string; depth: number }[] = [{ url: rootUrl, depth: 0 }];
  const seen = new Set<string>();
  const discovered: string[] = [];
  while (queue.length && discovered.length < limit) {
    const current = queue.shift()!;
    if (seen.has(current.url)) continue;
    seen.add(current.url);
    discovered.push(current.url);
    if (current.depth >= maxDepth) continue;
    const resource = await fetchWebResource(current.url, 500000, timeoutSeconds);
    for (const link of extractLinks(resource.text, resource.finalUrl)) {
      if (seen.has(link) || discovered.length + queue.length >= limit) continue;
      if (!policy.canUseUrl(link)) continue;
      if (!mapDomainAllowed(link, rootDomain, includeDomains, excludeDomains)) continue;
      queue.push({ url: link, depth: current.depth + 1 });
    }
  }
  return discovered;
}

function ensureRequestDomainAllowed(url: string, includeDomains: string[], excludeDomains: string[]): void {
  const domain = domainFromUrl(url);
  if (includeDomains.length && !includeDomains.some((allowed) => domainMatches(domain, allowed))) {
    throw new Error(`domain is not included for this request: ${domain}`);
  }
  if (excludeDomains.some((denied) => domainMatches(domain, denied))) throw new Error(`domain is excluded for this request: ${domain}`);
}

function mapDomainAllowed(url: string, rootDomain: string, includeDomains: string[], excludeDomains: string[]): boolean {
  const domain = domainFromUrl(url);
  if (excludeDomains.some((denied) => domainMatches(domain, denied))) return false;
  if (includeDomains.length) return includeDomains.some((allowed) => domainMatches(domain, allowed));
  return domainMatches(domain, rootDomain);
}

function newRequestId(prefix: string): string {
  return `${prefix}_${crypto.randomUUID().replaceAll("-", "").slice(0, 12)}`;
}

function elapsedSeconds(startedAt: number): number {
  return Math.max(0, (performance.now() - startedAt) / 1000);
}
