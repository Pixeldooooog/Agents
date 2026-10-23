import {
  sdkControlCancelRequestSchema,
  sdkControlRequestSchema,
  sdkControlResponseSchema,
  sdkKeepAliveSchema,
  sdkUpdateEnvironmentVariablesSchema
} from "./sdkControlJsonSchemas.js";
import { cloneSchema, emptyRecordSchema, nullable, numberSchema, oneOf, stringArraySchema, stringSchema } from "./sdkJsonSchemaBuilders.js";
import type { SdkJsonSchema } from "./sdkJsonSchemaBuilders.js";
import {
  sdkMessageSchema,
  sdkResultMessageSchema,
  sdkSessionInfoSchema,
  userMessageSchema
} from "./sdkMessageJsonSchemas.js";

export type { SdkJsonSchema } from "./sdkJsonSchemaBuilders.js";

export function sdkOptionsJsonSchema(): SdkJsonSchema {
  return cloneSchema(sdkOptionsSchema);
}

export function sdkMessageJsonSchema(): SdkJsonSchema {
  return cloneSchema(sdkMessageSchema);
}

export function sdkResultJsonSchema(): SdkJsonSchema {
  return cloneSchema(sdkResultMessageSchema);
}

export function sdkSessionInfoJsonSchema(): SdkJsonSchema {
  return cloneSchema(sdkSessionInfoSchema);
}

export function sdkControlRequestJsonSchema(): SdkJsonSchema {
  return cloneSchema(sdkControlRequestSchema);
}

export function sdkControlResponseJsonSchema(): SdkJsonSchema {
  return cloneSchema(sdkControlResponseSchema);
}

export function sdkControlCancelRequestJsonSchema(): SdkJsonSchema {
  return cloneSchema(sdkControlCancelRequestSchema);
}

export function sdkStdinMessageJsonSchema(): SdkJsonSchema {
  return cloneSchema(sdkStdinMessageSchema);
}

export function sdkStdoutMessageJsonSchema(): SdkJsonSchema {
  return cloneSchema(sdkStdoutMessageSchema);
}

export const sdk_options_json_schema = sdkOptionsJsonSchema;
export const sdk_message_json_schema = sdkMessageJsonSchema;
export const sdk_result_json_schema = sdkResultJsonSchema;
export const sdk_session_info_json_schema = sdkSessionInfoJsonSchema;
export const sdk_control_request_json_schema = sdkControlRequestJsonSchema;
export const sdk_control_response_json_schema = sdkControlResponseJsonSchema;
export const sdk_control_cancel_request_json_schema = sdkControlCancelRequestJsonSchema;
export const sdk_stdin_message_json_schema = sdkStdinMessageJsonSchema;
export const sdk_stdout_message_json_schema = sdkStdoutMessageJsonSchema;

const sdkOptionsSchema = {
  type: "object",
  additionalProperties: false,
  properties: {
    model: nullable(stringSchema),
    protocol: nullable(stringSchema),
    baseUrl: nullable(stringSchema),
    base_url: nullable(stringSchema),
    apiKey: nullable(stringSchema),
    api_key: nullable(stringSchema),
    cwd: nullable(stringSchema),
    systemPrompt: nullable(stringSchema),
    system_prompt: nullable(stringSchema),
    allowedTools: nullable(stringArraySchema),
    allowed_tools: nullable(stringArraySchema),
    enabledTools: nullable(stringArraySchema),
    enabled_tools: nullable(stringArraySchema),
    skills: nullable(stringArraySchema),
    permissionMode: nullable(stringSchema),
    permission_mode: nullable(stringSchema),
    permissionProfile: nullable(stringSchema),
    permission_profile: nullable(stringSchema),
    outputFormat: nullable(emptyRecordSchema),
    output_format: nullable(emptyRecordSchema),
    sessionId: nullable(stringSchema),
    session_id: nullable(stringSchema),
    agentId: nullable(stringSchema),
    agent_id: nullable(stringSchema),
    tenantId: nullable(stringSchema),
    tenant_id: nullable(stringSchema),
    userId: nullable(stringSchema),
    user_id: nullable(stringSchema),
    workspaceId: nullable(stringSchema),
    workspace_id: nullable(stringSchema),
    replayUserMessages: { type: "boolean" },
    replay_user_messages: { type: "boolean" },
    maxToolIterations: numberSchema,
    max_tool_iterations: numberSchema,
    maxTurns: numberSchema,
    max_turns: numberSchema,
    maxThinkingTokens: numberSchema,
    max_thinking_tokens: numberSchema,
    approvalRequiredTools: stringArraySchema,
    approval_required_tools: stringArraySchema,
    deniedTools: stringArraySchema,
    denied_tools: stringArraySchema,
    metadata: emptyRecordSchema
  }
};

const sdkStdinMessageSchema = oneOf([
  userMessageSchema,
  sdkControlRequestSchema,
  sdkControlResponseSchema,
  sdkKeepAliveSchema,
  sdkUpdateEnvironmentVariablesSchema
]);

const sdkStdoutMessageSchema = oneOf([
  sdkMessageSchema,
  sdkControlRequestSchema,
  sdkControlResponseSchema,
  sdkControlCancelRequestSchema,
  sdkKeepAliveSchema
]);
