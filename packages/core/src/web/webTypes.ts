export type WebUsage = {
  credits: number;
  raw?: Record<string, unknown>;
};

export type WebSource = {
  source_id: string;
  title: string;
  url: string;
  domain: string;
  content: string;
  score: number;
  published_date?: string;
  favicon?: string;
  raw_content?: string;
};

export type WebSearchRequest = {
  query: string;
  topic: string;
  search_depth: string;
  max_results: number;
  time_range: string;
  include_domains: string[];
  exclude_domains: string[];
  country: string;
  include_answer: boolean;
  include_raw_content: boolean;
  chunks_per_source: number;
};

export type WebSearchPayload = {
  query: string;
  provider: string;
  request_id: string;
  usage: WebUsage;
  response_time: number;
  sources: WebSource[];
  provider_answer: string;
  warnings: string[];
  cached: boolean;
};

export type WebExtractRequest = {
  urls: string[];
  query: string;
  extract_depth: string;
  format: "markdown" | "text" | string;
  chunks_per_source: number;
};

export type WebExtractPayload = {
  provider: string;
  request_id: string;
  usage: WebUsage;
  response_time: number;
  sources: WebSource[];
  failed_results: Record<string, unknown>[];
  warnings: string[];
  cached: boolean;
};

export type WebMapRequest = {
  url: string;
  instructions: string;
  max_depth: number;
  limit: number;
  include_domains: string[];
  exclude_domains: string[];
};

export type WebMapPayload = {
  provider: string;
  url: string;
  request_id: string;
  usage: WebUsage;
  response_time: number;
  urls: string[];
  warnings: string[];
};

export type FetchedWebResource = {
  url: string;
  finalUrl: string;
  status: number;
  statusText: string;
  contentType: string;
  bytes: number;
  truncated: boolean;
  body: Buffer;
  text: string;
};
