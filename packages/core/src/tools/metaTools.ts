import type { JsonObject } from "../types/jsonTypes.js";
import type { ToolDefinition, ToolExecutionContext } from "./toolContracts.js";
import { booleanArg, numberArg, stringArg } from "./toolInputs.js";

const toolSearchSchema = {
  type: "object",
  properties: {
    query: { type: "string", description: "Tool name or keyword query. Use select:<tool> for exact lookup." },
    max_results: { type: "integer", minimum: 1, maximum: 50 },
    include_all: { type: "boolean", description: "Include registered tools that are not enabled for this session." }
  }
};

export function createMetaToolDefinitions(toolCatalog: () => ToolDefinition[]): ToolDefinition[] {
  return [
    {
      name: "tool.search",
      description: "Search registered tools by name, description, or exact select:<tool> lookup.",
      risk: "low",
      parameters: toolSearchSchema,
      handler: (context, args) => toolSearch(context, args, toolCatalog())
    }
  ];
}

async function toolSearch(context: ToolExecutionContext, args: JsonObject, tools: ToolDefinition[]) {
  const query = stringArg(args.query);
  const enabled = new Set(context.spec?.enabled_tools || []);
  const includeAll = booleanArg(args.include_all);
  const candidates = includeAll || !enabled.size ? tools : tools.filter((tool) => enabled.has(tool.name));
  const matches = rankedToolMatches(candidates, query, numberArg(args.max_results, 20), enabled);
  return {
    query,
    matches,
    count: matches.length,
    total_registered_tools: tools.length,
    total_enabled_tools: enabled.size
  };
}

function rankedToolMatches(tools: ToolDefinition[], query: string, maxResults: number, enabled: Set<string>) {
  const terms = queryTerms(query);
  const exact = selectExact(query);
  return tools
    .flatMap((tool) => {
      const score = scoreTool(tool.name, [tool.name, tool.description].join(" "), terms, exact);
      return score > 0 || (!terms.length && !exact) ? [{ score, tool }] : [];
    })
    .sort((left, right) => right.score - left.score || left.tool.name.localeCompare(right.tool.name))
    .slice(0, limit(maxResults))
    .map(({ tool }) => ({
      name: tool.name,
      description: tool.description,
      enabled: enabled.has(tool.name),
      risk: tool.risk
    }));
}

function scoreTool(name: string, haystack: string, terms: string[], exact: string): number {
  const normalizedName = name.toLowerCase();
  const normalizedHaystack = haystack.toLowerCase();
  if (exact) return normalizedName === exact || normalizedName.endsWith(exact) ? 1000 : 0;
  if (!terms.length) return 1;
  return terms.reduce((score, term) => {
    if (term === normalizedName) return score + 100;
    if (normalizedName.includes(term)) return score + 25;
    if (normalizedHaystack.includes(term)) return score + 5;
    return score;
  }, 0);
}

function queryTerms(query: string): string[] {
  const value = query.trim().toLowerCase();
  if (value.startsWith("select:")) return [];
  return value.replace(/[._-]/g, " ").split(/\s+/).filter(Boolean);
}

function selectExact(query: string): string {
  const value = query.trim().toLowerCase();
  return value.startsWith("select:") ? value.slice("select:".length).trim() : "";
}

function limit(value: number): number {
  return Math.max(1, Math.min(value || 20, 50));
}
