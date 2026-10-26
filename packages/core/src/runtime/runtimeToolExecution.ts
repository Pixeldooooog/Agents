import { deniesTool, isToolEnabled } from "./runtimeToolPermissions.js";
import type { AgentSpec } from "../types/agentTypes.js";
import type { Message, PendingApproval, RuntimeEvent, ToolCall, ToolResult, ToolTurnContinuation } from "../types/runtimeTypes.js";
import { runtimeEvent } from "../types/runtimeTypes.js";
import { canonicalToolName, executeBuiltinTool } from "../tools/toolRegistry.js";
import type { ToolExecution } from "../tools/toolContracts.js";
import type { RuntimeOptions } from "./runtimeOptions.js";
import { runtimeToolExecutionContext } from "./runtimeOptions.js";

export type RuntimeToolCallInput = {
  options: RuntimeOptions;
  spec: AgentSpec;
  runId: string;
  toolCall: ToolCall;
  messages: Message[];
  toolResults: ToolResult[];
  runtimeEvents: RuntimeEvent[];
};

export type PendingApprovalResolution = {
  messages: Message[];
  toolResults: ToolResult[];
  events: RuntimeEvent[];
};

export async function executeRuntimeToolCall(input: RuntimeToolCallInput): Promise<ToolExecution> {
  const name = canonicalToolName(input.toolCall.name);
  if (!isToolEnabled(input.options.settings, input.spec, name) || deniesTool(input.spec, name)) return deniedToolExecution(input.toolCall);
  return executeBuiltinTool(
    input.options.settings.repoRoot,
    input.toolCall.name,
    { ...input.toolCall.arguments, tool_call_id: input.toolCall.id },
    runtimeToolExecutionContext(input.options, {
      spec: input.spec,
      runId: input.runId,
      messages: input.messages,
      runtimeEvents: input.runtimeEvents
    })
  );
}

export async function resolvePendingApproval(
  options: RuntimeOptions,
  spec: AgentSpec,
  pendingApproval: PendingApproval,
  approved: boolean,
  runId: string
): Promise<PendingApprovalResolution> {
  options.signal?.throwIfAborted();
  const messages = [...pendingApproval.messages];
  const toolResults = [...pendingApproval.tool_results];
  const execution = approved
    ? await executeRuntimeToolCall({
        options,
        spec,
        runId,
        toolCall: pendingApproval.tool_call,
        messages,
        toolResults,
        runtimeEvents: []
      })
    : deniedToolExecution(pendingApproval.tool_call);

  toolResults.push(execution.result);
  appendToolResultMessage(messages, pendingApproval.tool_call, execution.result);
  return { messages, toolResults, events: execution.events };
}

export function deniedToolExecution(toolCall: ToolCall): ToolExecution {
  const canonicalName = canonicalToolName(toolCall.name);
  const result: ToolResult = {
    tool_call_id: toolCall.id,
    name: canonicalName,
    content: `tool denied: ${canonicalName}`,
    is_error: true
  };
  return {
    events: [runtimeEvent("tool_result", result, canonicalName)],
    result
  };
}

export function pendingApprovalForToolCall(
  toolCall: ToolCall,
  messages: Message[],
  toolResults: ToolResult[],
  continuation: ToolTurnContinuation
): PendingApproval {
  return {
    approval_id: crypto.randomUUID(),
    continuation: structuredClone(continuation),
    tool_call: structuredClone(toolCall),
    messages: structuredClone(messages),
    tool_results: structuredClone(toolResults)
  };
}

export function appendToolResultMessage(messages: Message[], toolCall: ToolCall, result: ToolResult): void {
  messages.push({
    role: "tool",
    tool_call_id: toolCall.id,
    name: result.name,
    content: result.content
  });
}
