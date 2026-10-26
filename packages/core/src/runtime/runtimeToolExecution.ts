import { dispatchRuntimeHooks } from "../hooks/runtimeHooks.js";
import { deniesTool, isToolEnabled, type ToolAuthorization } from "./runtimeToolPermissions.js";
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
  /** Snapshot taken when the run started; gates combine it with the live spec. */
  authorization: ToolAuthorization;
  runId: string;
  toolCall: ToolCall;
  messages: Message[];
  toolResults: ToolResult[];
  runtimeEvents: RuntimeEvent[];
  onEvent?: (event: RuntimeEvent) => void | Promise<void>;
};

export type PendingApprovalResolution = {
  messages: Message[];
  toolResults: ToolResult[];
  events: RuntimeEvent[];
};

export async function executeRuntimeToolCall(input: RuntimeToolCallInput): Promise<ToolExecution> {
  const name = canonicalToolName(input.toolCall.name);
  const { authorization, options: { settings }, spec } = input;
  if (!isToolEnabled(authorization, settings, spec, name) || deniesTool(authorization, settings, spec, name)) return deniedToolExecution(input.toolCall);
  const before = await dispatchRuntimeHooks(input.options, input.spec, "pre_tool_use", name);
  if (before.denied) {
    const denied = deniedToolExecution(input.toolCall);
    return { ...denied, events: [...before.events, ...denied.events] };
  }
  if (input.onEvent) for (const event of before.events) await input.onEvent(event);
  let startEmitted = false;
  const execution = await executeBuiltinTool(
    input.options.settings.repoRoot,
    input.toolCall.name,
    { ...input.toolCall.arguments, tool_call_id: input.toolCall.id },
    {
      ...runtimeToolExecutionContext(input.options, {
        spec: input.spec,
        runId: input.runId,
        messages: input.messages,
        runtimeEvents: input.runtimeEvents
      }),
      onToolStart: input.onEvent ? async event => {
        await input.onEvent!(event);
        startEmitted = true;
      } : undefined
    }
  );
  const after = await dispatchRuntimeHooks(input.options, input.spec, "post_tool_use", name);
  if (!input.onEvent) execution.events.unshift(...before.events);
  if (startEmitted) execution.events = execution.events.filter(event => event.type !== "tool_start");
  execution.events.push(...after.events);
  if (!execution.result.is_error && (name === "worktree.enter" || name === "worktree.exit")) {
    const worktree = await dispatchRuntimeHooks(input.options, input.spec, name === "worktree.enter" ? "worktree_create" : "worktree_remove", name);
    execution.events.push(...worktree.events);
  }
  return execution;
}

export async function resolvePendingApproval(
  options: RuntimeOptions,
  spec: AgentSpec,
  authorization: ToolAuthorization,
  pendingApproval: PendingApproval,
  approved: boolean,
  runId: string,
  onEvent?: (event: RuntimeEvent) => void | Promise<void>
): Promise<PendingApprovalResolution> {
  options.signal?.throwIfAborted();
  const messages = [...pendingApproval.messages];
  const toolResults = [...pendingApproval.tool_results];
  const execution = approved
    ? await executeRuntimeToolCall({
        options,
        spec,
        authorization,
        runId,
        toolCall: pendingApproval.tool_call,
        messages,
        toolResults,
        runtimeEvents: [],
        onEvent
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
