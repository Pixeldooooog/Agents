import { modelUsageFromPayload, modelUsagePayload } from "../models/modelUsage.js";
import type { AgentResult, RunRecord, RuntimeEvent } from "../types/runtimeTypes.js";
import type { SdkResultMessage, SdkResultSubtype } from "./sdkMessages.js";
import { numberField, objectValue, optionalObjectValue, stringField, stringList } from "./sdkEventFields.js";

export function sdkResultMessageFromDoneEvent(
  runId: string,
  sessionId: string,
  event: RuntimeEvent,
  fallbackEventCount = 0
): SdkResultMessage {
  return sdkResultMessageFromPayload(runId, sessionId, objectValue(event.payload), fallbackEventCount);
}

export function sdkResultMessageFromAgentResult(
  runId: string,
  sessionId: string,
  result: AgentResult
): SdkResultMessage {
  return {
    type: "result",
    runId,
    sessionId,
    status: result.status,
    subtype: result.status === "error" ? "error_during_execution" : "success",
    content: result.content,
    result: result.content,
    isError: result.status === "error",
    numTurns: result.messages.filter((message) => message.role === "assistant").length,
    modelUsage: result.model_usage ? modelUsagePayload(result.model_usage) : undefined,
    eventCount: result.events.length,
    errors: result.status === "error" ? ["run failed"] : [],
    uuid: newSdkResultUuid()
  };
}

export function sdkResultMessageFromRunRecord(run: RunRecord, sessionId: string): SdkResultMessage {
  const doneEvent = [...run.events].reverse().find((event) => event.type === "done");
  if (doneEvent) return sdkResultMessageFromDoneEvent(run.run_id, sessionId, doneEvent, run.events.length);
  const modelUsage = lastModelUsagePayload(run);
  const content = lastAssistantContent(run);
  const status = run.status === "awaiting_approval" || run.status === "error" || run.status === "canceled"
    ? run.status
    : "finished";
  return {
    type: "result",
    runId: run.run_id,
    sessionId,
    status,
    subtype: status === "error" ? "error_during_execution" : "success",
    content,
    result: content,
    isError: status === "error",
    eventCount: run.events.length,
    ...(modelUsage ? { modelUsage } : {}),
    errors: status === "error" ? ["run failed"] : [],
    uuid: newSdkResultUuid()
  };
}

function sdkResultMessageFromPayload(
  runId: string,
  sessionId: string,
  payload: Record<string, unknown>,
  fallbackEventCount: number
): SdkResultMessage {
  const errors = resultErrors(payload);
  const statusText = stringField(payload, "status", "stop_reason", "stopReason") || "finished";
  const isError = Boolean(payload.is_error ?? payload.isError) || errors.length > 0 || statusText === "error";
  const content = resultContent(payload);
  return {
    type: "result",
    runId,
    sessionId,
    status: sdkResultStatus(statusText, isError),
    subtype: resultSubtype(payload.subtype, isError),
    content,
    result: content,
    isError,
    durationMs: numberField(payload.duration_ms ?? payload.durationMs),
    durationApiMs: numberField(payload.duration_api_ms ?? payload.durationApiMs),
    numTurns: numberField(payload.num_turns ?? payload.numTurns),
    stopReason: stringField(payload, "stop_reason", "stopReason") || statusText,
    totalCostUsd: numberField(payload.total_cost_usd ?? payload.totalCostUsd),
    usage: objectValue(payload.usage),
    modelUsage: objectValue(payload.modelUsage ?? payload.model_usage),
    permissionDenials: objectList(payload.permission_denials ?? payload.permissionDenials),
    structuredOutput: payload.structured_output ?? payload.structuredOutput,
    fastModeState: optionalObjectValue(payload.fast_mode_state ?? payload.fastModeState) || null,
    errors,
    eventCount: numberField(payload.event_count ?? payload.eventCount) || fallbackEventCount,
    uuid: stringField(payload, "uuid", "message_id", "messageId") || newSdkResultUuid()
  };
}

function sdkResultStatus(statusText: string, isError: boolean): SdkResultMessage["status"] {
  if (statusText === "awaiting_approval" || statusText === "canceled") return statusText;
  if (isError || statusText === "error") return "error";
  return "finished";
}

function resultSubtype(value: unknown, isError: boolean): SdkResultSubtype {
  const subtype = String(value || "");
  if (
    subtype === "error_during_execution"
    || subtype === "error_max_turns"
    || subtype === "error_max_budget_usd"
    || subtype === "error_max_structured_output_retries"
  ) {
    return subtype;
  }
  return isError ? "error_during_execution" : "success";
}

function resultContent(payload: Record<string, unknown>): string {
  if (payload.result !== undefined) return String(payload.result || "");
  return stringField(payload, "content");
}

function resultErrors(payload: Record<string, unknown>): string[] {
  const errors = stringList(payload.errors);
  const error = stringField(payload, "error");
  return errors.length || !error ? errors : [error];
}

function objectList(value: unknown): Array<Record<string, unknown>> {
  if (!Array.isArray(value)) return [];
  return value.map(objectValue).filter((item) => Object.keys(item).length);
}

function lastAssistantContent(run: RunRecord): string {
  const modelMessage = [...run.events].reverse().find((event) => event.type === "model_message");
  return String(modelMessage?.payload?.content || "");
}

function lastModelUsagePayload(run: RunRecord): Record<string, unknown> | undefined {
  const doneUsage = [...run.events].reverse().find((event) => event.type === "done")?.payload?.modelUsage;
  return modelUsagePayload(modelUsageFromPayload(doneUsage));
}

function newSdkResultUuid(): string {
  return `result_${crypto.randomUUID().replaceAll("-", "")}`;
}
