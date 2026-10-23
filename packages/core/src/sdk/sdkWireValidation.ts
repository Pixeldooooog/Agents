import type {
  SdkControlCancelRequestMessage,
  SdkControlRequestMessage,
  SdkControlResponseMessage,
  SdkStdinMessage,
  SdkStdoutMessage,
  SdkWireMessage
} from "./sdkControlTypes.js";
import type { SdkMessage } from "./sdkMessages.js";
import { validatePermissionMode, validateSdkMessageFrame } from "./sdkMessageValidation.js";
import { normalizeSdkWireMessage } from "./sdkWireNormalization.js";
import {
  objectValue,
  optionalBoolean,
  optionalBooleanOrNull,
  optionalNumber,
  optionalNumberOrNull,
  optionalObject,
  optionalObjectArray,
  optionalObjectArrayOrNull,
  optionalObjectOrNull,
  optionalString,
  optionalStringArray,
  optionalStringArrayOrNull,
  optionalStringOrNull,
  rejectUnknownKeys,
  requireBoolean,
  requireFrameObject,
  requireNumber,
  requireObject,
  requireString,
  requireStringRecord,
  stringValue
} from "./sdkWireValidationFields.js";

export function validateSdkWireMessage(value: unknown): SdkWireMessage {
  const message = normalizeSdkWireMessage(requireFrameObject(value));
  const messageType = stringValue(message.type);
  if (!messageType) throw new Error("missing message type");

  if (validateSdkMessageFrame(message, messageType)) return message as SdkWireMessage;
  if (messageType === "control_request") {
    rejectUnknownKeys(message, "control_request", ["type", "requestId", "request"]);
    requireString(message, "requestId");
    validateControlRequestPayload(requireObject(message, "request"));
    return message as SdkWireMessage;
  }
  if (messageType === "control_response") {
    rejectUnknownKeys(message, "control_response", ["type", "response"]);
    validateControlResponsePayload(requireObject(message, "response"));
    return message as SdkWireMessage;
  }
  if (messageType === "control_cancel_request") {
    rejectUnknownKeys(message, "control_cancel_request", ["type", "requestId"]);
    requireString(message, "requestId");
    return message as SdkWireMessage;
  }
  if (messageType === "keep_alive") {
    rejectUnknownKeys(message, "keep_alive", ["type"]);
    return message as SdkWireMessage;
  }
  if (messageType === "update_environment_variables") {
    rejectUnknownKeys(message, "update_environment_variables", ["type", "variables"]);
    requireStringRecord(message, "variables");
    return message as SdkWireMessage;
  }

  throw new Error(`unsupported message type ${messageType}`);
}

export function validateSdkControlRequest(value: unknown): SdkControlRequestMessage {
  const message = validateSdkWireMessage(value);
  if (message.type !== "control_request") throw new Error("expected SDK control_request message");
  return message;
}

export function validateSdkMessage(value: unknown): SdkMessage {
  const message = validateSdkWireMessage(value);
  if (isSdkProtocolControlMessage(message)) throw new Error("expected SDK stream message");
  return message as SdkMessage;
}

export function validateSdkControlResponse(value: unknown): SdkControlResponseMessage {
  const message = validateSdkWireMessage(value);
  if (message.type !== "control_response") throw new Error("expected SDK control_response message");
  return message;
}

export function validateSdkControlCancelRequest(value: unknown): SdkControlCancelRequestMessage {
  const message = validateSdkWireMessage(value);
  if (message.type !== "control_cancel_request") throw new Error("expected SDK control_cancel_request message");
  return message;
}

export function validateSdkStdinMessage(value: unknown): SdkStdinMessage {
  const message = validateSdkWireMessage(value);
  if (message.type === "control_cancel_request") throw new Error("control_cancel_request is not a valid SDK stdin message");
  if (message.type === "user_message" || message.type === "control_request" || message.type === "control_response" ||
    message.type === "keep_alive" || message.type === "update_environment_variables") {
    return message;
  }
  throw new Error(`${message.type} is not a valid SDK stdin message`);
}

export function validateSdkStdoutMessage(value: unknown): SdkStdoutMessage {
  const message = validateSdkWireMessage(value);
  if (message.type === "update_environment_variables") {
    throw new Error("update_environment_variables is not a valid SDK stdout message");
  }
  return message;
}

