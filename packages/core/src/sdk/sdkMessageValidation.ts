import {
  optionalBoolean,
  optionalNumber,
  optionalNumberOrNull,
  optionalObject,
  optionalObjectArray,
  optionalObjectOrNull,
  optionalString,
  optionalStringArray,
  optionalStringOrNull,
  requireBoolean,
  requireNumber,
  requireObject,
  requireObjectArray,
  requireString,
  requireStringArray,
  rejectUnknownKeys,
  stringValue
} from "./sdkWireValidationFields.js";
import { isSdkPermissionMode } from "./sdkPermissionModes.js";

export function validateSdkMessageFrame(message: Record<string, unknown>, messageType: string): boolean {
  if (messageType === "user_message") {
    rejectMessageKeys(message, ["type", "uuid", "sessionId", "content", "message", "parentToolUseId", "isSynthetic", "toolUseResult", "priority", "timestamp", "isReplay"]);
    requireString(message, "uuid");
    requireString(message, "sessionId");
    requireString(message, "content");
    optionalObject(message, "message");
    optionalString(message, "parentToolUseId");
    optionalBoolean(message, "isSynthetic");
    optionalUserMessagePriority(message, "priority");
    optionalString(message, "timestamp");
    optionalBoolean(message, "isReplay");
    return true;
  }
  if (messageType === "run_started") {
    rejectMessageKeys(message, ["type", "runId", "sessionId", "createdAt"]);
    requireString(message, "runId");
    requireString(message, "sessionId");
    requireNumber(message, "createdAt");
    return true;
  }
  if (messageType === "assistant_message") {
    rejectMessageKeys(message, ["type", "runId", "sessionId", "content", "message", "parentToolUseId", "error", "uuid", "modelUsage"]);
    requireString(message, "runId");
    requireString(message, "sessionId");
    requireString(message, "content");
    optionalObject(message, "message");
    optionalString(message, "parentToolUseId");
    optionalAssistantError(message, "error");
    optionalString(message, "uuid");
    optionalObject(message, "modelUsage");
    return true;
  }
  if (messageType === "tool_result") {
    rejectMessageKeys(message, ["type", "runId", "sessionId", "toolName", "toolCallId", "content", "isError"]);
    requireString(message, "runId");
    requireString(message, "sessionId");
    requireString(message, "toolName");
    requireString(message, "toolCallId");
    requireString(message, "content");
    requireBoolean(message, "isError");
    return true;
  }
  if (messageType === "approval_required") {
    rejectMessageKeys(message, ["type", "runId", "sessionId", "approvalId", "toolName", "arguments", "reason"]);
    requireString(message, "runId");
    requireString(message, "sessionId");
    requireString(message, "approvalId");
    requireString(message, "toolName");
    requireObject(message, "arguments");
    requireString(message, "reason");
    return true;
  }
  if (messageType === "tool_progress") {
    validateToolProgressMessage(message);
    return true;
  }
  if (messageType === "auth_status") {
    rejectMessageKeys(message, ["type", "runId", "sessionId", "isAuthenticating", "output", "error", "metadata"]);
    requireString(message, "runId");
    requireString(message, "sessionId");
    requireBoolean(message, "isAuthenticating");
    requireStringArray(message, "output");
    requireString(message, "error");
    requireObject(message, "metadata");
    return true;
  }
  if (messageType === "rate_limit_event") {
    rejectMessageKeys(message, ["type", "runId", "sessionId", "rateLimitInfo", "uuid"]);
    requireString(message, "runId");
    requireString(message, "sessionId");
    requireObject(message, "rateLimitInfo");
    requireString(message, "uuid");
    return true;
  }
  if (messageType === "tool_use_summary") {
    rejectMessageKeys(message, ["type", "runId", "sessionId", "summary", "precedingToolUseIds", "uuid"]);
    requireString(message, "runId");
    requireString(message, "sessionId");
    requireString(message, "summary");
    requireStringArray(message, "precedingToolUseIds");
    requireString(message, "uuid");
    return true;
  }
  if (messageType === "prompt_suggestion") {
    rejectMessageKeys(message, ["type", "runId", "sessionId", "suggestion", "uuid"]);
    requireString(message, "runId");
    requireString(message, "sessionId");
    requireString(message, "suggestion");
    requireString(message, "uuid");
    return true;
  }
  if (messageType === "stream_event") {
    rejectMessageKeys(message, ["type", "runId", "sessionId", "event", "parentToolUseId", "uuid"]);
    requireString(message, "runId");
    requireString(message, "sessionId");
    requireObject(message, "event");
    requireString(message, "uuid");
    optionalString(message, "parentToolUseId");
    return true;
  }
  if (messageType === "system") {
    validateSystemMessage(message);
    return true;
  }
  if (messageType === "runtime_event") {
    rejectMessageKeys(message, ["type", "runId", "sessionId", "event"]);
    requireString(message, "runId");
    requireString(message, "sessionId");
    const event = requireObject(message, "event");
    if (!stringValue(event.type)) throw new Error("runtime_event.event.type must be a string");
    return true;
  }
  if (messageType === "result") {
    validateResultMessage(message);
    return true;
  }
  return false;
}

