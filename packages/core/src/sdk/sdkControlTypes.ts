import type { SdkMessage, SdkUserMessage } from "./sdkMessages.js";
import type { SdkPermissionModeInput } from "./sdkPermissionModes.js";

export type { SdkPermissionMode, SdkPermissionModeInput } from "./sdkPermissionModes.js";
export type SdkMcpMessageHandler = (message: unknown) => unknown | Promise<unknown>;
export type SdkHookCallbackRequest = Extract<SdkControlRequestPayload, { subtype: "hook_callback" }>;
export type SdkElicitationRequest = Extract<SdkControlRequestPayload, { subtype: "elicitation" }>;
export type SdkElicitationResponse = {
  action: "accept" | "decline" | "cancel";
  content?: Record<string, unknown>;
};
export type SdkHookCallbackHandler = (request: SdkHookCallbackRequest) => Record<string, unknown> | undefined | Promise<Record<string, unknown> | undefined>;
export type SdkElicitationHandler = (request: SdkElicitationRequest) => SdkElicitationResponse | undefined | Promise<SdkElicitationResponse | undefined>;

export type SdkControlHookCallbackMatcher = {
  matcher?: string | null;
  hookCallbackIds?: string[];
  timeout?: number | null;
};

export type SdkControlInitializeRequest = {
  subtype: "initialize";
  hooks?: Record<string, SdkControlHookCallbackMatcher[]> | null;
  sdkMcpServers?: string[] | null;
  jsonSchema?: Record<string, unknown> | null;
  systemPrompt?: string | null;
  appendSystemPrompt?: string | null;
  agents?: Record<string, unknown> | null;
  promptSuggestions?: boolean | null;
  agentProgressSummaries?: boolean | null;
};

export type SdkControlPermissionRequest = {
  subtype: "can_use_tool";
  toolName: string;
  input?: Record<string, unknown>;
  permissionSuggestions?: Array<Record<string, unknown>> | null;
  blockedPath?: string | null;
  decisionReason?: string | null;
  title?: string | null;
  displayName?: string | null;
  toolUseId: string;
  agentId?: string | null;
  description?: string | null;
};

export type SdkMcpServerConfig = {
  type?: string;
  transport?: string;
  command?: string;
  args?: string[];
  url?: string;
  headers?: Record<string, unknown>;
  authToken?: string;
  authRequired?: boolean;
  authUrl?: string;
  authStatus?: string;
  authMessage?: string;
  executionMode?: string;
  sandboxProfile?: string;
  enabled?: boolean;
};

export type SdkControlRequestPayload =
  | SdkControlInitializeRequest
  | SdkControlPermissionRequest
  | { subtype: "interrupt" }
  | { subtype: "set_permission_mode"; mode: SdkPermissionModeInput; ultraplan?: boolean | null }
  | { subtype: "set_model"; model?: string | null }
  | { subtype: "set_max_thinking_tokens"; maxThinkingTokens?: number | null }
  | { subtype: "mcp_status" }
  | { subtype: "get_context_usage" }
  | { subtype: "rewind_files"; userMessageId: string; dryRun?: boolean | null }
  | { subtype: "cancel_async_message"; messageUuid: string }
  | { subtype: "seed_read_state"; path: string; mtime: number }
  | { subtype: "hook_callback"; callbackId: string; input?: Record<string, unknown>; toolUseId?: string | null }
  | { subtype: "mcp_message"; serverName: string; message: unknown }
  | { subtype: "mcp_set_servers"; servers?: Record<string, SdkMcpServerConfig> }
  | { subtype: "reload_plugins" }
  | { subtype: "mcp_reconnect"; serverName: string }
  | { subtype: "mcp_toggle"; serverName: string; enabled: boolean }
  | { subtype: "stop_task"; taskId: string }
  | { subtype: "apply_flag_settings"; settings?: Record<string, unknown> }
  | { subtype: "get_settings" }
  | {
      subtype: "elicitation";
      mcpServerName: string;
      message: string;
      mode?: "form" | "url" | null;
      url?: string | null;
      elicitationId?: string | null;
      requestedSchema?: Record<string, unknown> | null;
    };

export type SdkControlRequestMessage = {
  type: "control_request";
  requestId: string;
  request: SdkControlRequestPayload;
};

export type SdkControlSuccessResponse = {
  subtype: "success";
  requestId: string;
  response?: Record<string, unknown> | null;
};

export type SdkControlErrorResponse = {
  subtype: "error";
  requestId: string;
  error: string;
  pendingPermissionRequests?: SdkControlRequestMessage[] | null;
};

export type SdkControlResponseMessage = {
  type: "control_response";
  response: SdkControlSuccessResponse | SdkControlErrorResponse;
};

export type SdkControlCancelRequestMessage = {
  type: "control_cancel_request";
  requestId: string;
};

export type SdkKeepAliveMessage = {
  type: "keep_alive";
};

export type SdkUpdateEnvironmentVariablesMessage = {
  type: "update_environment_variables";
  variables?: Record<string, string>;
};

export type SdkControlMessage =
  | SdkControlRequestMessage
  | SdkControlResponseMessage
  | SdkControlCancelRequestMessage
  | SdkKeepAliveMessage
  | SdkUpdateEnvironmentVariablesMessage;

export type SdkWireMessage = SdkMessage | SdkControlMessage;
export type SdkWireInputMessage = SdkWireMessage | Record<string, unknown>;
export type SdkStdinMessage =
  | SdkUserMessage
  | SdkControlRequestMessage
  | SdkControlResponseMessage
  | SdkKeepAliveMessage
  | SdkUpdateEnvironmentVariablesMessage;
export type SdkStdoutMessage =
  | SdkMessage
  | SdkControlRequestMessage
  | SdkControlResponseMessage
  | SdkControlCancelRequestMessage
  | SdkKeepAliveMessage;

export function createSdkControlRequest(
  request: SdkControlRequestPayload,
  requestId = newSdkControlRequestId()
): SdkControlRequestMessage {
  return { type: "control_request", requestId, request };
}

export function createSdkControlSuccessResponse(
  requestId: string,
  response: Record<string, unknown> | null = {}
): SdkControlResponseMessage {
  return { type: "control_response", response: { subtype: "success", requestId, response } };
}

export function createSdkControlErrorResponse(
  requestId: string,
  error: string,
  pendingPermissionRequests?: SdkControlRequestMessage[]
): SdkControlResponseMessage {
  return {
    type: "control_response",
    response: {
      subtype: "error",
      requestId,
      error,
      ...(pendingPermissionRequests ? { pendingPermissionRequests } : {})
    }
  };
}

export function createSdkControlCancelRequest(requestId: string): SdkControlCancelRequestMessage {
  return { type: "control_cancel_request", requestId };
}

export function isSdkControlResponse(message: SdkWireMessage): message is SdkControlResponseMessage {
  return message.type === "control_response";
}

export function isSdkPermissionControlRequest(message: SdkControlRequestMessage): boolean {
  return message.request.subtype === "can_use_tool";
}

function newSdkControlRequestId(): string {
  return `control_${crypto.randomUUID().replaceAll("-", "")}`;
}
