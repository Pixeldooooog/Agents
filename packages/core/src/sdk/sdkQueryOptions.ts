import type { AgentChatPayload } from "../types/agentTypes.js";
import type { SdkPermissionModeInput } from "./sdkPermissionModes.js";
import { sdkPermissionProfileForMode } from "./sdkPermissionModes.js";

export type SdkOutputFormat = {
  type?: string;
  schema?: Record<string, unknown>;
  [key: string]: unknown;
};

export type SdkQueryOptions = {
  sessionId?: string;
  session_id?: string;
  protocol?: string;
  model?: string;
  baseUrl?: string;
  base_url?: string;
  apiKey?: string;
  api_key?: string;
  cwd?: string;
  systemPrompt?: string;
  system_prompt?: string;
  allowedTools?: string[];
  allowed_tools?: string[];
  enabledTools?: string[];
  enabled_tools?: string[];
  skills?: string[];
  permissionProfile?: string;
  permission_profile?: string;
  permissionMode?: SdkPermissionModeInput;
  permission_mode?: SdkPermissionModeInput;
  approvalRequiredTools?: string[];
  approval_required_tools?: string[];
  deniedTools?: string[];
  denied_tools?: string[];
  maxToolIterations?: number;
  max_tool_iterations?: number;
  maxTurns?: number;
  max_turns?: number;
  maxThinkingTokens?: number;
  max_thinking_tokens?: number;
  tenantId?: string;
  tenant_id?: string;
  userId?: string;
  user_id?: string;
  agentId?: string;
  agent_id?: string;
  workspaceId?: string;
  workspace_id?: string;
  outputFormat?: SdkOutputFormat;
  output_format?: SdkOutputFormat;
  replayUserMessages?: boolean;
  replay_user_messages?: boolean;
  metadata?: Record<string, unknown>;
};

export function chatPayloadFromSdkOptions(message: string, options: SdkQueryOptions = {}): AgentChatPayload {
  const resolvedSessionId = stringOption(options.sessionId ?? options.session_id);
  const resolvedCwd = stringOption(options.cwd);
  const metadata = metadataFromSdkOptions(message, options, resolvedSessionId, resolvedCwd);
  return {
    message,
    protocol: options.protocol,
    model: options.model,
    base_url: stringOption(options.baseUrl ?? options.base_url),
    api_key: stringOption(options.apiKey ?? options.api_key),
    system_prompt: stringOption(options.systemPrompt ?? options.system_prompt),
    enabled_tools: stringListOption(options.enabledTools ?? options.enabled_tools ?? options.allowedTools ?? options.allowed_tools),
    permission_profile: permissionProfileFromSdkOptions(options),
    approval_required_tools: stringListOption(options.approvalRequiredTools ?? options.approval_required_tools),
    denied_tools: stringListOption(options.deniedTools ?? options.denied_tools),
    runtime: runtimeOptionsFromSdkOptions(options),
    tenant_id: stringOption(options.tenantId ?? options.tenant_id),
    user_id: stringOption(options.userId ?? options.user_id),
    agent_id: stringOption(options.agentId ?? options.agent_id),
    workspace_id: stringOption(options.workspaceId ?? options.workspace_id),
    metadata
  };
}

function runtimeOptionsFromSdkOptions(options: SdkQueryOptions): AgentChatPayload["runtime"] {
  const runtime: NonNullable<AgentChatPayload["runtime"]> = {};
  const maxToolIterations = numberOption(
    options.maxToolIterations ?? options.max_tool_iterations ?? options.maxTurns ?? options.max_turns
  );
  const maxThinkingTokens = numberOption(options.maxThinkingTokens ?? options.max_thinking_tokens);
  if (maxToolIterations !== undefined) runtime.maxToolIterations = maxToolIterations;
  if (maxThinkingTokens !== undefined) runtime.maxThinkingTokens = maxThinkingTokens;
  return Object.keys(runtime).length ? runtime : undefined;
}

function metadataFromSdkOptions(
  message: string,
  options: SdkQueryOptions,
  sessionId: string,
  cwd: string
): Record<string, string> {
  const metadata = stringRecord(options.metadata);
  metadata.sdk_prompt = stringOption(options.metadata?.sdk_prompt) || message;
  if (sessionId) metadata.sdk_session_id = sessionId;
  if (cwd) {
    metadata.sdk_cwd = cwd;
    metadata.cwd = cwd;
  }

  const skills = stringListOption(options.skills);
  if (skills.length) {
    metadata.enabled_skills = skills.join(",");
    metadata.sdk_skills = skills.join(",");
  }

  const outputFormat = options.outputFormat || options.output_format;
  const structuredSchema = structuredOutputSchema(outputFormat);
  if (structuredSchema) {
    metadata.structured_output_schema = JSON.stringify(structuredSchema);
    metadata.sdk_output_format = JSON.stringify(outputFormat);
  }

  const replayUserMessages = booleanOption(options.replayUserMessages ?? options.replay_user_messages);
  if (replayUserMessages !== undefined) metadata.replayUserMessages = String(replayUserMessages);
  return metadata;
}

function permissionProfileFromSdkOptions(options: SdkQueryOptions): string {
  const explicitProfile = stringOption(options.permissionProfile ?? options.permission_profile);
  if (explicitProfile) return explicitProfile;
  return sdkPermissionProfileForMode(options.permissionMode ?? options.permission_mode);
}

function structuredOutputSchema(outputFormat: unknown): Record<string, unknown> | undefined {
  if (!outputFormat || typeof outputFormat !== "object" || Array.isArray(outputFormat)) return undefined;
  const record = outputFormat as Record<string, unknown>;
  const schema = record.schema;
  if (record.type !== "json_schema" || !schema || typeof schema !== "object" || Array.isArray(schema)) return undefined;
  return schema as Record<string, unknown>;
}

function stringOption(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function stringListOption(value: unknown): string[] {
  if (Array.isArray(value)) return value.map((item) => String(item).trim()).filter(Boolean);
  if (typeof value === "string") return value.split(",").map((item) => item.trim()).filter(Boolean);
  return [];
}

function numberOption(value: unknown): number | undefined {
  if (value === undefined || value === null || value === "") return undefined;
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed >= 0 ? parsed : undefined;
}

function booleanOption(value: unknown): boolean | undefined {
  if (typeof value === "boolean") return value;
  if (typeof value !== "string") return undefined;
  const normalized = value.trim().toLowerCase();
  if (["1", "true", "yes", "on"].includes(normalized)) return true;
  if (["0", "false", "no", "off"].includes(normalized)) return false;
  return undefined;
}

function stringRecord(value: unknown): Record<string, string> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  return Object.fromEntries(
    Object.entries(value).map(([key, entry]) => [key, metadataString(entry)])
  );
}

function metadataString(value: unknown): string {
  if (typeof value === "string") return value;
  if (value === undefined || value === null) return "";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}