export function validatePermissionMode(mode: string, label: string): void {
  if (!isSdkPermissionMode(mode)) {
    throw new Error(`${label} is invalid`);
  }
}

function validateToolProgressMessage(message: Record<string, unknown>): void {
  rejectMessageKeys(message, [
    "type",
    "runId",
    "sessionId",
    "toolCallId",
    "name",
    "status",
    "input",
    "result",
    "activity",
    "target",
    "paths",
    "metadata",
    "error",
    "output",
    "fullOutput",
    "elapsedTimeSeconds",
    "totalLines",
    "totalBytes",
    "taskId",
    "timeoutMs"
  ]);
  requireString(message, "runId");
  requireString(message, "sessionId");
  requireString(message, "toolCallId");
  requireString(message, "name");
  const status = requireString(message, "status");
  if (!["started", "running", "stalled", "completed", "failed", "awaiting_approval", "denied"].includes(status)) {
    throw new Error("tool_progress.status is invalid");
  }
  requireObject(message, "input");
  requireObject(message, "result");
  optionalObject(message, "activity");
  optionalString(message, "target");
  optionalStringArray(message, "paths");
  optionalObject(message, "metadata");
  requireString(message, "error");
  optionalString(message, "output");
  optionalString(message, "fullOutput");
  optionalNumber(message, "elapsedTimeSeconds");
  optionalNumber(message, "totalLines");
  optionalNumber(message, "totalBytes");
  optionalString(message, "taskId");
  optionalNumber(message, "timeoutMs");
}

