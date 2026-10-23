import type { AgentSpec } from "../types/agentTypes.js";
import type { JsonObject } from "../types/jsonTypes.js";
import type { MemoryRecord } from "../types/memoryTypes.js";
import type { ToolDefinition, ToolExecutionContext } from "../tools/toolContracts.js";
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

export const memoryToolDefinitions: ToolDefinition[] = [
  {
    name: "memory.list",
    description: "List memories visible to the current user, agent, and workspace scope.",
    risk: "low",
    parameters: memoryListSchema,
    handler: memoryList
  },
  {
    name: "memory.add",
    description: "Save a memory for future context retrieval.",
    risk: "medium",
    parameters: memoryAddSchema,
    handler: memoryAdd
  },
  {
    name: "memory.edit",
    description: "Update a visible memory by id or short id.",
    risk: "medium",
    parameters: memoryEditSchema,
    handler: memoryEdit
  },
  {
    name: "memory.forget",
    description: "Delete a visible memory by id or short id.",
    risk: "medium",
    parameters: memoryForgetSchema,
    handler: memoryForget
  }
];

async function memoryList(context: ToolExecutionContext, args: JsonObject = {}): Promise<Record<string, unknown>> {
  const scope = args.scope ? normalizeMemoryScope(args.scope) : "";
  const memories = await requiredStore(context).listMemories({
    ...memoryScopeFromSpec(context.spec),
    scope,
    query: String(args.query || ""),
    limit: boundedLimit(args.limit)
  });
  return { memories, count: memories.length, total: memories.length };
}

async function memoryAdd(context: ToolExecutionContext, args: JsonObject): Promise<Record<string, unknown>> {
  const memory = createMemoryRecord({
    spec: requiredSpec(context),
    content: requiredText(args.content, "content"),
    scope: normalizeMemoryScope(args.scope || "workspace"),
    metadata: { source: "tool", ...stringRecord(args.metadata) },
    runId: context.runId
  });
  return { memory: await requiredStore(context).saveMemory(memory) };
}

async function memoryEdit(context: ToolExecutionContext, args: JsonObject): Promise<Record<string, unknown>> {
  const memory = await resolveScopedMemory(context, requiredText(args.memory_id, "memory_id"));
  const updatedMemory = await requiredStore(context).saveMemory(memoryWithContent(memory, requiredText(args.content, "content")));
  return { memory: updatedMemory };
}

async function memoryForget(context: ToolExecutionContext, args: JsonObject): Promise<Record<string, unknown>> {
  const memory = await resolveScopedMemory(context, requiredText(args.memory_id, "memory_id"));
  await requiredStore(context).deleteMemory(memory.memory_id);
  return { memory, forgotten: true };
}

async function resolveScopedMemory(context: ToolExecutionContext, memoryId: string): Promise<MemoryRecord> {
  const memories = await requiredStore(context).listMemories({ ...memoryScopeFromSpec(context.spec), limit: 100 });
  return resolveMemory(memories, memoryId);
}

function requiredStore(context: ToolExecutionContext) {
  if (!context.store) throw new Error("memory store is not available");
  return context.store;
}

function requiredSpec(context: ToolExecutionContext): AgentSpec {
  if (!context.spec) throw new Error("agent spec is not available");
  return context.spec;
}

function boundedLimit(value: unknown): number {
  const limit = Number(value || 50);
  return Number.isFinite(limit) ? Math.max(1, Math.min(100, limit)) : 50;
}
