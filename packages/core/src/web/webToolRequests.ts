import type { JsonObject } from "../types/jsonTypes.js";
import { booleanArg, numberArg, stringArg } from "../tools/toolInputs.js";
import type { WebExtractRequest, WebMapRequest, WebSearchRequest } from "./webTypes.js";

export function searchRequest(args: JsonObject, defaultMaxResults: number): WebSearchRequest {
  return {
    query: stringArg(args.query),
    topic: stringArg(args.topic, "general"),
    search_depth: stringArg(args.search_depth, "basic"),
    max_results: Math.max(1, Math.min(10, numberArg(args.max_results, defaultMaxResults || 5))),
    time_range: stringArg(args.time_range),
    include_domains: stringListArg(args.include_domains),
    exclude_domains: stringListArg(args.exclude_domains),
    country: stringArg(args.country),
    include_answer: booleanArg(args.include_answer),
    include_raw_content: booleanArg(args.include_raw_content),
    chunks_per_source: Math.max(1, Math.min(10, numberArg(args.chunks_per_source, 3)))
  };
}

export function extractRequest(args: JsonObject): WebExtractRequest {
  const urls = stringListArg(args.urls);
  if (!urls.length) throw new Error("urls is required");
  return {
    urls,
    query: stringArg(args.query),
    extract_depth: stringArg(args.extract_depth, "basic"),
    format: stringArg(args.format, "markdown"),
    chunks_per_source: Math.max(1, Math.min(10, numberArg(args.chunks_per_source, 3)))
  };
}

export function mapRequest(args: JsonObject): WebMapRequest {
  return {
    url: stringArg(args.url),
    instructions: stringArg(args.instructions),
    max_depth: Math.max(1, Math.min(5, numberArg(args.max_depth, 1))),
    limit: Math.max(1, Math.min(500, numberArg(args.limit, 50))),
    include_domains: stringListArg(args.include_domains),
    exclude_domains: stringListArg(args.exclude_domains)
  };
}

export function stringListArg(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.map(String).map((item) => item.trim()).filter(Boolean);
  }
  return String(value || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}