export const validate_sdk_message = validateSdkMessage;
export const validate_sdk_control_request = validateSdkControlRequest;
export const validate_sdk_control_response = validateSdkControlResponse;
export const validate_sdk_stdin_message = validateSdkStdinMessage;
export const validate_sdk_stdout_message = validateSdkStdoutMessage;

function validateControlRequestPayload(request: Record<string, unknown>): void {
  const subtype = requireString(request, "subtype");
  if (subtype === "initialize") {
    rejectControlRequestKeys(request, [
      "subtype",
      "hooks",
      "sdkMcpServers",
      "jsonSchema",
      "systemPrompt",
      "appendSystemPrompt",
      "agents",
      "promptSuggestions",
      "agentProgressSummaries"
    ]);
    optionalObjectOrNull(request, "hooks");
    optionalStringArrayOrNull(request, "sdkMcpServers");
    optionalObjectOrNull(request, "jsonSchema");
    optionalStringOrNull(request, "systemPrompt");
    optionalStringOrNull(request, "appendSystemPrompt");
    optionalObjectOrNull(request, "agents");
    optionalBooleanOrNull(request, "promptSuggestions");
    optionalBooleanOrNull(request, "agentProgressSummaries");
    return;
  }
  if (subtype === "interrupt" || subtype === "mcp_status" || subtype === "get_context_usage" ||
    subtype === "reload_plugins" || subtype === "get_settings") {
    rejectControlRequestKeys(request, ["subtype"]);
    return;
  }
  if (subtype === "can_use_tool") {
    rejectControlRequestKeys(request, [
      "subtype",
      "toolName",
      "input",
      "permissionSuggestions",
      "blockedPath",
      "decisionReason",
      "title",
      "displayName",
      "toolUseId",
      "agentId",
      "description"
    ]);
    requireString(request, "toolName");
    requireString(request, "toolUseId");
    optionalObject(request, "input");
    optionalObjectArrayOrNull(request, "permissionSuggestions");
    optionalStringOrNull(request, "blockedPath");
    optionalStringOrNull(request, "decisionReason");
    optionalStringOrNull(request, "title");
    optionalStringOrNull(request, "displayName");
    optionalStringOrNull(request, "agentId");
    optionalStringOrNull(request, "description");
    return;
  }
  if (subtype === "set_permission_mode") {
    rejectControlRequestKeys(request, ["subtype", "mode", "ultraplan"]);
    validatePermissionMode(requireString(request, "mode"), "set_permission_mode.mode");
    optionalBooleanOrNull(request, "ultraplan");
    return;
  }
  if (subtype === "set_model") {
    rejectControlRequestKeys(request, ["subtype", "model"]);
    optionalStringOrNull(request, "model");
    return;
  }
  if (subtype === "set_max_thinking_tokens") {
    rejectControlRequestKeys(request, ["subtype", "maxThinkingTokens"]);
    optionalNumberOrNull(request, "maxThinkingTokens");
    return;
  }
  if (subtype === "rewind_files") {
    rejectControlRequestKeys(request, ["subtype", "userMessageId", "dryRun"]);
    requireString(request, "userMessageId");
    optionalBooleanOrNull(request, "dryRun");
    return;
  }
  if (subtype === "cancel_async_message") {
    rejectControlRequestKeys(request, ["subtype", "messageUuid"]);
    requireString(request, "messageUuid");
    return;
  }
  if (subtype === "seed_read_state") {
    rejectControlRequestKeys(request, ["subtype", "path", "mtime"]);
    requireString(request, "path");
    requireNumber(request, "mtime");
    return;
  }
  if (subtype === "hook_callback") {
    rejectControlRequestKeys(request, ["subtype", "callbackId", "input", "toolUseId"]);
    requireString(request, "callbackId");
    optionalObject(request, "input");
    optionalStringOrNull(request, "toolUseId");
    return;
  }
  if (subtype === "mcp_message") {
    rejectControlRequestKeys(request, ["subtype", "serverName", "message"]);
    requireString(request, "serverName");
    return;
  }
  if (subtype === "mcp_set_servers") {
    rejectControlRequestKeys(request, ["subtype", "servers"]);
    validateMcpServerConfigs(request);
    return;
  }
  if (subtype === "mcp_reconnect") {
    rejectControlRequestKeys(request, ["subtype", "serverName"]);
    requireString(request, "serverName");
    return;
  }
  if (subtype === "mcp_toggle") {
    rejectControlRequestKeys(request, ["subtype", "serverName", "enabled"]);
    requireString(request, "serverName");
    requireBoolean(request, "enabled");
    return;
  }
  if (subtype === "stop_task") {
    rejectControlRequestKeys(request, ["subtype", "taskId"]);
    requireString(request, "taskId");
    return;
  }
  if (subtype === "apply_flag_settings") {
    rejectControlRequestKeys(request, ["subtype", "settings"]);
    optionalObject(request, "settings");
    return;
  }
  if (subtype === "elicitation") {
    rejectControlRequestKeys(request, [
      "subtype",
      "mcpServerName",
      "message",
      "mode",
      "url",
      "elicitationId",
      "requestedSchema"
    ]);
    requireString(request, "mcpServerName");
    requireString(request, "message");
    optionalElicitationMode(request);
    optionalStringOrNull(request, "url");
    optionalStringOrNull(request, "elicitationId");
    optionalObjectOrNull(request, "requestedSchema");
    return;
  }
  throw new Error(`unsupported control request subtype ${subtype}`);
}

