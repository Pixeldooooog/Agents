import { describe, expect, test } from "bun:test";
import {
  decodeSdkStdinJsonlLine,
  decodeSdkJsonlLine,
  encode_stdout_message,
  encodeSdkJsonlMessage,
  encodeSdkStdoutMessage,
  iter_stdin_jsonl,
  ndjson_safe_dumps,
  readSdkJsonlTransport,
  readSdkStdinJsonlTransport,
  SdkJsonlDecodeError,
  SdkJsonlDecoder,
  SdkStdinDecodeError,
  SdkStdinJsonlDecoder,
  sdk_control_request_json_schema,
  sdkControlRequestJsonSchema,
  sdkControlResponseJsonSchema,
  sdkMessageJsonSchema,
  sdkOptionsJsonSchema,
  sdkResultJsonSchema,
  sdkSessionInfoJsonSchema,
  sdkStdinMessageJsonSchema,
  sdkStdoutMessageJsonSchema,
  SdkQueueJsonlTransport,
  SdkQueueJsonlTransport,
  sdkStdinMessagesFromJsonlChunks,
  normalize_sdk_control_message_keys,
  normalizeSdkControlMessageKeys,
  validate_sdk_control_request,
  validate_sdk_message,
  validateSdkControlRequest,
  validateSdkControlResponse,
  validateSdkMessage,
  validateSdkStdinMessage,
  validateSdkStdoutMessage,
  writeSdkJsonlTransport,
  writeSdkStdoutJsonlTransport,
  type SdkMessage,
  type SdkWireInputMessage,
  type SdkWireMessage
} from "@kevin/core/sdk";

