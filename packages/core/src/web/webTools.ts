import type { JsonObject } from "../types/jsonTypes.js";
import { defineTool, type RegisteredTool, type ToolContext } from "../tools/toolContracts.js";
import { WebRequestPolicy, webSettingsForContext } from "./webPolicy.js";
import { runWebExtract, runWebMap, runWebSearch } from "./webProvider.js";
import { extractRequest, mapRequest, searchRequest } from "./webToolRequests.js";
import {
  webExtractSchema,
  webMapSchema,
  webSearchSchema
} from "./webToolSchemas.js";

export const webToolDefinitions: RegisteredTool[] = [
  defineTool({
    name: "web.search",
    description: "Search the web through the configured search provider and return cited sources.",
    risk: "medium",
    parameters: webSearchSchema,
    requires: [],
    uses: ["settings"],
    handler: webSearch
  }),
  defineTool({
    name: "web.extract",
    description: "Extract clean content from specific URLs.",
    risk: "medium",
    parameters: webExtractSchema,
    requires: [],
    uses: ["settings"],
    handler: webExtract
  }),
  defineTool({
    name: "web.map",
    description: "Discover URLs under a site.",
    risk: "high",
    parameters: webMapSchema,
    requires: [],
    uses: ["settings"],
    handler: webMap
  })
];

async function webSearch(context: ToolContext<never, "settings">, args: JsonObject) {
  const runtime = webRuntime(context);
  return runWebSearch(
    runtime.settings,
    runtime.policy,
    searchRequest(args, runtime.settings.maxResults),
    context.runId || ""
  );
}

async function webExtract(context: ToolContext<never, "settings">, args: JsonObject) {
  const runtime = webRuntime(context);
  return runWebExtract(runtime.settings, runtime.policy, extractRequest(args), context.runId || "");
}

async function webMap(context: ToolContext<never, "settings">, args: JsonObject) {
  const runtime = webRuntime(context);
  return runWebMap(runtime.settings, runtime.policy, mapRequest(args), context.runId || "");
}

function webRuntime(context: ToolContext<never, "settings">) {
  const settings = webSettingsForContext(context);
  return { settings, policy: new WebRequestPolicy(settings) };
}
