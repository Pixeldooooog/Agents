import {
  constSchema,
  emptyRecordSchema,
  enumSchema,
  type JsonSchemaProperties,
  nullable,
  numberSchema,
  objectArraySchema,
  oneOf,
  strictObject,
  stringArraySchema,
  stringSchema,
  type SdkJsonSchema
} from "./sdkJsonSchemaBuilders.js";

export const systemMessageSchema = oneOf([
  strictObject({
    type: constSchema("system"),
    subtype: constSchema("init"),
    runId: stringSchema,
    sessionId: stringSchema,
    agents: stringArraySchema,
    apiKeySource: enumSchema(["user", "project", "org", "temporary", "oauth"]),
    betas: stringArraySchema,
    claudeCodeVersion: stringSchema,
    cwd: stringSchema,
    tools: stringArraySchema,
    mcpServers: objectArraySchema,
    model: stringSchema,
    permissionMode: enumSchema(["default", "acceptEdits", "bypassPermissions", "plan", "dontAsk"]),
    slashCommands: stringArraySchema,
    outputStyle: stringSchema,
    skills: stringArraySchema,
    plugins: objectArraySchema,
    fastModeState: nullable(enumSchema(["off", "cooldown", "on"])),
    uuid: stringSchema
  }, ["type", "subtype", "runId", "sessionId"]),
  systemSubtypeSchema("api_retry", {
    attempt: numberSchema,
    maxRetries: numberSchema,
    retryDelayMs: numberSchema,
    errorStatus: nullable(numberSchema),
    error: emptyRecordSchema,
    metadata: emptyRecordSchema
  }, ["attempt", "maxRetries", "retryDelayMs", "error", "metadata"]),
  systemSubtypeSchema("model_recovery", {
    reason: stringSchema,
    attempt: numberSchema,
    maxAttempts: numberSchema,
    stopReason: stringSchema,
    message: stringSchema,
    metadata: emptyRecordSchema,
    uuid: stringSchema
  }, ["reason", "attempt", "maxAttempts", "stopReason", "message", "metadata", "uuid"]),
  systemSubtypeSchema("compact_boundary", { compactMetadata: emptyRecordSchema, uuid: stringSchema }, ["compactMetadata", "uuid"]),
  systemSubtypeSchema("task_started", {
    taskId: stringSchema,
    toolUseId: stringSchema,
    description: stringSchema,
    taskType: stringSchema,
    workflowName: stringSchema,
    prompt: stringSchema
  }, ["taskId"]),
  systemSubtypeSchema("task_progress", {
    taskId: stringSchema,
    toolUseId: stringSchema,
    description: stringSchema,
    usage: emptyRecordSchema,
    lastToolName: stringSchema,
    summary: stringSchema
  }, ["taskId"]),
  systemSubtypeSchema("task_notification", {
    taskId: stringSchema,
    toolUseId: stringSchema,
    status: enumSchema(["completed", "failed", "stopped"]),
    outputFile: stringSchema,
    summary: stringSchema,
    usage: emptyRecordSchema
  }, ["taskId", "status"]),
  systemSubtypeSchema("files_persisted", {
    files: objectArraySchema,
    failed: objectArraySchema,
    processedAt: stringSchema
  }, ["files", "failed", "processedAt"]),
  systemSubtypeSchema("local_command_output", { content: stringSchema, uuid: stringSchema }, ["content", "uuid"]),
  systemSubtypeSchema("hook_started", {
    hookId: stringSchema,
    hookName: stringSchema,
    hookEvent: stringSchema,
    uuid: stringSchema
  }, ["hookId", "hookName", "hookEvent", "uuid"]),
  systemSubtypeSchema("hook_progress", {
    hookId: stringSchema,
    hookName: stringSchema,
    hookEvent: stringSchema,
    stdout: stringSchema,
    stderr: stringSchema,
    output: stringSchema,
    uuid: stringSchema
  }, ["hookId", "hookName", "hookEvent", "uuid"]),
  systemSubtypeSchema("hook_response", {
    hookId: stringSchema,
    hookName: stringSchema,
    hookEvent: stringSchema,
    output: stringSchema,
    stdout: stringSchema,
    stderr: stringSchema,
    exitCode: nullable(numberSchema),
    outcome: enumSchema(["success", "error", "cancelled"]),
    uuid: stringSchema
  }, ["hookId", "hookName", "hookEvent", "outcome", "uuid"]),
  systemSubtypeSchema("elicitation_complete", {
    mcpServerName: stringSchema,
    elicitationId: stringSchema,
    uuid: stringSchema
  }, ["mcpServerName", "elicitationId", "uuid"]),
  systemSubtypeSchema("post_turn_summary", {
    summarizesUuid: stringSchema,
    statusCategory: enumSchema(["blocked", "waiting", "completed", "review_ready", "failed"]),
    statusDetail: stringSchema,
    isNoteworthy: { type: "boolean" },
    title: stringSchema,
    description: stringSchema,
    recentAction: stringSchema,
    needsAction: stringSchema,
    artifactUrls: stringArraySchema,
    uuid: stringSchema
  }, ["summarizesUuid", "statusCategory", "uuid"]),
  systemSubtypeSchema("session_state_changed", { state: enumSchema(["idle", "running", "requires_action"]) }, ["state"]),
  systemSubtypeSchema("status", { status: nullable(constSchema("compacting")), permissionMode: nullable(stringSchema), uuid: stringSchema })
]);

function systemSubtypeSchema(
  subtype: string,
  properties: JsonSchemaProperties,
  subtypeRequired: string[] = []
): SdkJsonSchema {
  return strictObject({
    type: constSchema("system"),
    subtype: constSchema(subtype),
    runId: stringSchema,
    sessionId: stringSchema,
    ...properties
  }, ["type", "subtype", "runId", "sessionId", ...subtypeRequired]);
}
