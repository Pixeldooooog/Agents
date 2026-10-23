import type { RuntimeEvent } from "../types/runtimeTypes.js";

export type SdkUserMessage = {
  type: "user_message";
  uuid: string;
  sessionId: string;
  content: string;
  message?: Record<string, unknown>;
  parentToolUseId?: string;
  isSynthetic?: boolean;
  toolUseResult?: unknown;
  priority?: "now" | "next" | "later";
  timestamp?: string;
  isReplay?: boolean;
};

export type SdkRunStartedMessage = {
  type: "run_started";
  runId: string;
  sessionId: string;
  createdAt: number;
};

export type SdkAssistantError =
  | "authentication_failed"
  | "billing_error"
  | "rate_limit"
  | "invalid_request"
  | "server_error"
  | "unknown"
  | "max_output_tokens";

export type SdkAssistantMessage = {
  type: "assistant_message";
  runId: string;
  sessionId: string;
  content: string;
  message?: Record<string, unknown>;
  parentToolUseId?: string;
  error?: SdkAssistantError;
  uuid?: string;
  modelUsage?: Record<string, unknown>;
};

export type SdkToolResultMessage = {
  type: "tool_result";
  runId: string;
  sessionId: string;
  toolName: string;
  toolCallId: string;
  content: string;
  isError: boolean;
};

export type SdkApprovalRequiredMessage = {
  type: "approval_required";
  runId: string;
  sessionId: string;
  approvalId: string;
  toolName: string;
  arguments: Record<string, unknown>;
  reason: string;
};

export type SdkToolProgressStatus =
  | "started"
  | "running"
  | "stalled"
  | "completed"
  | "failed"
  | "awaiting_approval"
  | "denied";

export type SdkToolProgressMessage = {
  type: "tool_progress";
  runId: string;
  sessionId: string;
  toolCallId: string;
  name: string;
  status: SdkToolProgressStatus;
  input: Record<string, unknown>;
  result: Record<string, unknown>;
  activity?: Record<string, unknown>;
  target?: string;
  paths?: string[];
  metadata?: Record<string, unknown>;
  error: string;
  output?: string;
  fullOutput?: string;
  elapsedTimeSeconds?: number;
  totalLines?: number;
  totalBytes?: number;
  taskId?: string;
  timeoutMs?: number;
};

export type SdkSystemInitMessage = {
  type: "system";
  subtype: "init";
  runId: string;
  sessionId: string;
  agents: string[];
  apiKeySource: "user" | "project" | "org" | "temporary" | "oauth";
  betas: string[];
  claudeCodeVersion: string;
  cwd: string;
  tools: string[];
  mcpServers: Array<Record<string, string>>;
  model: string;
  permissionMode: "default" | "acceptEdits" | "bypassPermissions" | "plan" | "dontAsk";
  slashCommands: string[];
  outputStyle: string;
  skills: string[];
  plugins: Array<Record<string, string>>;
  fastModeState?: "off" | "cooldown" | "on" | null;
  uuid: string;
};

export type SdkApiRetryMessage = {
  type: "system";
  subtype: "api_retry";
  runId: string;
  sessionId: string;
  attempt: number;
  maxRetries: number;
  retryDelayMs: number;
  errorStatus?: number | null;
  error: Record<string, unknown>;
  metadata: Record<string, unknown>;
};

export type SdkModelRecoveryMessage = {
  type: "system";
  subtype: "model_recovery";
  runId: string;
  sessionId: string;
  reason: string;
  attempt: number;
  maxAttempts: number;
  stopReason: string;
  message: string;
  metadata: Record<string, unknown>;
  uuid: string;
};

export type SdkTaskStartedMessage = {
  type: "system";
  subtype: "task_started";
  runId: string;
  sessionId: string;
  taskId: string;
  toolUseId: string;
  description: string;
  taskType: string;
  workflowName: string;
  prompt: string;
};

export type SdkTaskProgressMessage = {
  type: "system";
  subtype: "task_progress";
  runId: string;
  sessionId: string;
  taskId: string;
  toolUseId: string;
  description: string;
  usage: Record<string, number>;
  lastToolName: string;
  summary: string;
};

export type SdkTaskNotificationMessage = {
  type: "system";
  subtype: "task_notification";
  runId: string;
  sessionId: string;
  taskId: string;
  toolUseId: string;
  status: "completed" | "failed" | "stopped";
  outputFile: string;
  summary: string;
  usage: Record<string, number>;
};

export type SdkFilesPersistedMessage = {
  type: "system";
  subtype: "files_persisted";
  runId: string;
  sessionId: string;
  files: Array<{ filename: string; fileId: string }>;
  failed: Array<{ filename: string; error: string }>;
  processedAt: string;
};

export type SdkLocalCommandOutputMessage = {
  type: "system";
  subtype: "local_command_output";
  runId: string;
  sessionId: string;
  content: string;
  uuid: string;
};

export type SdkHookStartedMessage = {
  type: "system";
  subtype: "hook_started";
  runId: string;
  sessionId: string;
  hookId: string;
  hookName: string;
  hookEvent: string;
  uuid: string;
};

