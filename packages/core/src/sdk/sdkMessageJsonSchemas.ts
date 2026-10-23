import {
  booleanSchema,
  constSchema,
  emptyRecordSchema,
  enumSchema,
  nullable,
  numberSchema,
  objectArraySchema,
  oneOf,
  strictObject,
  stringArraySchema,
  stringSchema
} from "./sdkJsonSchemaBuilders.js";
import { systemMessageSchema } from "./sdkSystemMessageJsonSchemas.js";

export const userMessageSchema = strictObject({
  type: constSchema("user_message"),
  uuid: stringSchema,
  sessionId: stringSchema,
  content: stringSchema,
  message: emptyRecordSchema,
  parentToolUseId: stringSchema,
  isSynthetic: booleanSchema,
  toolUseResult: {},
  priority: enumSchema(["now", "next", "later"]),
  timestamp: stringSchema,
  isReplay: booleanSchema
}, ["type", "uuid", "sessionId", "content"]);

export const sdkResultMessageSchema = strictObject({
  type: constSchema("result"),
  runId: stringSchema,
  sessionId: stringSchema,
  status: enumSchema(["finished", "awaiting_approval", "error", "canceled"]),
  content: stringSchema,
  isError: booleanSchema,
  eventCount: numberSchema,
  subtype: stringSchema,
  durationMs: numberSchema,
  durationApiMs: numberSchema,
  numTurns: numberSchema,
  result: stringSchema,
  stopReason: nullable(stringSchema),
  totalCostUsd: numberSchema,
  usage: emptyRecordSchema,
  modelUsage: emptyRecordSchema,
  permissionDenials: objectArraySchema,
  structuredOutput: {},
  fastModeState: nullable(emptyRecordSchema),
  errors: stringArraySchema,
  uuid: stringSchema
}, ["type", "runId", "sessionId", "status", "content", "isError", "eventCount"]);

export const sdkSessionInfoSchema = strictObject({
  sessionId: stringSchema,
  summary: stringSchema,
  lastModified: numberSchema,
  fileSize: nullable(numberSchema),
  customTitle: nullable(stringSchema),
  firstPrompt: nullable(stringSchema),
  gitBranch: nullable(stringSchema),
  cwd: nullable(stringSchema),
  tag: nullable(stringSchema),
  createdAt: nullable(numberSchema),
  status: stringSchema,
  latestRunId: stringSchema,
  runIds: stringArraySchema,
  runCount: numberSchema,
  metadata: emptyRecordSchema
}, ["sessionId", "summary", "lastModified"]);

const toolProgressMessageSchema = strictObject({
  type: constSchema("tool_progress"),
  runId: stringSchema,
  sessionId: stringSchema,
  toolCallId: stringSchema,
  name: stringSchema,
  status: enumSchema(["started", "running", "stalled", "completed", "failed", "awaiting_approval", "denied"]),
  input: emptyRecordSchema,
  result: emptyRecordSchema,
  activity: emptyRecordSchema,
  target: stringSchema,
  paths: stringArraySchema,
  metadata: emptyRecordSchema,
  error: stringSchema,
  output: stringSchema,
  fullOutput: stringSchema,
  elapsedTimeSeconds: numberSchema,
  totalLines: numberSchema,
  totalBytes: numberSchema,
  taskId: stringSchema,
  timeoutMs: numberSchema
}, ["type", "runId", "sessionId", "toolCallId", "name", "status", "input", "result", "error"]);

const authStatusMessageSchema = strictObject({
  type: constSchema("auth_status"),
  runId: stringSchema,
  sessionId: stringSchema,
  isAuthenticating: booleanSchema,
  output: stringArraySchema,
  error: stringSchema,
  metadata: emptyRecordSchema
}, ["type", "runId", "sessionId", "isAuthenticating", "output", "error", "metadata"]);

const rateLimitEventMessageSchema = strictObject({
  type: constSchema("rate_limit_event"),
  runId: stringSchema,
  sessionId: stringSchema,
  rateLimitInfo: emptyRecordSchema,
  uuid: stringSchema
}, ["type", "runId", "sessionId", "rateLimitInfo", "uuid"]);

const toolUseSummaryMessageSchema = strictObject({
  type: constSchema("tool_use_summary"),
  runId: stringSchema,
  sessionId: stringSchema,
  summary: stringSchema,
  precedingToolUseIds: stringArraySchema,
  uuid: stringSchema
}, ["type", "runId", "sessionId", "summary", "precedingToolUseIds", "uuid"]);

const promptSuggestionMessageSchema = strictObject({
  type: constSchema("prompt_suggestion"),
  runId: stringSchema,
  sessionId: stringSchema,
  suggestion: stringSchema,
  uuid: stringSchema
}, ["type", "runId", "sessionId", "suggestion", "uuid"]);

const streamEventMessageSchema = strictObject({
  type: constSchema("stream_event"),
  runId: stringSchema,
  sessionId: stringSchema,
  event: emptyRecordSchema,
  parentToolUseId: stringSchema,
  uuid: stringSchema
}, ["type", "runId", "sessionId", "event", "uuid"]);

const runtimeEventMessageSchema = strictObject({
  type: constSchema("runtime_event"),
  runId: stringSchema,
  sessionId: stringSchema,
  event: emptyRecordSchema
}, ["type", "runId", "sessionId", "event"]);

export const sdkMessageSchema = oneOf([
  userMessageSchema,
  strictObject({
    type: constSchema("run_started"),
    runId: stringSchema,
    sessionId: stringSchema,
    createdAt: numberSchema
  }, ["type", "runId", "sessionId", "createdAt"]),
  strictObject({
    type: constSchema("assistant_message"),
    runId: stringSchema,
    sessionId: stringSchema,
    content: stringSchema,
    message: emptyRecordSchema,
    parentToolUseId: stringSchema,
    error: enumSchema(["authentication_failed", "billing_error", "rate_limit", "invalid_request", "server_error", "unknown", "max_output_tokens"]),
    uuid: stringSchema,
    modelUsage: emptyRecordSchema
  }, ["type", "runId", "sessionId", "content"]),
  strictObject({
    type: constSchema("tool_result"),
    runId: stringSchema,
    sessionId: stringSchema,
    toolName: stringSchema,
    toolCallId: stringSchema,
    content: stringSchema,
    isError: booleanSchema
  }, ["type", "runId", "sessionId", "toolName", "toolCallId", "content", "isError"]),
  strictObject({
    type: constSchema("approval_required"),
    runId: stringSchema,
    sessionId: stringSchema,
    approvalId: stringSchema,
    toolName: stringSchema,
    arguments: emptyRecordSchema,
    reason: stringSchema
  }, ["type", "runId", "sessionId", "approvalId", "toolName", "arguments", "reason"]),
  toolProgressMessageSchema,
  authStatusMessageSchema,
  rateLimitEventMessageSchema,
  toolUseSummaryMessageSchema,
  promptSuggestionMessageSchema,
  streamEventMessageSchema,
  runtimeEventMessageSchema,
  sdkResultMessageSchema,
  systemMessageSchema
]);
