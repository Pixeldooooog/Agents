import { isDeepStrictEqual } from "node:util";
import type { PendingApproval, ToolTurnContinuation } from "../types/runtimeTypes.js";

/** Persisted approval must describe the unresolved suffix of the original model turn. */
export function validateApprovalContinuation(pending: PendingApproval): ToolTurnContinuation {
  const state = pending.continuation;
  if (!state) throw new Error("approval continuation missing; start a new run");
  for (const value of [state.completed_tool_iterations, state.model_turn_count, state.started_at, state.max_tool_iterations]) {
    if (!Number.isSafeInteger(value) || value < 0) throw new Error("invalid approval continuation counters");
  }
  if (!state.max_tool_iterations || !state.model_turn_count || !Array.isArray(state.remaining_tool_calls)) throw new Error("invalid approval continuation");
  const assistantIndex = pending.messages.findLastIndex(message => message.role === "assistant");
  const calls = pending.messages[assistantIndex]?.tool_calls;
  if (!calls?.length) throw new Error("approval has no original model tool turn");
  const results = pending.messages.slice(assistantIndex + 1);
  if (results.some((result, index) => result.role !== "tool" || result.tool_call_id !== calls[index]?.id)) {
    throw new Error("approval results do not match the completed tool prefix");
  }
  if (!isDeepStrictEqual(calls.slice(results.length), [pending.tool_call, ...state.remaining_tool_calls])) {
    throw new Error("approval calls do not match the unresolved tool suffix");
  }
  return structuredClone(state);
}
