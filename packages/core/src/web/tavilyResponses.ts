import { domainFromUrl } from "./webPolicy.js";
import type { WebSource, WebUsage } from "./webTypes.js";
import { isRecord, type TavilyPayload } from "./tavilyHttp.js";

export function sourcesFromRaw(results: unknown): WebSource[] {
  if (!Array.isArray(results)) return [];
  return results.filter(isRecord).map((item, index) => {
    const url = stringValue(item.url);
    return {
      source_id: `S${index + 1}`,
      title: stringValue(item.title) || url,
      url,
      domain: url ? domainFromUrl(url) : "",
      content: stringValue(item.content || item.raw_content),
      score: Number(item.score || 0),
      published_date: stringValue(item.published_date) || undefined,
      favicon: stringValue(item.favicon) || undefined,
      raw_content: stringValue(item.raw_content) || undefined
    };
  });
}

export function usageFromRaw(raw: TavilyPayload): WebUsage {
  const rawUsage = isRecord(raw.usage) ? raw.usage : {};
  return { credits: Number(rawUsage.credits || rawUsage.cost || 0), raw: rawUsage };
}

export function recordsFromRaw(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.filter(isRecord) : [];
}

export function stringsFromRaw(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String).filter(Boolean) : [];
}

export function warningsFromRaw(raw: TavilyPayload): string[] {
  const value = raw.warnings;
  return Array.isArray(value) ? value.map(String) : value ? [String(value)] : [];
}

export function requestId(raw: TavilyPayload): string {
  return stringValue(raw.request_id || raw.id);
}

export function responseTime(raw: TavilyPayload): number {
  return Number(raw.response_time || 0);
}

export function stringValue(value: unknown): string {
  return String(value || "");
}
