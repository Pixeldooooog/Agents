export const webSearchSchema = {
  type: "object",
  properties: {
    query: { type: "string", description: "Search query." },
    topic: { type: "string", enum: ["general", "news", "finance"] },
    search_depth: { type: "string", enum: ["basic", "advanced", "fast", "ultra_fast"] },
    max_results: { type: "integer", minimum: 1, maximum: 10 },
    time_range: { type: "string" },
    include_domains: { type: "array", items: { type: "string" } },
    exclude_domains: { type: "array", items: { type: "string" } },
    country: { type: "string" },
    include_answer: { type: "boolean" },
    include_raw_content: { type: "boolean" },
    chunks_per_source: { type: "integer", minimum: 1, maximum: 10 }
  },
  required: ["query"]
};

export const webExtractSchema = {
  type: "object",
  properties: {
    urls: { type: "array", items: { type: "string" } },
    query: { type: "string" },
    extract_depth: { type: "string", enum: ["basic", "advanced"] },
    format: { type: "string", enum: ["markdown", "text"] },
    chunks_per_source: { type: "integer", minimum: 1, maximum: 10 }
  },
  required: ["urls"]
};

export const webMapSchema = {
  type: "object",
  properties: {
    url: { type: "string" },
    instructions: { type: "string" },
    max_depth: { type: "integer", minimum: 1, maximum: 5 },
    limit: { type: "integer", minimum: 1, maximum: 500 },
    include_domains: { type: "array", items: { type: "string" } },
    exclude_domains: { type: "array", items: { type: "string" } }
  },
  required: ["url"]
};