function validateSystemMessage(message: Record<string, unknown>): void {
  requireString(message, "runId");
  requireString(message, "sessionId");
  const subtype = requireString(message, "subtype");
  if (subtype === "init") {
    validateSystemInitMessage(message);
    return;
  }
  if (subtype === "api_retry") {
    rejectMessageKeys(message, ["type", "subtype", "runId", "sessionId", "attempt", "maxRetries", "retryDelayMs", "errorStatus", "error", "metadata"]);
    requireNumber(message, "attempt");
    requireNumber(message, "maxRetries");
    requireNumber(message, "retryDelayMs");
    optionalNumberOrNull(message, "errorStatus");
    requireObject(message, "error");
    requireObject(message, "metadata");
    return;
  }
  if (subtype === "model_recovery") {
    rejectMessageKeys(message, ["type", "subtype", "runId", "sessionId", "reason", "attempt", "maxAttempts", "stopReason", "message", "metadata", "uuid"]);
    requireString(message, "reason");
    requireNumber(message, "attempt");
    requireNumber(message, "maxAttempts");
    requireString(message, "stopReason");
    requireString(message, "message");
    requireObject(message, "metadata");
    requireString(message, "uuid");
    return;
  }
  if (subtype === "task_started") {
    rejectMessageKeys(message, ["type", "subtype", "runId", "sessionId", "taskId", "toolUseId", "description", "taskType", "workflowName", "prompt"]);
    requireString(message, "taskId");
    requireString(message, "toolUseId");
    requireString(message, "description");
    requireString(message, "taskType");
    requireString(message, "workflowName");
    requireString(message, "prompt");
    return;
  }
  if (subtype === "task_progress") {
    rejectMessageKeys(message, ["type", "subtype", "runId", "sessionId", "taskId", "toolUseId", "description", "usage", "lastToolName", "summary"]);
    requireString(message, "taskId");
    requireString(message, "toolUseId");
    requireString(message, "description");
    requireObject(message, "usage");
    requireString(message, "lastToolName");
    requireString(message, "summary");
    return;
  }
  if (subtype === "task_notification") {
    rejectMessageKeys(message, ["type", "subtype", "runId", "sessionId", "taskId", "toolUseId", "status", "outputFile", "summary", "usage"]);
    requireString(message, "taskId");
    requireString(message, "toolUseId");
    const status = requireString(message, "status");
    if (!["completed", "failed", "stopped"].includes(status)) throw new Error("task_notification.status is invalid");
    requireString(message, "outputFile");
    requireString(message, "summary");
    requireObject(message, "usage");
    return;
  }
  if (subtype === "files_persisted") {
    rejectMessageKeys(message, ["type", "subtype", "runId", "sessionId", "files", "failed", "processedAt"]);
    requireObjectArray(message, "files");
    requireObjectArray(message, "failed");
    requireString(message, "processedAt");
    return;
  }
  if (subtype === "local_command_output") {
    rejectMessageKeys(message, ["type", "subtype", "runId", "sessionId", "content", "uuid"]);
    requireString(message, "content");
    requireString(message, "uuid");
    return;
  }
  if (subtype === "hook_started") {
    rejectMessageKeys(message, ["type", "subtype", "runId", "sessionId", "hookId", "hookName", "hookEvent", "uuid"]);
    validateHookMessage(message);
    return;
  }
  if (subtype === "hook_progress") {
    rejectMessageKeys(message, ["type", "subtype", "runId", "sessionId", "hookId", "hookName", "hookEvent", "stdout", "stderr", "output", "uuid"]);
    validateHookMessage(message);
    requireString(message, "stdout");
    requireString(message, "stderr");
    requireString(message, "output");
    return;
  }
  if (subtype === "hook_response") {
    rejectMessageKeys(message, ["type", "subtype", "runId", "sessionId", "hookId", "hookName", "hookEvent", "output", "stdout", "stderr", "exitCode", "outcome", "uuid"]);
    validateHookMessage(message);
    requireString(message, "output");
    requireString(message, "stdout");
    requireString(message, "stderr");
    optionalNumberOrNull(message, "exitCode");
    const outcome = requireString(message, "outcome");
    if (!["success", "error", "cancelled"].includes(outcome)) throw new Error("hook_response.outcome is invalid");
    return;
  }
  if (subtype === "elicitation_complete") {
    rejectMessageKeys(message, ["type", "subtype", "runId", "sessionId", "mcpServerName", "elicitationId", "uuid"]);
    requireString(message, "mcpServerName");
    requireString(message, "elicitationId");
    requireString(message, "uuid");
    return;
  }
  if (subtype === "post_turn_summary") {
    validatePostTurnSummaryMessage(message);
    return;
  }
  if (subtype === "session_state_changed") {
    rejectMessageKeys(message, ["type", "subtype", "runId", "sessionId", "state"]);
    const state = requireString(message, "state");
    if (!["idle", "running", "requires_action"].includes(state)) throw new Error("session_state_changed.state is invalid");
    return;
  }
  if (subtype === "status") {
    rejectMessageKeys(message, ["type", "subtype", "runId", "sessionId", "status", "permissionMode", "uuid"]);
    if (message.status !== undefined && message.status !== null) {
      const status = requireString(message, "status");
      if (status !== "compacting") throw new Error("status.status is invalid");
    }
    optionalStringOrNull(message, "permissionMode");
    optionalString(message, "uuid");
    return;
  }
  if (subtype === "compact_boundary") {
    rejectMessageKeys(message, ["type", "subtype", "runId", "sessionId", "compactMetadata", "uuid"]);
    requireObject(message, "compactMetadata");
    requireString(message, "uuid");
    return;
  }
  throw new Error(`unsupported system message subtype ${subtype}`);
}

function validateSystemInitMessage(message: Record<string, unknown>): void {
  rejectMessageKeys(message, [
    "type",
    "subtype",
    "runId",
    "sessionId",
    "agents",
    "apiKeySource",
    "betas",
    "claudeCodeVersion",
    "cwd",
    "tools",
    "mcpServers",
    "model",
    "permissionMode",
    "slashCommands",
    "outputStyle",
    "skills",
    "plugins",
    "fastModeState",
    "uuid"
  ]);
  requireStringArray(message, "agents");
  validateApiKeySource(message);
  requireStringArray(message, "betas");
  requireString(message, "claudeCodeVersion");
  requireString(message, "cwd");
  requireStringArray(message, "tools");
  requireObjectArray(message, "mcpServers");
  requireString(message, "model");
  validatePermissionMode(requireString(message, "permissionMode"), "init.permissionMode");
  requireStringArray(message, "slashCommands");
  requireString(message, "outputStyle");
  requireStringArray(message, "skills");
  requireObjectArray(message, "plugins");
  optionalFastModeState(message);
  requireString(message, "uuid");
}

