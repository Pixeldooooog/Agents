import type { RuntimeEvent } from "../types/runtimeTypes.js";
import type { SdkMessage, SdkToolProgressMessage, SdkToolProgressStatus } from "./sdkMessages.js";
import { newSdkMessageUuid, numberField, objectValue, stringField, stringList } from "./sdkEventFields.js";
import { toolCallIdFromPayload, toolCallIdFromToolCall, toolResultPayloadData } from "./sdkEventPayloads.js";
import { sdkResultMessageFromDoneEvent } from "./sdkResultMessages.js";

export function explicitSdkMessagesFromRuntimeEvent(
  runId: string,
  sessionId: string,
  event: RuntimeEvent
): SdkMessage[] {
  const payload = objectValue(event.payload);
  if (event.type === "model_retry") return [apiRetryMessage(runId, sessionId, payload)];
  if (event.type === "model_recovery") return [modelRecoveryMessage(runId, sessionId, event, payload)];
  if (event.type === "rate_limit_event") return [rateLimitEventMessage(runId, sessionId, payload)];
  if (event.type === "local_command_output") return [localCommandOutputMessage(runId, sessionId, payload)];
  if (event.type === "tool_use_summary") return [toolUseSummaryMessage(runId, sessionId, payload)];
  if (event.type === "tool_progress") return [toolProgressMessage(runId, sessionId, event, payload)];
  if (event.type === "elicitation_complete") return [elicitationCompleteMessage(runId, sessionId, payload)];
  if (event.type === "prompt_suggestion") return [promptSuggestionMessage(runId, sessionId, payload)];
  if (event.type === "post_turn_summary") return [postTurnSummaryMessage(runId, sessionId, payload)];
  if (event.type === "hook_started") return [hookStartedMessage(runId, sessionId, payload)];
  if (event.type === "hook_progress") return [hookProgressMessage(runId, sessionId, payload)];
  if (event.type === "hook_response") return [hookResponseMessage(runId, sessionId, payload)];
  if (event.type === "tool_approval_decision") return [toolApprovalDecisionMessage(runId, sessionId, event, payload)];
  if (event.type === "done") return [sdkResultMessageFromDoneEvent(runId, sessionId, event)];
  return [];
}

export function sideChannelSdkMessagesFromRuntimeEvent(
  runId: string,
  sessionId: string,
  event: RuntimeEvent
): SdkMessage[] {
  const authStatus = authStatusMessageFromToolResult(runId, sessionId, event);
  return authStatus ? [authStatus] : [];
}

export function toolContract(payload: Record<string, unknown>): Record<string, unknown> {
  return objectValue(payload.contract);
}

export function toolContractActivity(payload: Record<string, unknown>): Record<string, unknown> | undefined {
  const contract = toolContract(payload);
  const activity = objectValue(contract.activity);
  return Object.keys(activity).length ? activity : undefined;
}

export function toolContractMetadata(payload: Record<string, unknown>): Record<string, unknown> | undefined {
  const contract = toolContract(payload);
  const metadata = objectValue(contract.metadata);
  return Object.keys(metadata).length ? metadata : undefined;
}

export function toolContractPaths(payload: Record<string, unknown>): string[] | undefined {
  const contract = toolContract(payload);
  const paths = stringList(contract.paths);
  return paths.length ? paths : undefined;
}

export function toolContractTarget(payload: Record<string, unknown>): string | undefined {
  return stringField(toolContract(payload), "target") || undefined;
}

export function toolProgressContractFields(
  payload: Record<string, unknown>
): Partial<Pick<SdkToolProgressMessage, "activity" | "target" | "paths" | "metadata">> {
  return {
    ...(toolContractActivity(payload) ? { activity: toolContractActivity(payload) } : {}),
    ...(toolContractTarget(payload) ? { target: toolContractTarget(payload) } : {}),
    ...(toolContractPaths(payload) ? { paths: toolContractPaths(payload) } : {}),
    ...(toolContractMetadata(payload) ? { metadata: toolContractMetadata(payload) } : {})
  };
}