export type SdkHookProgressMessage = {
  type: "system";
  subtype: "hook_progress";
  runId: string;
  sessionId: string;
  hookId: string;
  hookName: string;
  hookEvent: string;
  stdout: string;
  stderr: string;
  output: string;
  uuid: string;
};

export type SdkHookResponseMessage = {
  type: "system";
  subtype: "hook_response";
  runId: string;
  sessionId: string;
  hookId: string;
  hookName: string;
  hookEvent: string;
  output: string;
  stdout: string;
  stderr: string;
  exitCode?: number | null;
  outcome: "success" | "error" | "cancelled";
  uuid: string;
};

export type SdkElicitationCompleteMessage = {
  type: "system";
  subtype: "elicitation_complete";
  runId: string;
  sessionId: string;
  mcpServerName: string;
  elicitationId: string;
  uuid: string;
};

export type SdkPostTurnSummaryMessage = {
  type: "system";
  subtype: "post_turn_summary";
  runId: string;
  sessionId: string;
  summarizesUuid: string;
  statusCategory: "blocked" | "waiting" | "completed" | "review_ready" | "failed";
  statusDetail: string;
  isNoteworthy: boolean;
  title: string;
  description: string;
  recentAction: string;
  needsAction: string;
  artifactUrls: string[];
  uuid: string;
};

export type SdkSessionStateChangedMessage = {
  type: "system";
  subtype: "session_state_changed";
  runId: string;
  sessionId: string;
  state: "idle" | "running" | "requires_action";
};

export type SdkStatusMessage = {
  type: "system";
  subtype: "status";
  runId: string;
  sessionId: string;
  status?: "compacting" | null;
  permissionMode?: string | null;
  uuid?: string;
};

export type SdkCompactBoundaryMessage = {
  type: "system";
  subtype: "compact_boundary";
  runId: string;
  sessionId: string;
  compactMetadata: Record<string, unknown>;
  uuid: string;
};

export type SdkAuthStatusMessage = {
  type: "auth_status";
  runId: string;
  sessionId: string;
  isAuthenticating: boolean;
  output: string[];
  error: string;
  metadata: Record<string, unknown>;
};

export type SdkRateLimitEventMessage = {
  type: "rate_limit_event";
  runId: string;
  sessionId: string;
  rateLimitInfo: Record<string, unknown>;
  uuid: string;
};

export type SdkToolUseSummaryMessage = {
  type: "tool_use_summary";
  runId: string;
  sessionId: string;
  summary: string;
  precedingToolUseIds: string[];
  uuid: string;
};

export type SdkPromptSuggestionMessage = {
  type: "prompt_suggestion";
  runId: string;
  sessionId: string;
  suggestion: string;
  uuid: string;
};

export type SdkStreamEventMessage = {
  type: "stream_event";
  runId: string;
  sessionId: string;
  event: Record<string, unknown>;
  parentToolUseId?: string;
  uuid: string;
};

export type SdkRuntimeEventMessage = {
  type: "runtime_event";
  runId: string;
  sessionId: string;
  event: RuntimeEvent;
};

export type SdkResultSubtype =
  | "success"
  | "error_during_execution"
  | "error_max_turns"
  | "error_max_budget_usd"
  | "error_max_structured_output_retries";

export type SdkResultMessage = {
  type: "result";
  runId: string;
  sessionId: string;
  status: "finished" | "awaiting_approval" | "error" | "canceled";
  subtype?: SdkResultSubtype;
  content: string;
  result?: string;
  isError: boolean;
  durationMs?: number;
  durationApiMs?: number;
  numTurns?: number;
  stopReason?: string | null;
  totalCostUsd?: number;
  usage?: Record<string, unknown>;
  modelUsage?: Record<string, unknown>;
  permissionDenials?: Array<Record<string, unknown>>;
  structuredOutput?: unknown;
  fastModeState?: Record<string, unknown> | null;
  errors?: string[];
  eventCount: number;
  uuid?: string;
};

export type SdkSystemMessage =
  | SdkSystemInitMessage
  | SdkApiRetryMessage
  | SdkModelRecoveryMessage
  | SdkTaskStartedMessage
  | SdkTaskProgressMessage
  | SdkTaskNotificationMessage
  | SdkFilesPersistedMessage
  | SdkLocalCommandOutputMessage
  | SdkHookStartedMessage
  | SdkHookProgressMessage
  | SdkHookResponseMessage
  | SdkElicitationCompleteMessage
  | SdkPostTurnSummaryMessage
  | SdkSessionStateChangedMessage
  | SdkStatusMessage
  | SdkCompactBoundaryMessage;

export type SdkMessage =
  | SdkUserMessage
  | SdkRunStartedMessage
  | SdkAssistantMessage
  | SdkToolResultMessage
  | SdkApprovalRequiredMessage
  | SdkToolProgressMessage
  | SdkSystemMessage
  | SdkAuthStatusMessage
  | SdkRateLimitEventMessage
  | SdkToolUseSummaryMessage
  | SdkPromptSuggestionMessage
  | SdkStreamEventMessage
  | SdkRuntimeEventMessage
  | SdkResultMessage;
