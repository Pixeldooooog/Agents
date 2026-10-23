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
  stringSchema,
  subtypeOnlySchema
} from "./sdkJsonSchemaBuilders.js";

const mcpServerConfigSchema = emptyRecordSchema;

export const sdkControlRequestSchema = strictObject({
  type: constSchema("control_request"),
  requestId: stringSchema,
  request: oneOf([
    strictObject({
      subtype: constSchema("initialize"),
      hooks: nullable(emptyRecordSchema),
      sdkMcpServers: nullable(stringArraySchema),
      jsonSchema: nullable(emptyRecordSchema),
      systemPrompt: nullable(stringSchema),
      appendSystemPrompt: nullable(stringSchema),
      agents: nullable(emptyRecordSchema),
      promptSuggestions: nullable(booleanSchema),
      agentProgressSummaries: nullable(booleanSchema)
    }, ["subtype"]),
    strictObject({
      subtype: constSchema("can_use_tool"),
      toolName: stringSchema,
      input: emptyRecordSchema,
      permissionSuggestions: nullable(objectArraySchema),
      blockedPath: nullable(stringSchema),
      decisionReason: nullable(stringSchema),
      title: nullable(stringSchema),
      displayName: nullable(stringSchema),
      toolUseId: stringSchema,
      agentId: nullable(stringSchema),
      description: nullable(stringSchema)
    }, ["subtype", "toolName", "toolUseId"]),
    subtypeOnlySchema("interrupt"),
    strictObject({
      subtype: constSchema("set_permission_mode"),
      mode: enumSchema(["default", "acceptEdits", "bypassPermissions", "plan", "dontAsk"]),
      ultraplan: nullable(booleanSchema)
    }, ["subtype", "mode"]),
    strictObject({ subtype: constSchema("set_model"), model: nullable(stringSchema) }, ["subtype"]),
    strictObject({ subtype: constSchema("set_max_thinking_tokens"), maxThinkingTokens: nullable(numberSchema) }, ["subtype"]),
    subtypeOnlySchema("mcp_status"),
    subtypeOnlySchema("get_context_usage"),
    strictObject({
      subtype: constSchema("rewind_files"),
      userMessageId: stringSchema,
      dryRun: nullable(booleanSchema)
    }, ["subtype", "userMessageId"]),
    strictObject({
      subtype: constSchema("cancel_async_message"),
      messageUuid: stringSchema
    }, ["subtype", "messageUuid"]),
    strictObject({
      subtype: constSchema("seed_read_state"),
      path: stringSchema,
      mtime: numberSchema
    }, ["subtype", "path", "mtime"]),
    strictObject({
      subtype: constSchema("hook_callback"),
      callbackId: stringSchema,
      input: emptyRecordSchema,
      toolUseId: nullable(stringSchema)
    }, ["subtype", "callbackId"]),
    strictObject({
      subtype: constSchema("mcp_message"),
      serverName: stringSchema,
      message: {}
    }, ["subtype", "serverName"]),
    strictObject({
      subtype: constSchema("mcp_set_servers"),
      servers: { type: "object", additionalProperties: mcpServerConfigSchema }
    }, ["subtype"]),
    subtypeOnlySchema("reload_plugins"),
    strictObject({ subtype: constSchema("mcp_reconnect"), serverName: stringSchema }, ["subtype", "serverName"]),
    strictObject({
      subtype: constSchema("mcp_toggle"),
      serverName: stringSchema,
      enabled: booleanSchema
    }, ["subtype", "serverName", "enabled"]),
    strictObject({ subtype: constSchema("stop_task"), taskId: stringSchema }, ["subtype", "taskId"]),
    strictObject({ subtype: constSchema("apply_flag_settings"), settings: emptyRecordSchema }, ["subtype"]),
    subtypeOnlySchema("get_settings"),
    strictObject({
      subtype: constSchema("elicitation"),
      mcpServerName: stringSchema,
      message: stringSchema,
      mode: nullable(enumSchema(["form", "url"])),
      url: nullable(stringSchema),
      elicitationId: nullable(stringSchema),
      requestedSchema: nullable(emptyRecordSchema)
    }, ["subtype", "mcpServerName", "message"])
  ])
}, ["type", "requestId", "request"]);

export const sdkControlResponseSchema = strictObject({
  type: constSchema("control_response"),
  response: oneOf([
    strictObject({
      subtype: constSchema("success"),
      requestId: stringSchema,
      response: nullable(emptyRecordSchema)
    }, ["subtype", "requestId"]),
    strictObject({
      subtype: constSchema("error"),
      requestId: stringSchema,
      error: stringSchema,
      pendingPermissionRequests: nullable({ type: "array", items: sdkControlRequestSchema })
    }, ["subtype", "requestId", "error"])
  ])
}, ["type", "response"]);

export const sdkControlCancelRequestSchema = strictObject({
  type: constSchema("control_cancel_request"),
  requestId: stringSchema
}, ["type", "requestId"]);

export const sdkKeepAliveSchema = strictObject({
  type: constSchema("keep_alive")
}, ["type"]);

export const sdkUpdateEnvironmentVariablesSchema = strictObject({
  type: constSchema("update_environment_variables"),
  variables: { type: "object", additionalProperties: stringSchema }
}, ["type"]);