function apiRetryMessage(runId: string, sessionId: string, payload: Record<string, unknown>): SdkMessage {
  return {
    type: "system",
    subtype: "api_retry",
    runId,
    sessionId,
    attempt: retryAttempt(payload),
    maxRetries: retryMaxAttempts(payload),
    retryDelayMs: retryDelayMs(payload),
    errorStatus: retryErrorStatus(payload),
    error: retryErrorPayload(payload),
    metadata: { ...payload }
  };
}

function modelRecoveryMessage(
  runId: string,
  sessionId: string,
  event: RuntimeEvent,
  payload: Record<string, unknown>
): SdkMessage {
  return {
    type: "system",
    subtype: "model_recovery",
    runId,
    sessionId,
    reason: event.name || stringField(payload, "reason"),
    attempt: numberField(payload.attempt),
    maxAttempts: numberField(payload.max_attempts ?? payload.maxAttempts),
    stopReason: stringField(payload, "stop_reason", "stopReason"),
    message: stringField(payload, "message"),
    metadata: { ...payload },
    uuid: sdkEventUuid(payload)
  };
}

function rateLimitEventMessage(runId: string, sessionId: string, payload: Record<string, unknown>): SdkMessage {
  return {
    type: "rate_limit_event",
    runId,
    sessionId,
    rateLimitInfo: objectValue(payload.rate_limit_info || payload.rateLimitInfo),
    uuid: sdkEventUuid(payload)
  };
}

function localCommandOutputMessage(runId: string, sessionId: string, payload: Record<string, unknown>): SdkMessage {
  return {
    type: "system",
    subtype: "local_command_output",
    runId,
    sessionId,
    content: localCommandOutputContent(payload),
    uuid: sdkEventUuid(payload)
  };
}

function toolUseSummaryMessage(runId: string, sessionId: string, payload: Record<string, unknown>): SdkMessage {
  return {
    type: "tool_use_summary",
    runId,
    sessionId,
    summary: stringField(payload, "summary"),
    precedingToolUseIds: stringList(payload.preceding_tool_use_ids ?? payload.precedingToolUseIds),
    uuid: sdkEventUuid(payload)
  };
}

function toolProgressMessage(
  runId: string,
  sessionId: string,
  event: RuntimeEvent,
  payload: Record<string, unknown>
): SdkMessage {
  const metadata = {
    ...(toolContractMetadata(payload) || {}),
    ...objectValue(payload.metadata)
  };
  return {
    type: "tool_progress",
    runId,
    sessionId,
    toolCallId: toolCallIdFromPayload(payload),
    name: stringField(payload, "tool_name", "toolName") || event.name || "",
    status: toolProgressStatus(payload.status),
    input: objectValue(payload.input),
    result: objectValue(payload.result),
    activity: nonEmptyObject(toolContractActivity(payload) || objectValue(payload.activity)),
    target: toolContractTarget(payload) || stringField(payload, "target") || undefined,
    paths: toolContractPaths(payload) || stringList(payload.paths),
    metadata: nonEmptyObject(metadata),
    error: stringField(payload, "error"),
    output: stringField(payload, "output") || undefined,
    fullOutput: stringField(payload, "full_output", "fullOutput") || undefined,
    elapsedTimeSeconds: numberField(payload.elapsed_time_seconds ?? payload.elapsedTimeSeconds),
    totalLines: numberField(payload.total_lines ?? payload.totalLines),
    totalBytes: numberField(payload.total_bytes ?? payload.totalBytes),
    taskId: stringField(payload, "task_id", "taskId") || undefined,
    timeoutMs: numberField(payload.timeout_ms ?? payload.timeoutMs)
  };
}

