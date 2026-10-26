import { dispatchRuntimeHooks } from "../hooks/runtimeHooks.js";
import type { AgentSpec } from "../types/agentTypes.js";
import type { AgentResult, Message, RuntimeEvent, ToolResult, ToolCall, PendingApproval } from "../types/runtimeTypes.js";
import { runtimeEvent } from "../types/runtimeTypes.js";
import type { ModelUsage } from "../types/modelTypes.js";
import { combineModelUsage, modelUsagePayload } from "../models/modelUsage.js";
import { completeModelTurn, streamModelTurn, ModelConfigError, resolveModelClientConfig } from "../models/modelClients.js";
import { defaultEnabledTools } from "../models/modelProfiles.js";
import { canonicalToolName, modelToolDefinitions } from "../tools/toolRegistry.js";
import { canContinueToolLoop, runtimeToolLoopBudget } from "./runtimeLimits.js";
import { deniesTool, requiresApproval, isToolEnabled } from "./runtimeToolPermissions.js";
import { validateApprovalContinuation } from "./runtimeApprovalContinuation.js";
import type { RuntimeOptions } from "./runtimeOptions.js";
import {
  appendToolResultMessage,
  deniedToolExecution,
  executeRuntimeToolCall,
  resolvePendingApproval,
  pendingApprovalForToolCall
} from "./runtimeToolExecution.js";

export type RuntimeTurnLoopInput = {
  options: RuntimeOptions;
  spec: AgentSpec;
  runId: string;
  initialMessages: Message[];
  initialToolResults?: ToolResult[];
  resume?: { pendingApproval: PendingApproval; approved: boolean };
};

