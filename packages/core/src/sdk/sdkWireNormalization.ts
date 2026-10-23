import { newSdkUserMessageUuid } from "./sdkUserMessageIds.js";
import { normalizeSdkPermissionMode } from "./sdkPermissionModes.js";

export function normalizeSdkWireMessage(message: Record<string, unknown>): Record<string, unknown> {
  const normalized = { ...message };
  const messageType = stringValue(normalized.type);
  if (messageType === "user" || messageType === "user_message") {
    return normalizeUserMessage(normalized);
  }
  if (messageType === "control_request") {
    normalizeAlias(normalized, "requestId", "request_id");
    const request = objectValue(normalized.request);
    if (request) normalized.request = normalizeControlRequestPayload(request);
  } else if (messageType === "control_response") {
    const response = objectValue(normalized.response);
    if (response) normalized.response = normalizeControlResponse(response);
  } else if (messageType === "control_cancel_request") {
    normalizeAlias(normalized, "requestId", "request_id");
  } else if (messageType === "update_environment_variables" && normalized.variables === undefined) {
    normalized.variables = {};
  }
  return normalized;
}

export function normalizeSdkControlMessageKeys(message: unknown): unknown {
  const record = objectValue(message);
  return record ? normalizeSdkWireMessage(record) : message;
}

export const normalize_sdk_control_message_keys = normalizeSdkControlMessageKeys;

function normalizeUserMessage(message: Record<string, unknown>): Record<string, unknown> {
  const normalized: Record<string, unknown> = { ...message, type: "user_message" };
  normalizeAlias(normalized, "sessionId", "session_id");
  normalizeAlias(normalized, "isReplay", "is_replay");
  normalizeAlias(normalized, "parentToolUseId", "parent_tool_use_id");
  normalizeAlias(normalized, "toolUseResult", "tool_use_result");
  normalizeAlias(normalized, "isSynthetic", "is_synthetic");
  normalized.uuid = stringValue(normalized.uuid) || newSdkUserMessageUuid();
  normalized.content = stringValue(normalized.content) || messageContentText(objectValue(normalized.message));
  return normalized;
}

function normalizeControlRequestPayload(request: Record<string, unknown>): Record<string, unknown> {
  const normalized = { ...request };
  const subtype = stringValue(normalized.subtype);
  if (subtype === "initialize") {
    normalizeAlias(normalized, "sdkMcpServers", "sdk_mcp_servers");
    normalizeAlias(normalized, "jsonSchema", "json_schema");
    normalizeAlias(normalized, "systemPrompt", "system_prompt");
    normalizeAlias(normalized, "appendSystemPrompt", "append_system_prompt");
    normalizeAlias(normalized, "promptSuggestions", "prompt_suggestions");
    normalizeAlias(normalized, "agentProgressSummaries", "agent_progress_summaries");
  } else if (subtype === "can_use_tool") {
    normalizeAlias(normalized, "toolName", "tool_name");
    normalizeAlias(normalized, "permissionSuggestions", "permission_suggestions");
    normalizeAlias(normalized, "blockedPath", "blocked_path");
    normalizeAlias(normalized, "decisionReason", "decision_reason");
    normalizeAlias(normalized, "displayName", "display_name");
    normalizeAlias(normalized, "toolUseId", "tool_use_id");
    normalizeAlias(normalized, "agentId", "agent_id");
  } else if (subtype === "set_permission_mode") {
    const mode = normalizeSdkPermissionMode(normalized.mode);
    if (mode) normalized.mode = mode;
  } else if (subtype === "set_max_thinking_tokens") {
    normalizeAlias(normalized, "maxThinkingTokens", "max_thinking_tokens");
  } else if (subtype === "rewind_files") {
    normalizeAlias(normalized, "userMessageId", "user_message_id");
    normalizeAlias(normalized, "dryRun", "dry_run");
  } else if (subtype === "cancel_async_message") {
    normalizeAlias(normalized, "messageUuid", "message_uuid");
  } else if (subtype === "hook_callback") {
    normalizeAlias(normalized, "callbackId", "callback_id");
    normalizeAlias(normalized, "toolUseId", "tool_use_id");
  } else if (subtype === "mcp_message") {
    normalizeAlias(normalized, "serverName", "server_name");
  } else if (subtype === "mcp_set_servers") {
    const servers = objectValue(normalized.servers);
    if (servers) normalized.servers = normalizeMcpServerConfigAliases(servers);
  } else if (subtype === "mcp_reconnect" || subtype === "mcp_toggle") {
    normalizeAlias(normalized, "serverName", "server_name");
  } else if (subtype === "stop_task") {
    normalizeAlias(normalized, "taskId", "task_id");
  } else if (subtype === "elicitation") {
    normalizeAlias(normalized, "mcpServerName", "mcp_server_name");
    normalizeAlias(normalized, "elicitationId", "elicitation_id");
    normalizeAlias(normalized, "requestedSchema", "requested_schema");
  }
  return normalized;
}

function normalizeControlResponse(response: Record<string, unknown>): Record<string, unknown> {
  const normalized = { ...response };
  normalizeAlias(normalized, "requestId", "request_id");
  normalizeAlias(normalized, "pendingPermissionRequests", "pending_permission_requests");
  const pending = normalized.pendingPermissionRequests;
  if (Array.isArray(pending)) {
    normalized.pendingPermissionRequests = pending.map((request) => {
      const requestObject = objectValue(request);
      return requestObject ? normalizeSdkWireMessage(requestObject) : request;
    });
  }
  return normalized;
}

function normalizeMcpServerConfigAliases(servers: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(Object.entries(servers).map(([name, rawConfig]) => {
    const config = objectValue(rawConfig);
    if (!config) return [name, rawConfig];
    const normalized = { ...config };
    normalizeAlias(normalized, "transport", "type");
    normalizeAlias(normalized, "authToken", "auth_token");
    normalizeAlias(normalized, "authRequired", "auth_required");
    normalizeAlias(normalized, "authUrl", "auth_url");
    normalizeAlias(normalized, "authStatus", "auth_status");
    normalizeAlias(normalized, "authMessage", "auth_message");
    normalizeAlias(normalized, "executionMode", "execution_mode");
    normalizeAlias(normalized, "sandboxProfile", "sandbox_profile");
    return [name, normalized];
  }));
}

function normalizeAlias(target: Record<string, unknown>, canonicalKey: string, ...aliasKeys: string[]): void {
  for (const aliasKey of aliasKeys) {
    if (target[canonicalKey] === undefined && target[aliasKey] !== undefined) {
      target[canonicalKey] = target[aliasKey];
    }
    delete target[aliasKey];
  }
}

function objectValue(value: unknown): Record<string, unknown> | undefined {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : undefined;
}

function stringValue(value: unknown): string | undefined {
  return typeof value === "string" ? value : undefined;
}

function messageContentText(message: Record<string, unknown> | undefined): string {
  const content = message?.content;
  if (typeof content === "string") return content;
  if (!Array.isArray(content)) return "";
  return content.map((item) => {
    const block = objectValue(item);
    return block?.type === "text" ? String(block.text || "") : "";
  }).join("");
}