function elicitationCompleteMessage(runId: string, sessionId: string, payload: Record<string, unknown>): SdkMessage {
  return {
    type: "system",
    subtype: "elicitation_complete",
    runId,
    sessionId,
    mcpServerName: stringField(payload, "mcp_server_name", "mcpServerName", "server"),
    elicitationId: stringField(payload, "elicitation_id", "elicitationId", "id"),
    uuid: sdkEventUuid(payload)
  };
}

function promptSuggestionMessage(runId: string, sessionId: string, payload: Record<string, unknown>): SdkMessage {
  return {
    type: "prompt_suggestion",
    runId,
    sessionId,
    suggestion: stringField(payload, "suggestion"),
    uuid: sdkEventUuid(payload)
  };
}

function postTurnSummaryMessage(runId: string, sessionId: string, payload: Record<string, unknown>): SdkMessage {
  return {
    type: "system",
    subtype: "post_turn_summary",
    runId,
    sessionId,
    summarizesUuid: stringField(payload, "summarizes_uuid", "summarizesUuid"),
    statusCategory: postTurnStatusCategory(payload.status_category ?? payload.statusCategory),
    statusDetail: stringField(payload, "status_detail", "statusDetail"),
    isNoteworthy: Boolean(payload.is_noteworthy ?? payload.isNoteworthy),
    title: stringField(payload, "title"),
    description: stringField(payload, "description"),
    recentAction: stringField(payload, "recent_action", "recentAction"),
    needsAction: stringField(payload, "needs_action", "needsAction"),
    artifactUrls: stringList(payload.artifact_urls ?? payload.artifactUrls),
    uuid: sdkEventUuid(payload)
  };
}

function hookStartedMessage(runId: string, sessionId: string, payload: Record<string, unknown>): SdkMessage {
  return {
    type: "system",
    subtype: "hook_started",
    runId,
    sessionId,
    hookId: stringField(payload, "hook_id", "hookId"),
    hookName: stringField(payload, "hook_name", "hookName"),
    hookEvent: stringField(payload, "hook_event", "hookEvent"),
    uuid: sdkEventUuid(payload)
  };
}

function hookProgressMessage(runId: string, sessionId: string, payload: Record<string, unknown>): SdkMessage {
  return {
    type: "system",
    subtype: "hook_progress",
    runId,
    sessionId,
    hookId: stringField(payload, "hook_id", "hookId"),
    hookName: stringField(payload, "hook_name", "hookName"),
    hookEvent: stringField(payload, "hook_event", "hookEvent"),
    stdout: stringField(payload, "stdout"),
    stderr: stringField(payload, "stderr"),
    output: stringField(payload, "output"),
    uuid: sdkEventUuid(payload)
  };
}

function hookResponseMessage(runId: string, sessionId: string, payload: Record<string, unknown>): SdkMessage {
  return {
    type: "system",
    subtype: "hook_response",
    runId,
    sessionId,
    hookId: stringField(payload, "hook_id", "hookId"),
    hookName: stringField(payload, "hook_name", "hookName"),
    hookEvent: stringField(payload, "hook_event", "hookEvent"),
    output: stringField(payload, "output"),
    stdout: stringField(payload, "stdout"),
    stderr: stringField(payload, "stderr"),
    exitCode: optionalNumber(payload.exit_code ?? payload.exitCode),
    outcome: hookOutcome(payload.outcome),
    uuid: sdkEventUuid(payload)
  };
}

function toolApprovalDecisionMessage(
  runId: string,
  sessionId: string,
  event: RuntimeEvent,
  payload: Record<string, unknown>
): SdkMessage {
  const toolCall = objectValue(payload.tool_call);
  return {
    type: "tool_progress",
    runId,
    sessionId,
    toolCallId: toolCallIdFromToolCall(toolCall),
    name: stringField(toolCall, "name") || event.name || "",
    status: payload.approved ? "completed" : "denied",
    input: objectValue(toolCall.arguments),
    result: payload,
    activity: toolContractActivity(payload),
    target: toolContractTarget(payload),
    paths: toolContractPaths(payload) || [],
    metadata: toolContractMetadata(payload),
    error: ""
  };
}