function validateApiKeySource(message: Record<string, unknown>): void {
  const source = requireString(message, "apiKeySource");
  if (!["user", "project", "org", "temporary", "oauth"].includes(source)) {
    throw new Error("init.apiKeySource is invalid");
  }
}

function validatePostTurnSummaryMessage(message: Record<string, unknown>): void {
  rejectMessageKeys(message, [
    "type",
    "subtype",
    "runId",
    "sessionId",
    "summarizesUuid",
    "statusCategory",
    "statusDetail",
    "isNoteworthy",
    "title",
    "description",
    "recentAction",
    "needsAction",
    "artifactUrls",
    "uuid"
  ]);
  requireString(message, "summarizesUuid");
  const category = requireString(message, "statusCategory");
  if (!["blocked", "waiting", "completed", "review_ready", "failed"].includes(category)) {
    throw new Error("post_turn_summary.statusCategory is invalid");
  }
  requireString(message, "statusDetail");
  requireBoolean(message, "isNoteworthy");
  requireString(message, "title");
  requireString(message, "description");
  requireString(message, "recentAction");
  requireString(message, "needsAction");
  requireStringArray(message, "artifactUrls");
  requireString(message, "uuid");
}

function validateResultMessage(message: Record<string, unknown>): void {
  rejectMessageKeys(message, [
    "type",
    "runId",
    "sessionId",
    "status",
    "subtype",
    "content",
    "result",
    "isError",
    "durationMs",
    "durationApiMs",
    "numTurns",
    "stopReason",
    "totalCostUsd",
    "usage",
    "modelUsage",
    "permissionDenials",
    "structuredOutput",
    "fastModeState",
    "errors",
    "eventCount",
    "uuid"
  ]);
  requireString(message, "runId");
  requireString(message, "sessionId");
  const status = requireString(message, "status");
  if (!["finished", "awaiting_approval", "error", "canceled"].includes(status)) throw new Error("result.status is invalid");
  optionalResultSubtype(message, "subtype");
  requireString(message, "content");
  optionalString(message, "result");
  requireBoolean(message, "isError");
  optionalNumber(message, "durationMs");
  optionalNumber(message, "durationApiMs");
  optionalNumber(message, "numTurns");
  optionalStringOrNull(message, "stopReason");
  optionalNumber(message, "totalCostUsd");
  optionalObject(message, "usage");
  requireNumber(message, "eventCount");
  optionalObject(message, "modelUsage");
  optionalObjectArray(message, "permissionDenials");
  optionalObjectOrNull(message, "fastModeState");
  optionalStringArray(message, "errors");
  optionalString(message, "uuid");
}

function validateHookMessage(message: Record<string, unknown>): void {
  requireString(message, "hookId");
  requireString(message, "hookName");
  requireString(message, "hookEvent");
  requireString(message, "uuid");
}

function rejectMessageKeys(message: Record<string, unknown>, allowedKeys: string[]): void {
  rejectUnknownKeys(message, stringValue(message.type) || "message", allowedKeys);
}

function optionalUserMessagePriority(value: Record<string, unknown>, key: string): void {
  if (value[key] === undefined) return;
  const priority = requireString(value, key);
  if (!["now", "next", "later"].includes(priority)) throw new Error(`${key} is invalid`);
}

function optionalAssistantError(value: Record<string, unknown>, key: string): void {
  if (value[key] === undefined) return;
  const error = requireString(value, key);
  if (![
    "authentication_failed",
    "billing_error",
    "rate_limit",
    "invalid_request",
    "server_error",
    "unknown",
    "max_output_tokens"
  ].includes(error)) {
    throw new Error(`${key} is invalid`);
  }
}

function optionalFastModeState(value: Record<string, unknown>): void {
  if (value.fastModeState === undefined || value.fastModeState === null) return;
  const state = requireString(value, "fastModeState");
  if (!["off", "cooldown", "on"].includes(state)) throw new Error("init.fastModeState is invalid");
}

function optionalResultSubtype(value: Record<string, unknown>, key: string): void {
  if (value[key] === undefined) return;
  const subtype = requireString(value, key);
  if (![
    "success",
    "error_during_execution",
    "error_max_turns",
    "error_max_budget_usd",
    "error_max_structured_output_retries"
  ].includes(subtype)) {
    throw new Error(`${key} is invalid`);
  }
}
