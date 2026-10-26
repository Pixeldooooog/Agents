import { validateExecutableHook } from "./runtimeHooks.js";
import type { JsonObject } from "../types/jsonTypes.js";
import type { ToolDefinition, ToolExecutionContext } from "../tools/toolContracts.js";
import { hookActions, hookEvents } from "./hookCatalog.js";
import { createHookRecord, resolveHook } from "./hookRecords.js";
import { hookScopeFromSpec } from "./hookScopes.js";

export const hookToolDefinitions: ToolDefinition[] = [
  {
    name: "hook.events",
    description: "List supported session hook events and actions.",
    risk: "low",
    parameters: { type: "object", properties: {} },
    handler: async () => ({ events: hookEvents, actions: hookActions })
  },
  {
    name: "hook.list",
    description: "List session hooks configured for the current agent session.",
    risk: "low",
    parameters: {
      type: "object",
      properties: {
        event: { type: "string", description: "Optional event filter." },
        enabled: { type: "boolean", description: "Optional enabled-state filter." },
        limit: { type: "integer", minimum: 1, maximum: 100 }
      }
    },
    handler: hookList
  },
  {
    name: "hook.add",
    description: "Add a session hook that can append request guidance, record events, or gate tool use.",
    risk: "medium",
    parameters: {
      type: "object",
      properties: {
        event: { type: "string", enum: hookEvents },
        name: { type: "string" },
        action: { type: "string", enum: hookActions },
        content: { type: "string" },
        enabled: { type: "boolean" },
        tool: { type: "string", description: "Optional tool matcher for pre/post hooks, exact name or trailing wildcard, e.g. filesystem.*." },
        metadata: { type: "object", additionalProperties: { type: "string" } }
      },
      required: ["event", "name", "action"]
    },
    handler: hookAdd
  },
  {
    name: "hook.delete",
    description: "Delete a session hook by id or short id.",
    risk: "medium",
    parameters: {
      type: "object",
      properties: {
        hook_id: { type: "string", description: "Hook id or unambiguous short id." }
      },
      required: ["hook_id"]
    },
    handler: hookDelete
  }
];

async function hookList(context: ToolExecutionContext, args: JsonObject): Promise<Record<string, unknown>> {
  const hooks = await requiredStore(context).listHooks({
    ...hookScopeFromSpec(context.spec),
    event: String(args.event || ""),
    enabled: typeof args.enabled === "boolean" ? args.enabled : undefined,
    limit: boundedLimit(args.limit)
  });
  return { hooks, count: hooks.length };
}

async function hookAdd(context: ToolExecutionContext, args: JsonObject): Promise<Record<string, unknown>> {
  const hook = createHookRecord({
    spec: context.spec,
    event: args.event,
    name: args.name,
    action: args.action,
    content: args.content,
    enabled: args.enabled,
    tool: args.tool,
    metadata: { source: "tool", ...stringMetadata(args.metadata) }
  });
  validateExecutableHook(hook);
  return { hook: await requiredStore(context).saveHook(hook) };
}

async function hookDelete(context: ToolExecutionContext, args: JsonObject): Promise<Record<string, unknown>> {
  const hooks = await requiredStore(context).listHooks({ ...hookScopeFromSpec(context.spec), limit: 100 });
  const hook = resolveHook(hooks, requiredText(args.hook_id, "hook_id"));
  await requiredStore(context).deleteHook(hook.hook_id);
  return { hook, deleted: true };
}

function requiredStore(context: ToolExecutionContext) {
  if (!context.store) throw new Error("hook store is not available");
  return context.store;
}

function requiredText(value: unknown, name: string): string {
  const text = String(value || "").trim();
  if (!text) throw new Error(`${name} is required`);
  return text;
}

function stringMetadata(value: unknown): Record<string, string> {
  if (!value || typeof value !== "object") return {};
  return Object.fromEntries(Object.entries(value).map(([key, entryValue]) => [String(key), String(entryValue)]));
}

function boundedLimit(value: unknown): number {
  const limit = Number(value || 50);
  if (!Number.isFinite(limit)) return 50;
  return Math.max(1, Math.min(100, limit));
}
