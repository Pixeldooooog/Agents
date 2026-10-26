import type { AgentSpec } from "../types/agentTypes.js";
import type { JsonObject } from "../types/jsonTypes.js";
import type { MemoryRecord } from "../types/memoryTypes.js";
import { defineTool, type RegisteredTool, type ToolContext } from "../tools/toolContracts.js";

type MemoryToolContext = ToolContext<"store">;
import { createMemoryRecord, memoryScopeFromSpec, memoryWithContent, normalizeMemoryScope, requiredText, resolveMemory, stringRecord } from "./memoryRecords.js";

const memoryScopeValues = ["user", "agent", "workspace", "run"];

const memoryListSchema = {
  type: "object",
  properties: {
    scope: { type: "string", enum: ["", ...memoryScopeValues], description: "Optional scope filter." },
    query: { type: "string", description: "Optional content substring filter." },
    limit: { type: "integer", minimum: 1, maximum: 100 }
  }
};

const memoryAddSchema = {
  type: "object",
  properties: {
    content: { type: "string" },
    scope: { type: "string", enum: memoryScopeValues },
    metadata: { type: "object", additionalProperties: { type: "string" } }
  },
  required: ["content"]
};

const memoryEditSchema = {
  type: "object",
  properties: {
    memory_id: { type: "string", description: "Memory id or unambiguous short id." },
    content: { type: "string" }
  },
  required: ["memory_id", "content"]
};

const memoryForgetSchema = {
  type: "object",
  properties: {
    memory_id: { type: "string", description: "Memory id or unambiguous short id." }
  },
  required: ["memory_id"]
};

export const memoryToolDefinitions: RegisteredTool[] = [
  defineTool({
    name: "memory.list",
    description: "List memories visible to the current user, agent, and workspace scope.",
    risk: "low",
    parameters: memoryListSchema,
    requires: ["store"],
    handler: memoryList
  }),
  defineTool({
    name: "memory.add",
    description: "Save a memory for future context retrieval.",
    risk: "medium",
    parameters: memoryAddSchema,
    requires: ["store"],
    handler: memoryAdd
  }),
  defineTool({
    name: "memory.edit",
    description: "Update a visible memory by id or short id.",
    risk: "medium",
    parameters: memoryEditSchema,
    requires: ["store"],
    handler: memoryEdit
  }),
  defineTool({
    name: "memory.forget",
    description: "Delete a visible memory by id or short id.",
    risk: "medium",
    parameters: memoryForgetSchema,
    requires: ["store"],
    handler: memoryForget
  })
];

async function memoryList(context: MemoryToolContext, args: JsonObject = {}): Promise<Record<string, unknown>> {
  const scope = args.scope ? normalizeMemoryScope(args.scope) : "";
  const memories = await context.store.listMemories({
    ...memoryScopeFromSpec(context.spec),
    scope,
    query: String(args.query || ""),
    limit: boundedLimit(args.limit)
  });
  return { memories, count: memories.length, total: memories.length };
}

async function memoryAdd(context: MemoryToolContext, args: JsonObject): Promise<Record<string, unknown>> {
  const memory = createMemoryRecord({
    spec: requiredSpec(context),
    content: requiredText(args.content, "content"),
    scope: normalizeMemoryScope(args.scope || "workspace"),
    metadata: { source: "tool", ...stringRecord(args.metadata) },
    runId: context.runId
  });
  return { memory: await context.store.saveMemory(memory) };
}

async function memoryEdit(context: MemoryToolContext, args: JsonObject): Promise<Record<string, unknown>> {
  const memory = await resolveScopedMemory(context, requiredText(args.memory_id, "memory_id"));
  const updatedMemory = await context.store.saveMemory(memoryWithContent(memory, requiredText(args.content, "content")));
  return { memory: updatedMemory };
}

async function memoryForget(context: MemoryToolContext, args: JsonObject): Promise<Record<string, unknown>> {
  const memory = await resolveScopedMemory(context, requiredText(args.memory_id, "memory_id"));
  await context.store.deleteMemory(memory.memory_id);
  return { memory, forgotten: true };
}

async function resolveScopedMemory(context: MemoryToolContext, memoryId: string): Promise<MemoryRecord> {
  const memories = await context.store.listMemories({ ...memoryScopeFromSpec(context.spec), limit: 100 });
  return resolveMemory(memories, memoryId);
}


function requiredSpec(context: MemoryToolContext): AgentSpec {
  if (!context.spec) throw new Error("agent spec is not available");
  return context.spec;
}

function boundedLimit(value: unknown): number {
  const limit = Number(value || 50);
  return Number.isFinite(limit) ? Math.max(1, Math.min(100, limit)) : 50;
}