function authStatusMessageFromToolResult(
  runId: string,
  sessionId: string,
  event: RuntimeEvent
): SdkMessage | undefined {
  if (event.type !== "tool_result") return undefined;
  const payload = objectValue(event.payload);
  const contract = toolContract(payload);
  const metadata = objectValue(contract.metadata);
  if (!String(event.name || "").endsWith("__authenticate") && !metadata.auth_tool) return undefined;

  const data = toolResultPayloadData(payload);
  const status = stringField(data, "status");
  const authUrl = stringField(data, "authUrl", "auth_url");
  const message = stringField(data, "message");
  const output = [message, authUrl].filter(Boolean);
  return {
    type: "auth_status",
    runId,
    sessionId,
    isAuthenticating: status === "auth_url",
    output: output.length ? output : status ? [status] : [],
    error: status === "error" || status === "unsupported" ? message : "",
    metadata: Object.fromEntries(Object.entries(data).filter(([key]) => key !== "_meta"))
  };
}

function retryAttempt(payload: Record<string, unknown>): number {
  if (payload.next_attempt !== undefined) return numberField(payload.next_attempt);
  if (payload.attempt !== undefined) return numberField(payload.attempt);
  return payload.failed_attempt !== undefined ? numberField(payload.failed_attempt) + 1 : 0;
}

function retryMaxAttempts(payload: Record<string, unknown>): number {
  return numberField(payload.max_attempts ?? payload.max_retries ?? payload.maxAttempts ?? payload.maxRetries);
}

function retryDelayMs(payload: Record<string, unknown>): number {
  if (payload.retry_delay_ms !== undefined || payload.retryDelayMs !== undefined) {
    return numberField(payload.retry_delay_ms ?? payload.retryDelayMs);
  }
  return Math.trunc(numberField(payload.delay_seconds ?? payload.delaySeconds) * 1000);
}

function retryErrorStatus(payload: Record<string, unknown>): number | null {
  const value = payload.error_status ?? payload.errorStatus ?? payload.status_code ?? payload.statusCode ?? payload.status;
  if (value === undefined || value === null || value === "") return null;
  return numberField(value);
}

function retryErrorPayload(payload: Record<string, unknown>): Record<string, unknown> {
  const error = objectValue(payload.error);
  if (Object.keys(error).length) return error;
  return {
    message: stringField(payload, "error", "message") || "model request failed",
    type: stringField(payload, "error_type", "type") || "unknown"
  };
}

function localCommandOutputContent(payload: Record<string, unknown>): string {
  return (stringField(payload, "content", "output"))
    .replaceAll("<local-command-stdout>", "")
    .replaceAll("</local-command-stdout>", "")
    .replaceAll("<local-command-stderr>", "")
    .replaceAll("</local-command-stderr>", "")
    .trim();
}

function toolProgressStatus(value: unknown): SdkToolProgressStatus {
  const status = String(value || "running");
  if (["started", "running", "stalled", "completed", "failed", "awaiting_approval", "denied"].includes(status)) {
    return status as SdkToolProgressStatus;
  }
  return "running";
}

function hookOutcome(value: unknown): "success" | "error" | "cancelled" {
  if (value === "error") return "error";
  if (value === "cancelled") return "cancelled";
  return "success";
}

function postTurnStatusCategory(value: unknown): "blocked" | "waiting" | "completed" | "review_ready" | "failed" {
  if (value === "blocked" || value === "waiting" || value === "review_ready" || value === "failed") return value;
  return "completed";
}

function optionalNumber(value: unknown): number | null {
  if (value === undefined || value === null || value === "") return null;
  return numberField(value);
}

function nonEmptyObject(value: Record<string, unknown>): Record<string, unknown> | undefined {
  return Object.keys(value).length ? value : undefined;
}

function sdkEventUuid(payload: Record<string, unknown>): string {
  return stringField(payload, "uuid", "message_id", "messageId") || newSdkMessageUuid();
}