describe("SDK JSONL transport", () => {
  test("encodes SDK messages as safe JSONL lines", () => {
    const message: SdkMessage = {
      type: "assistant_message",
      runId: "run_1",
      sessionId: "session_1",
      content: "line\u2028separator\u2029safe"
    };

    const encoded = encodeSdkJsonlMessage(message);

    expect(encoded.endsWith("\n")).toBe(true);
    expect(encoded).toContain("\\u2028");
    expect(encoded).toContain("\\u2029");
    expect(encoded).not.toContain("\u2028");
    expect(encoded).not.toContain("\u2029");
    expect(decodeSdkJsonlLine(encoded.trim())).toEqual(message);
  });

  test("keeps stdin and stdout JSONL helpers directional", async () => {
    const environmentUpdate = {
      type: "update_environment_variables",
      variables: { SDK_BOUNDARY_TEST: "1" }
    };
    const userMessage: SdkMessage = {
      type: "user_message",
      uuid: "message_stdin_1",
      sessionId: "session_1",
      content: "stdin"
    };
    const decoder = new SdkStdinJsonlDecoder();
    const encodedInput = `${JSON.stringify(environmentUpdate)}\n${encodeSdkJsonlMessage(userMessage)}`;

    expect(decoder.decode(encodedInput.slice(0, 8))).toEqual([]);
    expect([
      ...decoder.decode(encodedInput.slice(8)),
      ...decoder.flush()
    ]).toEqual([environmentUpdate, userMessage]);
    expect(decodeSdkStdinJsonlLine("")).toBeUndefined();
    expect(() => decodeSdkStdinJsonlLine(JSON.stringify({
      type: "control_cancel_request",
      requestId: "cancel_1"
    }))).toThrow(SdkStdinDecodeError);

    const streamedMessages = [];
    for await (const message of sdkStdinMessagesFromJsonlChunks([
      JSON.stringify(environmentUpdate).slice(0, 11),
      `${JSON.stringify(environmentUpdate).slice(11)}\n`,
      encodeSdkJsonlMessage(userMessage)
    ])) {
      streamedMessages.push(message);
    }

    expect(streamedMessages).toEqual([environmentUpdate, userMessage]);
    expect(encodeSdkStdoutMessage(userMessage)).toBe(encodeSdkJsonlMessage(userMessage));
    expect(encode_stdout_message(userMessage)).toBe(encodeSdkJsonlMessage(userMessage));
    expect(ndjson_safe_dumps({ text: "a\u2028b\u2029c" })).toBe("{\"text\":\"a\\u2028b\\u2029c\"}");
    const pythonStyleStreamedMessages = [];
    for await (const message of iter_stdin_jsonl([encodeSdkJsonlMessage(userMessage)])) {
      pythonStyleStreamedMessages.push(message);
    }
    expect(pythonStyleStreamedMessages).toEqual([userMessage]);
    expect(() => encodeSdkStdoutMessage(environmentUpdate)).toThrow(/not a valid SDK stdout message/);
  });

  test("decodes split chunks and trailing JSONL frames", () => {
    const userMessage: SdkMessage = {
      type: "user_message",
      uuid: "message_1",
      sessionId: "session_1",
      content: "hello"
    };
    const resultMessage: SdkMessage = {
      type: "result",
      runId: "run_1",
      sessionId: "session_1",
      status: "finished",
      content: "done",
      isError: false,
      eventCount: 2
    };
    const decoder = new SdkJsonlDecoder();
    const encoded = `${encodeSdkJsonlMessage(userMessage)}\n${JSON.stringify(resultMessage)}`;

    expect(decoder.decode(encoded.slice(0, 12))).toEqual([]);
    expect(decoder.decode(encoded.slice(12))).toEqual([userMessage]);
    expect(decoder.flush()).toEqual([resultMessage]);
    expect(decodeSdkJsonlLine(JSON.stringify({
      type: "user",
      session_id: "session_1",
      uuid: "message_2",
      message: { role: "user", content: [{ type: "text", text: "hello " }, { type: "text", text: "python" }] },
      parent_tool_use_id: "tool_parent",
      tool_use_result: { ok: true },
      is_synthetic: true,
      priority: "next",
      isReplay: false
    }))).toEqual({
      type: "user_message",
      uuid: "message_2",
      sessionId: "session_1",
      content: "hello python",
      message: { role: "user", content: [{ type: "text", text: "hello " }, { type: "text", text: "python" }] },
      parentToolUseId: "tool_parent",
      toolUseResult: { ok: true },
      isSynthetic: true,
      priority: "next",
      isReplay: false
    });
  });

  test("rejects malformed or incomplete SDK frames", () => {
    expect(() => decodeSdkJsonlLine("{broken")).toThrow(SdkJsonlDecodeError);
    expect(() => decodeSdkJsonlLine("   ")).toThrow(SdkJsonlDecodeError);
    expect(() => decodeSdkJsonlLine(JSON.stringify({ type: "result", runId: "run_1" }))).toThrow(
      SdkJsonlDecodeError
    );
  });

  test("encodes and decodes strict SDK control wire messages", () => {
    const controlMessage: SdkWireMessage = {
      type: "control_request",
      requestId: "control_1",
      request: {
        subtype: "can_use_tool",
        toolName: "filesystem.read",
        toolUseId: "tool_1",
        input: { path: "note.txt" }
      }
    };

    expect(decodeSdkJsonlLine(encodeSdkJsonlMessage(controlMessage).trim())).toEqual(controlMessage);
    expect(decodeSdkJsonlLine(JSON.stringify({
      type: "control_request",
      request_id: "control_1",
      request: {
        subtype: "can_use_tool",
        tool_name: "filesystem.read",
        tool_use_id: "tool_1",
        permission_suggestions: [{ behavior: "allow" }],
        blocked_path: "note.txt"
      }
    }))).toEqual({
      type: "control_request",
      requestId: "control_1",
      request: {
        subtype: "can_use_tool",
        toolName: "filesystem.read",
        toolUseId: "tool_1",
        permissionSuggestions: [{ behavior: "allow" }],
        blockedPath: "note.txt"
      }
    });

    const mcpSetServersMessage: SdkWireMessage = {
      type: "control_request",
      requestId: "mcp_1",
      request: {
        subtype: "mcp_set_servers",
        servers: {
          docs: { transport: "sse", url: "http://localhost:3555/sse", authRequired: true }
        }
      }
    };
    expect(decodeSdkJsonlLine(encodeSdkJsonlMessage(mcpSetServersMessage).trim())).toEqual(mcpSetServersMessage);
    expect(decodeSdkJsonlLine(JSON.stringify({
      type: "control_request",
      request_id: "mcp_snake_1",
      request: {
        subtype: "mcp_set_servers",
        servers: {
          docs: {
            transport: "sse",
            url: "http://localhost:3555/sse",
            auth_required: true,
            auth_token: "token",
            execution_mode: "trusted_control_plane"
          }
        }
      }
    }))).toEqual({
      type: "control_request",
      requestId: "mcp_snake_1",
      request: {
        subtype: "mcp_set_servers",
        servers: {
          docs: {
            transport: "sse",
            url: "http://localhost:3555/sse",
            authRequired: true,
            authToken: "token",
            executionMode: "trusted_control_plane"
          }
        }
      }
    });
    expect(decodeSdkJsonlLine(JSON.stringify({
      type: "control_request",
      requestId: "mcp_legacy_1",
      request: {
        subtype: "mcp_set_servers",
        servers: { docs: { type: "sse", url: "http://localhost:3555/sse", vendor_option: "kept" } }
      }
    }))).toEqual({
      type: "control_request",
      requestId: "mcp_legacy_1",
      request: {
        subtype: "mcp_set_servers",
        servers: { docs: { transport: "sse", url: "http://localhost:3555/sse", vendor_option: "kept" } }
      }
    });

    expect(decodeSdkJsonlLine(JSON.stringify({
      type: "control_request",
      request_id: "rewind_1",
      request: { subtype: "rewind_files", user_message_id: "message_1", dry_run: true }
    }))).toEqual({
      type: "control_request",
      requestId: "rewind_1",
      request: { subtype: "rewind_files", userMessageId: "message_1", dryRun: true }
    });

    expect(decodeSdkJsonlLine(JSON.stringify({
      type: "control_response",
      response: { subtype: "success", request_id: "rewind_1", response: { ok: true } }
    }))).toEqual({
      type: "control_response",
      response: { subtype: "success", requestId: "rewind_1", response: { ok: true } }
    });
  });

  test("validates public SDK control, stdin, and stdout contracts strictly", () => {
    const permissionRequest = {
      type: "control_request",
      request_id: "permission_1",
      request: {
        subtype: "can_use_tool",
        tool_name: "filesystem.read",
        tool_use_id: "tool_1",
        input: { path: "note.txt" },
        decision_reason: "read file"
      }
    } satisfies SdkWireInputMessage;

    expect(validateSdkControlRequest(permissionRequest)).toEqual({
      type: "control_request",
      requestId: "permission_1",
      request: {
        subtype: "can_use_tool",
        toolName: "filesystem.read",
        toolUseId: "tool_1",
        input: { path: "note.txt" },
        decisionReason: "read file"
      }
    });
    expect(validateSdkStdinMessage(permissionRequest)).toMatchObject({
      type: "control_request",
      requestId: "permission_1"
    });

    const errorResponse = {
      type: "control_response",
      response: {
        subtype: "error",
        request_id: "outer_1",
        error: "denied",
        pending_permission_requests: [permissionRequest]
      }
    };

    expect(validateSdkControlResponse(errorResponse)).toMatchObject({
      type: "control_response",
      response: {
        subtype: "error",
        requestId: "outer_1",
        pendingPermissionRequests: [expect.objectContaining({ requestId: "permission_1" })]
      }
    });
    expect(validateSdkStdoutMessage({
      type: "control_cancel_request",
      request_id: "permission_1"
    })).toEqual({
      type: "control_cancel_request",
      requestId: "permission_1"
    });
    expect(decodeSdkJsonlLine(JSON.stringify({
      type: "update_environment_variables"
    }))).toEqual({
      type: "update_environment_variables",
      variables: {}
    });
    expect(validateSdkStdinMessage({
      type: "update_environment_variables"
    })).toEqual({
      type: "update_environment_variables",
      variables: {}
    });
    expect(validateSdkMessage({
      type: "user",
      session_id: "session_1",
      uuid: "message_1",
      content: "hello",
      is_replay: false
    })).toEqual({
      type: "user_message",
      sessionId: "session_1",
      uuid: "message_1",
      content: "hello",
      isReplay: false
    });
    expect(validate_sdk_message({
      type: "assistant_message",
      runId: "run_1",
      sessionId: "session_1",
      content: "answer"
    })).toEqual({
      type: "assistant_message",
      runId: "run_1",
      sessionId: "session_1",
      content: "answer"
    });
    expect(validate_sdk_control_request(permissionRequest)).toMatchObject({
      type: "control_request",
      requestId: "permission_1"
    });
    expect(normalizeSdkControlMessageKeys(errorResponse)).toMatchObject({
      type: "control_response",
      response: {
        requestId: "outer_1",
        pendingPermissionRequests: [
          expect.objectContaining({
            requestId: "permission_1",
            request: expect.objectContaining({
              toolName: "filesystem.read",
              toolUseId: "tool_1"
            })
          })
        ]
      }
    });
    expect(normalize_sdk_control_message_keys({
      type: "control_cancel_request",
      request_id: "permission_1"
    })).toEqual({
      type: "control_cancel_request",
      requestId: "permission_1"
    });
    expect(normalize_sdk_control_message_keys(null)).toBeNull();
    expect((permissionRequest.request as Record<string, unknown>).tool_name).toBe("filesystem.read");
    expect(validateSdkControlRequest({
      type: "control_request",
      request_id: "nullable_control_1",
      request: {
        subtype: "initialize",
        hooks: null,
        sdk_mcp_servers: null,
        json_schema: null,
        system_prompt: null,
        append_system_prompt: null,
        agents: null,
        prompt_suggestions: null,
        agent_progress_summaries: null
      }
    })).toMatchObject({
      type: "control_request",
      requestId: "nullable_control_1",
      request: {
        hooks: null,
        sdkMcpServers: null,
        jsonSchema: null,
        systemPrompt: null,
        appendSystemPrompt: null,
        agents: null,
        promptSuggestions: null,
        agentProgressSummaries: null
      }
    });
    expect(validateSdkControlRequest({
      type: "control_request",
      requestId: "nullable_control_2",
      request: {
        subtype: "set_model",
        model: null
      }
    })).toMatchObject({ request: { model: null } });
    expect(validateSdkControlRequest({
      type: "control_request",
      requestId: "nullable_control_3",
      request: {
        subtype: "set_max_thinking_tokens",
        max_thinking_tokens: null
      }
    })).toMatchObject({ request: { maxThinkingTokens: null } });
    expect(validateSdkControlResponse({
      type: "control_response",
      response: {
        subtype: "success",
        requestId: "nullable_control_2",
        response: null
      }
    })).toMatchObject({ response: { response: null } });
    expect(validateSdkControlResponse({
      type: "control_response",
      response: {
        subtype: "error",
        requestId: "nullable_control_3",
        error: "denied",
        pending_permission_requests: null
      }
    })).toMatchObject({ response: { pendingPermissionRequests: null } });

    expect(() => validateSdkControlRequest({
      type: "control_request",
      requestId: "bad_1",
      request: {
        subtype: "set_model",
        model: "mock",
        unexpected: true
      }
    })).toThrow(/not supported/);
    expect(() => validateSdkControlResponse({
      type: "control_response",
      response: {
        subtype: "error",
        requestId: "bad_2",
        error: "denied",
        pendingPermissionRequests: [{ type: "keep_alive" }]
      }
    })).toThrow(/expected SDK control_request message/);
    expect(() => validateSdkStdinMessage({
      type: "control_cancel_request",
      requestId: "cancel_1"
    })).toThrow(/not a valid SDK stdin message/);
    expect(() => validateSdkStdoutMessage({
      type: "update_environment_variables",
      variables: { A: "1" }
    })).toThrow(/not a valid SDK stdout message/);
    expect(() => validateSdkMessage(permissionRequest)).toThrow(/expected SDK stream message/);
    expect(() => validate_sdk_message({ type: "keep_alive" })).toThrow(/expected SDK stream message/);
    expect(() => validateSdkStdoutMessage({
      type: "assistant_message",
      runId: "run_1",
      sessionId: "session_1",
      content: "answer",
      unexpected: true
    })).toThrow(/not supported/);
    const initMessage = {
      type: "system",
      subtype: "init",
      runId: "run_1",
      sessionId: "session_1",
      agents: [],
      apiKeySource: "project",
      betas: [],
      claudeCodeVersion: "",
      cwd: "/repo",
      tools: [],
      mcpServers: [],
      model: "mock",
      permissionMode: "default",
      slashCommands: [],
      outputStyle: "default",
      skills: [],
      plugins: [],
      uuid: "init_1"
    };
    expect(() => validateSdkStdoutMessage({
      ...initMessage,
      extraField: true
    })).toThrow(/not supported/);
    expect(() => validateSdkStdoutMessage({
      ...initMessage,
      apiKeySource: "env"
    })).toThrow(/apiKeySource/);
    expect(() => validateSdkStdoutMessage({
      ...initMessage,
      fastModeState: "turbo"
    })).toThrow(/fastModeState/);
    expect(validateSdkStdoutMessage({
      type: "system",
      subtype: "status",
      runId: "run_1",
      sessionId: "session_1",
      permissionMode: null
    })).toMatchObject({ permissionMode: null });
    expect(validateSdkStdoutMessage({
      type: "system",
      subtype: "status",
      runId: "run_1",
      sessionId: "session_1",
      status: null,
      permissionMode: null
    })).toMatchObject({ status: null, permissionMode: null });
  });

  test("exports SDK JSON schemas for public wire contracts", () => {
    const controlRequestSchema = sdkControlRequestJsonSchema();
    const controlRequestProperties = schemaProperties(controlRequestSchema);
    const controlRequestPayloads = schemaOneOf(controlRequestProperties.request);

    expect(controlRequestSchema).toMatchObject({
      type: "object",
      additionalProperties: false,
      required: ["type", "requestId", "request"]
    });
    expect(controlRequestPayloads.map((schema) => schemaProperties(schema).subtype?.const)).toContain("can_use_tool");
    expect(controlRequestPayloads.map((schema) => schemaProperties(schema).subtype?.const)).toContain("elicitation");
    const initializeSchema = controlRequestPayloads.find(
      (schema) => schemaProperties(schema).subtype?.const === "initialize"
    );
    expect(schemaAcceptsNull(schemaProperties(initializeSchema).systemPrompt)).toBe(true);
    expect(schemaAcceptsNull(schemaProperties(initializeSchema).sdkMcpServers)).toBe(true);
    const setModelSchema = controlRequestPayloads.find(
      (schema) => schemaProperties(schema).subtype?.const === "set_model"
    );
    expect(schemaAcceptsNull(schemaProperties(setModelSchema).model)).toBe(true);
    const mcpSetServersSchema = controlRequestPayloads.find(
      (schema) => schemaProperties(schema).subtype?.const === "mcp_set_servers"
    );
    expect(schemaProperties(mcpSetServersSchema).servers?.additionalProperties).toMatchObject({
      type: "object",
      additionalProperties: true
    });
    const controlResponsePayloads = schemaOneOf(schemaProperties(sdkControlResponseJsonSchema()).response);
    const successResponseSchema = controlResponsePayloads.find(
      (schema) => schemaProperties(schema).subtype?.const === "success"
    );
    const errorResponseSchema = controlResponsePayloads.find(
      (schema) => schemaProperties(schema).subtype?.const === "error"
    );
    expect(schemaAcceptsNull(schemaProperties(successResponseSchema).response)).toBe(true);
    expect(schemaAcceptsNull(schemaProperties(errorResponseSchema).pendingPermissionRequests)).toBe(true);

    const stdinTypes = schemaOneOf(sdkStdinMessageJsonSchema()).map(schemaTypeConst);
    const stdoutTypes = schemaOneOf(sdkStdoutMessageJsonSchema()).map(schemaTypeConst);
    expect(stdinTypes).toContain("update_environment_variables");
    expect(stdoutTypes).toContain("control_cancel_request");
    expect(stdoutTypes).not.toContain("update_environment_variables");
    const environmentUpdateSchema = schemaOneOf(sdkStdinMessageJsonSchema()).find(
      (schema) => schemaTypeConst(schema) === "update_environment_variables"
    );
    expect(environmentUpdateSchema?.required).toEqual(["type"]);

    expect(schemaProperties(sdkOptionsJsonSchema())).toMatchObject({
      sessionId: expect.any(Object),
      session_id: expect.any(Object),
      baseUrl: expect.any(Object),
      base_url: expect.any(Object),
      apiKey: expect.any(Object),
      api_key: expect.any(Object),
      replayUserMessages: { type: "boolean" }
    });
    expect(schemaOneOf(sdkMessageJsonSchema()).map(schemaTypeConst)).toContain("result");
    const systemSchemas = schemaOneOf(sdkMessageJsonSchema()).flatMap(schemaOneOf);
    const initSchema = systemSchemas.find((schema) => schemaProperties(schema).subtype?.const === "init");
    expect(schemaProperties(initSchema)).toMatchObject({
      tools: { type: "array", items: { type: "string" } },
      slashCommands: { type: "array", items: { type: "string" } },
      apiKeySource: { enum: ["user", "project", "org", "temporary", "oauth"] },
      permissionMode: { enum: ["default", "acceptEdits", "bypassPermissions", "plan", "dontAsk"] },
      fastModeState: { anyOf: [{ enum: ["off", "cooldown", "on"] }, { type: "null" }] }
    });
    expect(schemaProperties(initSchema).availableOutputStyles).toBeUndefined();
    const statusSchema = systemSchemas.find((schema) => schemaProperties(schema).subtype?.const === "status");
    expect(schemaProperties(statusSchema).status).toEqual({
      anyOf: [{ const: "compacting" }, { type: "null" }]
    });
    expect(schemaProperties(sdkResultJsonSchema())).toMatchObject({
      status: { enum: ["finished", "awaiting_approval", "error", "canceled"] }
    });
    expect(schemaProperties(sdkSessionInfoJsonSchema())).toMatchObject({
      sessionId: { type: "string" },
      runIds: { type: "array", items: { type: "string" } }
    });

    (controlRequestSchema as any).properties.extra = { type: "string" };
    expect(schemaProperties(sdk_control_request_json_schema()).extra).toBeUndefined();
  });

  test("encodes and decodes structured SDK event messages", () => {
    const toolProgress: SdkMessage = {
      type: "tool_progress",
      runId: "run_1",
      sessionId: "session_1",
      toolCallId: "call_1",
      name: "task.update",
      status: "completed",
      input: {},
      result: { ok: true },
      error: ""
    };
    const systemMessage: SdkMessage = {
      type: "system",
      subtype: "task_notification",
      runId: "run_1",
      sessionId: "session_1",
      taskId: "task_1",
      toolUseId: "call_1",
      status: "completed",
      outputFile: "",
      summary: "done",
      usage: { totalTokens: 1, toolUses: 1, durationMs: 2 }
    };
    const streamEvent: SdkMessage = {
      type: "stream_event",
      runId: "run_1",
      sessionId: "session_1",
      event: { type: "content_block_delta", delta: { type: "text_delta", text: "a" } },
      uuid: "event_1"
    };
    const compactBoundary: SdkMessage = {
      type: "system",
      subtype: "compact_boundary",
      runId: "run_1",
      sessionId: "session_1",
      compactMetadata: { trigger: "manual", droppedMessages: 2 },
      uuid: "compact_1"
    };

    expect(decodeSdkJsonlLine(encodeSdkJsonlMessage(toolProgress).trim())).toEqual(toolProgress);
    expect(decodeSdkJsonlLine(encodeSdkJsonlMessage(systemMessage).trim())).toEqual(systemMessage);
    expect(decodeSdkJsonlLine(encodeSdkJsonlMessage(streamEvent).trim())).toEqual(streamEvent);
    expect(decodeSdkJsonlLine(encodeSdkJsonlMessage(compactBoundary).trim())).toEqual(compactBoundary);
    expect(() => decodeSdkJsonlLine(JSON.stringify({
      type: "tool_progress",
      runId: "run_1",
      sessionId: "session_1",
      toolCallId: "call_1",
      name: "task.update",
      status: "bad",
      input: {},
      result: {},
      error: ""
    }))).toThrow(SdkJsonlDecodeError);
  });

  test("encodes and decodes complete SDK output contract messages", () => {
    const messages: SdkMessage[] = [
      {
        type: "tool_progress",
        runId: "run_1",
        sessionId: "session_1",
        toolCallId: "call_1",
        name: "shell.run",
        status: "stalled",
        input: { command: "make check" },
        result: {},
        activity: { phase: "waiting" },
        target: "make check",
        paths: ["packages/core"],
        metadata: { source: "sdk" },
        error: "",
        output: "partial",
        fullOutput: "partial output",
        elapsedTimeSeconds: 1.5,
        totalLines: 2,
        totalBytes: 14,
        taskId: "task_1",
        timeoutMs: 30000
      },
      {
        type: "system",
        subtype: "init",
        runId: "run_1",
        sessionId: "session_1",
        agents: ["default"],
        apiKeySource: "project",
        betas: [],
        claudeCodeVersion: "",
        cwd: "/repo",
        tools: ["filesystem.read"],
        mcpServers: [{ name: "docs", status: "connected" }],
        model: "mock",
        permissionMode: "default",
        slashCommands: ["/review"],
        outputStyle: "default",
        skills: ["review"],
        plugins: [{ name: "docs" }],
        fastModeState: null,
        uuid: "init_1"
      },
      {
        type: "system",
        subtype: "api_retry",
        runId: "run_1",
        sessionId: "session_1",
        attempt: 1,
        maxRetries: 3,
        retryDelayMs: 250,
        errorStatus: 429,
        error: { message: "rate limited" },
        metadata: { provider: "mock" }
      },
      {
        type: "system",
        subtype: "model_recovery",
        runId: "run_1",
        sessionId: "session_1",
        reason: "rate_limit",
        attempt: 2,
        maxAttempts: 3,
        stopReason: "rate_limit",
        message: "retrying with fallback",
        metadata: { fallback: "mock-2" },
        uuid: "recovery_1"
      },
      {
        type: "system",
        subtype: "local_command_output",
        runId: "run_1",
        sessionId: "session_1",
        content: "local output",
        uuid: "local_1"
      },
      {
        type: "system",
        subtype: "hook_started",
        runId: "run_1",
        sessionId: "session_1",
        hookId: "hook_1",
        hookName: "lint",
        hookEvent: "post_tool_use",
        uuid: "hook_started_1"
      },
      {
        type: "system",
        subtype: "hook_progress",
        runId: "run_1",
        sessionId: "session_1",
        hookId: "hook_1",
        hookName: "lint",
        hookEvent: "post_tool_use",
        stdout: "ok",
        stderr: "",
        output: "ok",
        uuid: "hook_progress_1"
      },
      {
        type: "system",
        subtype: "hook_response",
        runId: "run_1",
        sessionId: "session_1",
        hookId: "hook_1",
        hookName: "lint",
        hookEvent: "post_tool_use",
        output: "ok",
        stdout: "ok",
        stderr: "",
        exitCode: 0,
        outcome: "success",
        uuid: "hook_response_1"
      },
      {
        type: "system",
        subtype: "elicitation_complete",
        runId: "run_1",
        sessionId: "session_1",
        mcpServerName: "forms",
        elicitationId: "ask_1",
        uuid: "elicitation_1"
      },
      {
        type: "system",
        subtype: "post_turn_summary",
        runId: "run_1",
        sessionId: "session_1",
        summarizesUuid: "message_1",
        statusCategory: "completed",
        statusDetail: "done",
        isNoteworthy: true,
        title: "Finished",
        description: "Completed the turn",
        recentAction: "Ran tests",
        needsAction: "",
        artifactUrls: ["file://report"],
        uuid: "summary_1"
      },
      {
        type: "auth_status",
        runId: "run_1",
        sessionId: "session_1",
        isAuthenticating: false,
        output: ["ready"],
        error: "",
        metadata: { provider: "mcp" }
      },
      {
        type: "rate_limit_event",
        runId: "run_1",
        sessionId: "session_1",
        rateLimitInfo: { limit: 10 },
        uuid: "rate_1"
      },
      {
        type: "tool_use_summary",
        runId: "run_1",
        sessionId: "session_1",
        summary: "Read and edited files",
        precedingToolUseIds: ["call_1"],
        uuid: "tool_summary_1"
      },
      {
        type: "prompt_suggestion",
        runId: "run_1",
        sessionId: "session_1",
        suggestion: "Run the full test suite",
        uuid: "suggestion_1"
      },
      {
        type: "result",
        runId: "run_1",
        sessionId: "session_1",
        status: "finished",
        subtype: "success",
        content: "done",
        result: "done",
        isError: false,
        durationMs: 120,
        durationApiMs: 80,
        numTurns: 1,
        stopReason: "end_turn",
        totalCostUsd: 0.01,
        usage: { input_tokens: 10 },
        modelUsage: { totalTokens: 20 },
        permissionDenials: [{ tool: "shell.run" }],
        structuredOutput: { ok: true },
        fastModeState: null,
        errors: [],
        eventCount: 4,
        uuid: "result_1"
      }
    ];

    for (const message of messages) {
      expect(decodeSdkJsonlLine(encodeSdkJsonlMessage(message).trim())).toEqual(message);
    }
    expect(() => decodeSdkJsonlLine(JSON.stringify({
      type: "system",
      subtype: "hook_response",
      runId: "run_1",
      sessionId: "session_1",
      hookId: "hook_1",
      hookName: "lint",
      hookEvent: "post_tool_use",
      output: "",
      stdout: "",
      stderr: "",
      outcome: "unknown",
      uuid: "hook_response_bad"
    }))).toThrow(SdkJsonlDecodeError);
  });

  test("moves JSONL chunks through the in-process queue transport", async () => {
    const userMessage: SdkMessage = {
      type: "user_message",
      uuid: "message_1",
      sessionId: "session_1",
      content: "queued"
    };
    const resultMessage: SdkMessage = {
      type: "result",
      runId: "run_1",
      sessionId: "session_1",
      status: "finished",
      content: "queued result",
      isError: false,
      eventCount: 1
    };
    const transport = new SdkQueueJsonlTransport();
    const receivedMessages = collectMessages(readSdkJsonlTransport(transport));
    const encoded = encodeSdkJsonlMessage(userMessage) + encodeSdkJsonlMessage(resultMessage);

    transport.send(encoded.slice(0, 9));
    transport.send(new TextEncoder().encode(encoded.slice(9)));
    transport.closeInput();

    expect(await receivedMessages).toEqual([userMessage, resultMessage]);
    expect(() => transport.send("\n")).toThrow("SDK JSONL transport input is closed");

    await writeSdkJsonlTransport(transport, resultMessage);
    expect(await transport.receive()).toBe(encodeSdkJsonlMessage(resultMessage));

    await writeSdkStdoutJsonlTransport(transport, resultMessage);
    expect(await transport.receive()).toBe(encodeSdkJsonlMessage(resultMessage));
    expect(() => writeSdkStdoutJsonlTransport(transport, {
      type: "update_environment_variables",
      variables: { SDK_BOUNDARY_TEST: "1" }
    })).toThrow(/not a valid SDK stdout message/);

    await writeSdkJsonlTransport(transport, userMessage);
    await writeSdkJsonlTransport(transport, resultMessage);
    expect(transport.drainOutput()).toEqual([
      encodeSdkJsonlMessage(userMessage),
      encodeSdkJsonlMessage(resultMessage)
    ]);

    transport.close();
    expect(transport.isClosed).toBe(true);
    expect(await transport.receive()).toBeUndefined();

    const stdinTransport = new SdkQueueJsonlTransport();
    const receivedStdinMessages = collectMessages(readSdkStdinJsonlTransport(stdinTransport));
    stdinTransport.send(JSON.stringify({
      type: "update_environment_variables",
      variables: { SDK_BOUNDARY_TEST: "2" }
    }) + "\n");
    stdinTransport.closeInput();

    expect(await receivedStdinMessages).toEqual([{
      type: "update_environment_variables",
      variables: { SDK_BOUNDARY_TEST: "2" }
    }]);

    const pythonStyleTransport = new SdkQueueJsonlTransport();
    const pythonStyleReceivedMessages = collectMessages(readSdkJsonlTransport(pythonStyleTransport));
    pythonStyleTransport.send(encodeSdkJsonlMessage(userMessage));
    pythonStyleTransport.close_input();

    expect(await pythonStyleReceivedMessages).toEqual([userMessage]);
    await writeSdkJsonlTransport(pythonStyleTransport, resultMessage);
    expect(pythonStyleTransport.drain_output()).toEqual([encodeSdkJsonlMessage(resultMessage)]);
    expect(pythonStyleTransport.closed).toBe(false);
    pythonStyleTransport.close();
    expect(pythonStyleTransport.closed).toBe(true);
  });
});

async function collectMessages(messages: AsyncIterable<SdkWireMessage>): Promise<SdkWireMessage[]> {
  const collected: SdkWireMessage[] = [];
  for await (const message of messages) collected.push(message);
  return collected;
}

function schemaProperties(schema: any): Record<string, any> {
  return schema?.properties || {};
}

function schemaOneOf(schema: any): any[] {
  return Array.isArray(schema?.oneOf) ? schema.oneOf : [];
}

function schemaAcceptsNull(schema: any): boolean {
  return Array.isArray(schema?.anyOf) && schema.anyOf.some((entry: any) => entry?.type === "null");
}

function schemaTypeConst(schema: any): string | undefined {
  return schemaProperties(schema).type?.const;
}