function isSdkProtocolControlMessage(message: SdkWireMessage): boolean {
  return message.type === "control_request" ||
    message.type === "control_response" ||
    message.type === "control_cancel_request" ||
    message.type === "keep_alive" ||
    message.type === "update_environment_variables";
}

function validateControlResponsePayload(response: Record<string, unknown>): void {
  const subtype = requireString(response, "subtype");
  requireString(response, "requestId");
  if (subtype === "success") {
    rejectUnknownKeys(response, "control_response.response", ["subtype", "requestId", "response"]);
    optionalObjectOrNull(response, "response");
    return;
  }
  if (subtype === "error") {
    rejectUnknownKeys(response, "control_response.response", [
      "subtype",
      "requestId",
      "error",
      "pendingPermissionRequests"
    ]);
    requireString(response, "error");
    const pendingPermissionRequests = response.pendingPermissionRequests;
    if (pendingPermissionRequests !== undefined && pendingPermissionRequests !== null) {
      if (!Array.isArray(pendingPermissionRequests)) {
        throw new Error("pendingPermissionRequests must be an object array");
      }
      for (const [index, request] of pendingPermissionRequests.entries()) {
        validateSdkControlRequest(request);
        if ((request as Record<string, unknown>).type !== "control_request") {
          throw new Error(`pendingPermissionRequests.${index} must be a control_request`);
        }
      }
    }
    return;
  }
  throw new Error(`unsupported control response subtype ${subtype}`);
}

function rejectControlRequestKeys(request: Record<string, unknown>, allowedKeys: string[]): void {
  rejectUnknownKeys(request, `control_request.${stringValue(request.subtype) || "request"}`, allowedKeys);
}

function optionalElicitationMode(request: Record<string, unknown>): void {
  if (request.mode === undefined || request.mode === null) return;
  const mode = requireString(request, "mode");
  if (mode !== "form" && mode !== "url") throw new Error("elicitation.mode is invalid");
}

function validateMcpServerConfigs(request: Record<string, unknown>): void {
  if (request.servers === undefined) return;
  const servers = requireObject(request, "servers");
  for (const [name, rawConfig] of Object.entries(servers)) {
    if (!name.trim()) throw new Error("mcp_set_servers server name must be non-empty");
    validateMcpServerConfig(name, objectValue(rawConfig));
  }
}

function validateMcpServerConfig(name: string, config: Record<string, unknown> | undefined): void {
  if (!config) throw new Error(`mcp_set_servers.${name} must be an object`);
  optionalString(config, "transport");
  optionalString(config, "command");
  optionalStringArray(config, "args");
  optionalString(config, "url");
  optionalObject(config, "headers");
  optionalString(config, "authToken");
  optionalBoolean(config, "authRequired");
  optionalString(config, "authUrl");
  optionalString(config, "authStatus");
  optionalString(config, "authMessage");
  optionalString(config, "executionMode");
  optionalString(config, "sandboxProfile");
  optionalBoolean(config, "enabled");
}