export async function runRuntimeTurnLoop(input: RuntimeTurnLoopInput): Promise<AgentResult> {
  let startedAt = Date.now();
  const events: RuntimeEvent[] = [];
  let messages = [...input.initialMessages];
  let toolResults: ToolResult[] = [...(input.initialToolResults || [])];
  const toolLoopBudget = runtimeToolLoopBudget(input.options.settings, input.spec);
  let completedToolIterations = 0;
  let modelTurnCount = 0;
  let accumulatedModelUsage: ModelUsage | undefined;
  const emit = async (event: RuntimeEvent) => {
    events.push(event);
    await input.options.onEvent?.(event);
  };

  try {
    const continuation = input.resume ? validateApprovalContinuation(input.resume.pendingApproval) : undefined;
    if (continuation) {
      completedToolIterations = continuation.completed_tool_iterations;
      modelTurnCount = continuation.model_turn_count;
      accumulatedModelUsage = continuation.model_usage;
      startedAt = continuation.started_at;
      toolLoopBudget.maxIterations = Math.min(toolLoopBudget.maxIterations, continuation.max_tool_iterations);
    }
    throwIfCanceled(input.options.signal);

    const config = {
      ...resolveModelClientConfig(input.options.settings, input.spec),
      maxThinkingTokens: input.spec.runtime.maxThinkingTokens,
      signal: input.options.signal
    };
    const enabledTools = input.spec.enabled_tools.length
      ? input.spec.enabled_tools
      : defaultEnabledTools(input.options.settings);

    let remainingCalls: ToolCall[] | undefined;
    if (input.resume && continuation) {
      if (!canContinueToolLoop(completedToolIterations, toolLoopBudget)) throw new Error("tool-call loop exceeded max iterations");
      const resolution = await resolvePendingApproval(input.options, input.spec, input.resume.pendingApproval, input.resume.approved, input.runId, emit);
      messages = resolution.messages;
      toolResults = resolution.toolResults;
      for (const event of resolution.events) await emit(event);
      remainingCalls = continuation.remaining_tool_calls;
    }

    while (canContinueToolLoop(completedToolIterations, toolLoopBudget)) {
      throwIfCanceled(input.options.signal);
      if (remainingCalls === undefined) {
        const before = await dispatchRuntimeHooks(input.options, input.spec, "before_request");
        messages.push(...before.messages);
        for (const event of before.events) await emit(event);
        const definitions = modelToolDefinitions(enabledTools, input.options.mcpProviders);
        const modelTurn = input.options.stream && config.protocol !== "gemini"
          ? await streamModelTurn(config, messages, definitions, async event => {
            // Partial arguments never enter the tool executor or persistent message history.
            if (event.type === "text_delta") await emit(runtimeEvent("text_delta", { delta: event.delta }));
          })
          : await completeModelTurn(config, messages, definitions);
        modelTurnCount += 1;
        accumulatedModelUsage = combineModelUsage([accumulatedModelUsage, modelTurn.usage]);
        throwIfCanceled(input.options.signal);
        const assistant: Message = { role: "assistant", content: modelTurn.content, tool_calls: modelTurn.tool_calls, model_context: modelTurn.model_context };
        messages.push(assistant);
        const after = await dispatchRuntimeHooks(input.options, input.spec, "after_response");
        for (const event of after.events) await emit(event);
        if (modelTurn.content) await emit(runtimeEvent("model_message", compactEventPayload({
          content: modelTurn.content,
          modelUsage: modelUsagePayload(modelTurn.usage)
        })));
        if (!modelTurn.tool_calls.length) {
          await emit(runtimeEvent("done", doneEventPayload(startedAt, modelTurnCount, events.length, {
            status: "finished",
            content: modelTurn.content,
            modelUsage: modelUsagePayload(accumulatedModelUsage)
          })));
          return {
            run_id: input.runId,
            status: "finished",
            content: modelTurn.content,
            messages,
            tool_results: toolResults,
            events,
            model_usage: accumulatedModelUsage
          };
        }

        remainingCalls = modelTurn.tool_calls;
      }

      for (const [callIndex, toolCall] of remainingCalls.entries()) {
        throwIfCanceled(input.options.signal);
        const canonicalName = canonicalToolName(toolCall.name);
        if (!isToolEnabled(input.options.settings, input.spec, canonicalName) || deniesTool(input.spec, canonicalName)) {
          const deniedExecution = deniedToolExecution(toolCall);
          for (const event of deniedExecution.events) await emit(event);
          toolResults.push(deniedExecution.result);
          appendToolResultMessage(messages, toolCall, deniedExecution.result);
          continue;
        }
        if (requiresApproval(input.spec, canonicalName)) {
          const pendingApproval = pendingApprovalForToolCall(toolCall, messages, toolResults, {
            remaining_tool_calls: remainingCalls.slice(callIndex + 1),
            completed_tool_iterations: completedToolIterations,
            max_tool_iterations: toolLoopBudget.maxIterations,
            model_turn_count: modelTurnCount,
            model_usage: accumulatedModelUsage,
            started_at: startedAt
          });
          await emit(runtimeEvent(
            "tool_approval_required",
            {
              approval_id: pendingApproval.approval_id,
              tool_call: toolCall,
              permission: { reason: "tool requires approval" }
            },
            toolCall.name
          ));
          await emit(runtimeEvent("done", doneEventPayload(startedAt, modelTurnCount, events.length, {
            status: "awaiting_approval",
            content: messages.findLast(message => message.role === "assistant")?.content || "",
            modelUsage: modelUsagePayload(accumulatedModelUsage)
          })));
          return {
            run_id: input.runId,
            status: "awaiting_approval",
            content: messages.findLast(message => message.role === "assistant")?.content || "",
            messages,
            tool_results: toolResults,
            events,
            pending_approval: pendingApproval,
            model_usage: accumulatedModelUsage
          };
        }

        const execution = await executeRuntimeToolCall({
          options: input.options,
          spec: input.spec,
          runId: input.runId,
          toolCall,
          messages,
          toolResults,
          runtimeEvents: events,
          onEvent: emit
        });
        for (const event of execution.events) await emit(event);
        toolResults.push(execution.result);
        appendToolResultMessage(messages, toolCall, execution.result);
        throwIfCanceled(input.options.signal);
      }
      remainingCalls = undefined;
      completedToolIterations += 1;
    }

    throw new Error("tool-call loop exceeded max iterations");
  } catch (error) {
    if (isRuntimeCancellation(error, input.options.signal)) {
      await emit(runtimeEvent("done", doneEventPayload(startedAt, modelTurnCount, events.length, {
        status: "canceled",
        content: "run canceled",
        modelUsage: modelUsagePayload(accumulatedModelUsage)
      })));
      return {
        run_id: input.runId,
        status: "canceled",
        content: "run canceled",
        messages,
        tool_results: toolResults,
        events,
        model_usage: accumulatedModelUsage
      };
    }
    const messageText = errorMessage(error);
    await emit(runtimeEvent("error", { message: messageText }, error instanceof ModelConfigError ? "config" : "runtime"));
    await emit(runtimeEvent("done", doneEventPayload(startedAt, modelTurnCount, events.length, {
      status: "error",
      content: "",
      error: messageText,
      modelUsage: modelUsagePayload(accumulatedModelUsage)
    })));
    return {
      run_id: input.runId,
      status: "error",
      content: "",
      messages,
      tool_results: toolResults,
      events,
      model_usage: accumulatedModelUsage
    };
  }
}

class RuntimeCancellationError extends Error {
  constructor() {
    super("run canceled");
    this.name = "RuntimeCancellationError";
  }
}

function throwIfCanceled(signal: AbortSignal | undefined): void {
  if (signal?.aborted) throw new RuntimeCancellationError();
}

function isRuntimeCancellation(error: unknown, signal: AbortSignal | undefined): boolean {
  return error instanceof RuntimeCancellationError || Boolean(signal?.aborted);
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function compactEventPayload(payload: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(Object.entries(payload).filter(([, value]) => value !== undefined));
}

function doneEventPayload(
  startedAt: number,
  modelTurnCount: number,
  emittedEventCount: number,
  payload: Record<string, unknown>
): Record<string, unknown> {
  return compactEventPayload({
    ...payload,
    duration_ms: Math.max(0, Date.now() - startedAt),
    num_turns: modelTurnCount,
    event_count: emittedEventCount + 1
  });
}
