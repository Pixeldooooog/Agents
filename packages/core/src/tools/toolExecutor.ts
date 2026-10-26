import { assertToolArguments } from "./toolValidation.js";
import { boundedToolContent } from "./toolOutput.js";
import type { JsonObject } from "../types/jsonTypes.js";
import { runtimeEvent, type ToolResult } from "../types/runtimeTypes.js";
import type { RegisteredTool, ToolCapability, ToolContext, ToolExecution, ToolRuntimeContext } from "./toolContracts.js";

export async function executeTool(definition: RegisteredTool | undefined, repoRoot: string, name: string, args: JsonObject, context: Omit<ToolRuntimeContext, "repoRoot"> = {}): Promise<ToolExecution> {
  const id = String(args?.tool_call_id || args?.id || `${name}:${Date.now()}`);
  const canonicalName = definition?.name || name;
  const start = runtimeEvent("tool_start", { id, tool_call_id: id, name: canonicalName, requested_name: name }, canonicalName);
  if (!definition) return toolError(id, canonicalName, `unknown tool: ${name}`, [start]);
  try {
    if (context.executionPolicy?.mode === "isolated") throw new Error("isolated_tool_execution_unavailable: sandbox backend deferred");
    if (context.signal?.aborted) throw new Error("tool_execution_cancelled");
    assertToolArguments(definition, args);
    start.payload!.arguments = args;
    await context.onToolStart?.(start);
    const payload = await definition.handler(scopedToolContext(definition, { ...context, repoRoot }), args);
    const content = boundedToolContent(payload);
    const result: ToolResult = { tool_call_id: id, name: canonicalName, content, is_error: false };
    return {
      events: [start, runtimeEvent("tool_result", { tool_call_id: id, name: canonicalName, content, is_error: false }, canonicalName)],
      result
    };
  } catch (error) {
    return toolError(id, canonicalName, error instanceof Error ? error.message : String(error), [start]);
  }
}

/** Least privilege: a handler receives the invocation plus only the capabilities its definition declares. */
export function scopedToolContext(definition: RegisteredTool, context: ToolRuntimeContext): ToolContext<ToolCapability, ToolCapability> {
  const scoped: Record<string, unknown> = {
    repoRoot: context.repoRoot,
    signal: context.signal,
    spec: context.spec,
    runId: context.runId,
    executionPolicy: context.executionPolicy
  };
  for (const capability of definition.requires) {
    if (context[capability] === undefined) throw new Error(`tool capability unavailable: ${capability}`);
    scoped[capability] = context[capability];
  }
  for (const capability of definition.uses ?? []) {
    if (context[capability] !== undefined) scoped[capability] = context[capability];
  }
  // The declared lists are the type parameters of the handler, so this view matches what it may read.
  return scoped as ToolContext<ToolCapability, ToolCapability>;
}

function toolError(id: string, name: string, content: string, events: ReturnType<typeof runtimeEvent>[]): ToolExecution {
  content = boundedToolContent(content);
  const result: ToolResult = { tool_call_id: id, name, content, is_error: true };
  return {
    events: [...events, runtimeEvent("tool_result", { tool_call_id: id, name, content, is_error: true }, name)],
    result
  };
}
