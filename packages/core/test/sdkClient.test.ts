import { describe, expect, test, spyOn } from "bun:test";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import {
  AgentSdkClient,
  chatPayloadFromSdkOptions,
  createSession,
  decodeSdkJsonlLine,
  encodeSdkJsonlMessage,
  fork_session,
  get_session_info,
  get_session_messages,
  handle_control_request,
  getSessionInfo,
  handleControlRequest,
  list_sessions,
  listSessions,
  prompt as sdkPrompt,
  query as sdkQuery,
  rename_session,
  renameSession,
  run_jsonl_transport,
  run_stdin,
  run_stdin_jsonl,
  runStdin,
  runStdinJsonl,
  SdkQueueJsonlTransport,
  tag_session,
  tagSession,
  unstable_v2_create_session,
  unstable_v2_prompt,
  unstable_v2_resume_session,
  unstableV2CreateSession,
  unstableV2Prompt,
  type SdkWireMessage
} from "@kevin/core/sdk";
import { loadSettings, JsonStateStore, specFromPayload } from "../src/index.js";

describe("TS SDK client", () => {
  test("maps SDK runtime options into structured chat payload controls", () => {
    const payload = chatPayloadFromSdkOptions("limit loop", {
      session_id: "session_options",
      cwd: "/workspace/options",
      allowed_tools: ["filesystem.read"],
      skills: ["review"],
      permission_mode: "bypass-permissions",
      output_format: {
        type: "json_schema",
        schema: { type: "object", properties: { answer: { type: "string" } } }
      },
      replay_user_messages: true,
      maxToolIterations: 2,
      maxThinkingTokens: 4096,
      metadata: { source: "sdk-test", nested: { ok: true } }
    });
    expect(payload).toMatchObject({
      message: "limit loop",
      enabled_tools: ["filesystem.read"],
      permission_profile: "auto",
      runtime: {
        maxToolIterations: 2,
        maxThinkingTokens: 4096
      },
      metadata: {
        source: "sdk-test",
        nested: "{\"ok\":true}",
        sdk_prompt: "limit loop",
        sdk_session_id: "session_options",
        sdk_cwd: "/workspace/options",
        cwd: "/workspace/options",
        enabled_skills: "review",
        sdk_skills: "review",
        replayUserMessages: "true"
      }
    });
    expect(JSON.parse(payload.metadata?.structured_output_schema || "{}")).toEqual({
      type: "object",
      properties: { answer: { type: "string" } }
    });
    expect(chatPayloadFromSdkOptions("deny loop", { permissionMode: "dont-ask" })).toMatchObject({
      permission_profile: "deny"
    });
  });

  test("exposes module-level SDK helpers over an explicit client", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-sdk-module-helpers-"));
    const server = Bun.serve({
      port: 0,
      async fetch(request) {
        const body = await request.json();
        const user = (body.messages || []).find((message: any) => message.role === "user");
        return Response.json({ choices: [{ message: { content: `module answer: ${user?.content || ""}` } }] });
      }
    });
    try {
      const settings = await loadSettings(root);
      const store = new JsonStateStore(path.join(root, "state.json"));
      const client = new AgentSdkClient({ settings, store });
      const modelOptions = {
        client,
        protocol: "openai-chat",
        model: "mock",
        baseUrl: `http://127.0.0.1:${server.port}/v1`,
        apiKey: "test"
      };

      const session = await createSession({ ...modelOptions, sessionId: "session_module" });
      const unstableSession = await unstableV2CreateSession({ client, sessionId: "session_unstable" });
      const snakeUnstableSession = await unstable_v2_create_session({ client, sessionId: "session_snake_unstable" });
      expect(session.sessionId).toBe("session_module");
      expect(unstableSession.sessionId).toBe("session_unstable");
      expect(snakeUnstableSession.sessionId).toBe("session_snake_unstable");

      const promptResult = await sdkPrompt("helper prompt", { ...modelOptions, sessionId: "session_module" });
      const unstablePromptResult = await unstableV2Prompt("unstable helper prompt", {
        ...modelOptions,
        sessionId: "session_unstable"
      });
      const snakeUnstablePromptResult = await unstable_v2_prompt("snake unstable helper prompt", {
        ...modelOptions,
        sessionId: "session_snake_unstable"
      });
      const streamedMessages = await collectSdkWireMessages(sdkQuery("helper stream", {
        ...modelOptions,
        sessionId: "session_stream"
      }) as AsyncIterable<SdkWireMessage>);
      const instanceUserMessages = await collectSdkWireMessages(client.query_user_message({
        type: "user_message",
        uuid: "message_client_snake_user",
        sessionId: "session_client_snake_user",
        content: "client snake user"
      }, {
        protocol: "openai-chat",
        model: "mock",
        baseUrl: `http://127.0.0.1:${server.port}/v1`,
        apiKey: "test"
      }) as AsyncIterable<SdkWireMessage>);
      const pythonDictUserMessages = await collectSdkWireMessages(client.query_user_message({
        type: "user",
        uuid: "message_python_dict_user",
        session_id: "session_python_dict_user",
        message: { role: "user", content: [{ type: "text", text: "python dict user" }] }
      }, {
        protocol: "openai-chat",
        model: "mock",
        baseUrl: `http://127.0.0.1:${server.port}/v1`,
        apiKey: "test"
      }) as AsyncIterable<SdkWireMessage>);

      expect(promptResult).toMatchObject({
        type: "result",
        sessionId: "session_module",
        content: "module answer: helper prompt"
      });
      expect(unstablePromptResult).toMatchObject({
        type: "result",
        sessionId: "session_unstable",
        content: "module answer: unstable helper prompt"
      });
      expect(snakeUnstablePromptResult).toMatchObject({
        type: "result",
        sessionId: "session_snake_unstable",
        content: "module answer: snake unstable helper prompt"
      });
      expect(streamedMessages.at(-1)).toMatchObject({
        type: "result",
        sessionId: "session_stream",
        content: "module answer: helper stream"
      });
      expect(instanceUserMessages.at(-1)).toMatchObject({
        type: "result",
        sessionId: "session_client_snake_user",
        content: "module answer: client snake user"
      });
      expect(pythonDictUserMessages.at(-1)).toMatchObject({
        type: "result",
        sessionId: "session_python_dict_user",
        content: "module answer: python dict user"
      });
      expect((await unstable_v2_resume_session("session_snake_unstable", { client })).sessionId)
        .toBe("session_snake_unstable");

      await renameSession("session_module", "Module Helper Session", { client });
      await tagSession("session_module", "module", { client });
      await rename_session("session_snake_unstable", "Snake Helper Session", { client });
      await tag_session("session_snake_unstable", "snake", { client });
      expect(await getSessionInfo("session_module", { client })).toMatchObject({
        customTitle: "Module Helper Session",
        tag: "module"
      });
      expect(await get_session_info("session_snake_unstable", { client })).toMatchObject({
        customTitle: "Snake Helper Session",
        tag: "snake"
      });
      expect(await listSessions({ client })).toContainEqual(expect.objectContaining({
        sessionId: "session_module"
      }));
      expect(await list_sessions({ client })).toContainEqual(expect.objectContaining({
        sessionId: "session_snake_unstable"
      }));
      expect(await get_session_messages("session_snake_unstable", { client })).toContainEqual(
        expect.objectContaining({
          type: "result",
          content: "module answer: snake unstable helper prompt"
        })
      );
      const forkedSnakeSession = await fork_session("session_snake_unstable", {
        client,
        title: "Snake Fork Session"
      });
      expect(forkedSnakeSession.sessionId).toMatch(/^session_/);
      expect(forkedSnakeSession.runIds.length).toBeGreaterThan(0);

      const controlResponse = await handleControlRequest({
        type: "control_request",
        requestId: "settings_1",
        request: { subtype: "get_settings" }
      }, { client, model: "module-model" });
      expect(controlPayload(controlResponse)).toMatchObject({
        effective: { model: "module-model" }
      });
      const snakeControlResponse = await handle_control_request({
        type: "control_request",
        requestId: "snake_settings_1",
        request: { subtype: "get_settings" }
      }, { client, model: "snake-model" });
      expect(controlPayload(snakeControlResponse)).toMatchObject({
        effective: { model: "snake-model" }
      });

      const stdinMessages = await collectSdkWireMessages(runStdin([{
        type: "control_request",
        requestId: "stdin_settings_1",
        request: { subtype: "get_settings" }
      }], { client, model: "stdin-model" }));
      expect(controlPayload(stdinMessages[0])).toMatchObject({
        effective: { model: "stdin-model" }
      });
      const snakeStdinMessages = await collectSdkWireMessages(run_stdin([{
        type: "control_request",
        requestId: "snake_stdin_settings_1",
        request: { subtype: "get_settings" }
      }], { client, model: "snake-stdin-model" }));
      expect(controlPayload(snakeStdinMessages[0])).toMatchObject({
        effective: { model: "snake-stdin-model" }
      });

      const jsonlLines = [];
      for await (const line of runStdinJsonl([encodeSdkJsonlMessage({
        type: "control_request",
        requestId: "jsonl_settings_1",
        request: { subtype: "get_settings" }
      })], { client, model: "jsonl-model" })) {
        jsonlLines.push(line);
      }
      expect(controlPayload(decodeSdkJsonlLine(jsonlLines[0].trim()))).toMatchObject({
        effective: { model: "jsonl-model" }
      });
      const snakeJsonlLines = [];
      for await (const line of run_stdin_jsonl([encodeSdkJsonlMessage({
        type: "control_request",
        requestId: "snake_jsonl_settings_1",
        request: { subtype: "get_settings" }
      })], { client, model: "snake-jsonl-model" })) {
        snakeJsonlLines.push(line);
      }
      expect(controlPayload(decodeSdkJsonlLine(snakeJsonlLines[0].trim()))).toMatchObject({
        effective: { model: "snake-jsonl-model" }
      });
      const snakeTransport = new SdkQueueJsonlTransport();
      const transportRun = run_jsonl_transport(snakeTransport, { client, model: "snake-transport-model" });
      snakeTransport.send(encodeSdkJsonlMessage({
        type: "control_request",
        requestId: "snake_transport_settings_1",
        request: { subtype: "get_settings" }
      }));
      const snakeTransportLine = await snakeTransport.receive();
      snakeTransport.closeInput();
      await transportRun;
      expect(controlPayload(decodeSdkJsonlLine(String(snakeTransportLine).trim()))).toMatchObject({
        effective: { model: "snake-transport-model" }
      });
    } finally {
      server.stop(true);
      await rm(root, { recursive: true, force: true });
    }
  });

  test("exposes Python-style AgentSdkClient instance aliases", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-sdk-client-aliases-"));
    try {
      const settings = await loadSettings(root);
      const store = new JsonStateStore(path.join(root, "state.json"));
      const client = new AgentSdkClient({ settings, store });

      const session = client.create_sdk_session({ session_id: "session_client_alias" });
      expect(session.session_id).toBe("session_client_alias");

      client.register_sdk_mcp_server("docs", async (message) => ({ echoed: message }));
      expect(await client.callSdkMcpServer("docs", { ok: true })).toEqual({ echoed: { ok: true } });
      client.unregister_sdk_mcp_server("docs");
      expect(client.hasSdkMcpServer("docs")).toBe(false);

      client.register_hook_callback("hook_1", (request) => ({ callbackId: request.callbackId }));
      expect(await client.callHookCallback({ subtype: "hook_callback", callbackId: "hook_1", input: {} })).toEqual({
        callbackId: "hook_1"
      });
      client.unregister_hook_callback("hook_1");
      expect(await client.callHookCallback({ subtype: "hook_callback", callbackId: "hook_1", input: {} })).toBeUndefined();

      client.set_elicitation_handler(() => ({ action: "accept", content: { ok: true } }));
      expect(await client.runElicitation({
        subtype: "elicitation",
        mcpServerName: "docs",
        message: "choose"
      })).toEqual({ action: "accept", content: { ok: true } });

      const stdinMessages = await collectSdkWireMessages(client.run_stdin([{
        type: "control_request",
        requestId: "client_alias_settings_1",
        request: { subtype: "get_settings" }
      }], { model: "client-alias-model" }));
      expect(controlPayload(stdinMessages[0])).toMatchObject({
        effective: { model: "client-alias-model" }
      });

      const jsonlLines = [];
      for await (const line of client.run_stdin_jsonl([encodeSdkJsonlMessage({
        type: "control_request",
        requestId: "client_alias_jsonl_1",
        request: { subtype: "get_settings" }
      })], { model: "client-alias-jsonl-model" })) {
        jsonlLines.push(line);
      }
      expect(controlPayload(decodeSdkJsonlLine(jsonlLines[0].trim()))).toMatchObject({
        effective: { model: "client-alias-jsonl-model" }
      });

      const transport = new SdkQueueJsonlTransport();
      const transportRun = client.run_jsonl_transport(transport, { model: "client-alias-transport-model" });
      transport.send(encodeSdkJsonlMessage({
        type: "control_request",
        requestId: "client_alias_transport_1",
        request: { subtype: "get_settings" }
      }));
      const line = await transport.receive();
      transport.closeInput();
      await transportRun;
      expect(controlPayload(decodeSdkJsonlLine(String(line).trim()))).toMatchObject({
        effective: { model: "client-alias-transport-model" }
      });
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  test("streams SDK messages and stores stable session metadata", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-sdk-client-"));
    const requests: any[] = [];
    const server = Bun.serve({
      port: 0,
      async fetch(request) {
        const body = await request.json();
        requests.push(body);
        if ((body.messages || []).some((message: any) => message.role === "tool")) {
          return Response.json({ choices: [{ message: { content: `sdk final: ${body.messages.at(-1).content}` } }] });
        }
        return Response.json({
          choices: [{
            message: {
              content: "",
              tool_calls: [{
                id: "call_sdk_read",
                type: "function",
                function: { name: "filesystem__read", arguments: JSON.stringify({ path: "sdk.txt" }) }
              }]
            }
          }]
        });
      }
    });
    try {
      await writeFile(path.join(root, "sdk.txt"), "sdk content");
      const settings = await loadSettings(root);
      const store = new JsonStateStore(path.join(root, "state.json"));
      const client = new AgentSdkClient({ settings, store });
      const session = client.createSession({
        sessionId: "session_test",
        protocol: "openai-chat",
        model: "mock",
        baseUrl: `http://127.0.0.1:${server.port}/v1`,
        apiKey: "test",
        permissionProfile: "auto",
        enabledTools: ["filesystem.read"],
        metadata: { feature: "sdk-test" }
      });

      const messages = [];
      for await (const message of session.query("read sdk file")) messages.push(message);

      expect(messages.map((message) => message.type)).toEqual([
        "user_message",
        "run_started",
        "tool_progress",
        "tool_progress",
        "tool_result",
        "assistant_message",
        "result"
      ]);
      expect(String((messages[0] as any).uuid).startsWith("msg_")).toBe(true);
      expect(messages.filter((message) => message.type === "tool_progress").map((message: any) => message.status)).toEqual([
        "started",
        "completed"
      ]);
      expect(messages.at(-1)).toMatchObject({
        type: "result",
        sessionId: "session_test",
        status: "finished",
        isError: false,
        subtype: "success",
        content: expect.stringContaining("sdk final:"),
        result: expect.stringContaining("sdk final:"),
        numTurns: 2
      });
      expect(requests[0].tools[0].function.name).toBe("filesystem__read");

      const storedRuns = await store.listRuns();
      expect(storedRuns[0].metadata).toMatchObject({
        sdk_session_id: "session_test",
        sdk_prompt: "read sdk file",
        feature: "sdk-test"
      });
    } finally {
      server.stop(true);
      await rm(root, { recursive: true, force: true });
    }
  });

  test("handles session control requests and applies updated session defaults", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-sdk-session-controls-"));
    const requests: any[] = [];
    const server = Bun.serve({
      port: 0,
      async fetch(request) {
        const body = await request.json();
        requests.push(body);
        const system = (body.messages || []).find((message: any) => message.role === "system");
        return Response.json({
          choices: [{
            message: {
              content: `model=${body.model}; system=${system?.content || ""}`
            }
          }]
        });
      }
    });
    try {
      const settings = await loadSettings(root);
      const store = new JsonStateStore(path.join(root, "state.json"));
      const client = new AgentSdkClient({ settings, store });
      const session = client.createSession({
        sessionId: "session_controls",
        protocol: "openai-chat",
        model: "initial-model",
        baseUrl: `http://127.0.0.1:${server.port}/v1`,
        apiKey: "test"
      });

      expect(controlPayload(await session.handleControlRequest({
        type: "control_request",
        requestId: "set_model_1",
        request: { subtype: "set_model", model: "session-control-model" }
      }))).toEqual({ model: "session-control-model" });

      expect(controlPayload(await session.handleControlRequest({
        type: "control_request",
        requestId: "flags_1",
        request: {
          subtype: "apply_flag_settings",
          settings: {
            systemPrompt: "session control system",
            allowedTools: ["filesystem.read"],
            replayUserMessages: true,
            maxThinkingTokens: 2048
          }
        }
      }))).toMatchObject({
        applied: {
          systemPrompt: "session control system",
          allowedTools: ["filesystem.read"],
          replayUserMessages: true,
          maxThinkingTokens: 2048
        },
        settings: {
          effective: {
            model: "session-control-model",
            systemPrompt: "session control system",
            allowedTools: ["filesystem.read"],
            replayUserMessages: true,
            maxThinkingTokens: 2048
          }
        }
      });

      expect(controlPayload(await session.handleControlRequest({
        type: "control_request",
        requestId: "settings_1",
        request: { subtype: "get_settings" }
      }))).toMatchObject({
        effective: {
          model: "session-control-model",
          systemPrompt: "session control system",
          allowedTools: ["filesystem.read"],
          replayUserMessages: true,
          maxThinkingTokens: 2048
        }
      });

      const result = await session.prompt("after session controls");
      const resultContent = result.content || result.result || "";

      expect(result).toMatchObject({
        type: "result",
        sessionId: "session_controls"
      });
      expect(resultContent).toContain("model=session-control-model");
      expect(resultContent).toContain("session control system");
      expect(requests[0].model).toBe("session-control-model");
      expect(requests[0].messages[0].content).toContain("session control system");
    } finally {
      server.stop(true);
      await rm(root, { recursive: true, force: true });
    }
  });

  test("lists session info and replays persisted SDK messages", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-sdk-sessions-"));
    const server = Bun.serve({
      port: 0,
      async fetch(request) {
        const body = await request.json();
        const user = (body.messages || []).find((message: any) => message.role === "user");
        return Response.json({ choices: [{ message: { content: `answer: ${user?.content || ""}` } }] });
      }
    });
    let clock = Date.now();
    const clockSpy = spyOn(Date, "now").mockImplementation(() => ++clock);
    try {
      const settings = await loadSettings(root);
      const store = new JsonStateStore(path.join(root, "state.json"));
      const client = new AgentSdkClient({ settings, store });
      const session = client.createSession({
        sessionId: "session_replay",
        protocol: "openai-chat",
        model: "mock",
        baseUrl: `http://127.0.0.1:${server.port}/v1`,
        apiKey: "test",
        metadata: { tag: "replay" }
      });

      await session.prompt("first prompt");
      await session.prompt("second prompt");

      const sessions = await client.listSessions();
      expect(sessions).toHaveLength(1);
      expect(sessions[0]).toMatchObject({
        sessionId: "session_replay",
        firstPrompt: "first prompt",
        runCount: 2,
        status: "finished"
      });
      expect(sessions[0].createdAt).toBeGreaterThan(1_000_000_000_000);
      expect(sessions[0].lastModified).toBeGreaterThanOrEqual(sessions[0].createdAt);
      expect(sessions[0].created_at).toBe(sessions[0].createdAt);
      expect(sessions[0].last_modified).toBe(sessions[0].lastModified);
      expect(sessions[0].session_id).toBe("session_replay");
      expect(sessions[0].first_prompt).toBe("first prompt");
      expect(sessions[0].runIds).toHaveLength(2);
      expect(sessions[0].run_ids).toEqual(sessions[0].runIds);
      expect(sessions[0].latestRunId).toBe(sessions[0].runIds.at(-1));
      expect(sessions[0].latest_run_id).toBe(sessions[0].latestRunId);
      expect(sessions[0].metadata.tag).toBe("replay");
      expect(Object.keys(sessions[0])).not.toContain("session_id");
      expect(Object.keys(sessions[0])).not.toContain("run_ids");

      const info = await session.info();
      expect(info?.sessionId).toBe("session_replay");
      expect(info?.session_id).toBe("session_replay");
      expect(info?.runCount).toBe(2);

      const replayed = await session.messages();
      expect(replayed.filter((message) => message.type === "user_message").map((message: any) => message.content)).toEqual([
        "first prompt",
        "second prompt"
      ]);
      expect(replayed.filter((message) => message.type === "run_started")).toHaveLength(2);
      expect(replayed.filter((message) => message.type === "assistant_message").map((message: any) => message.content)).toEqual([
        "answer: first prompt",
        "answer: second prompt"
      ]);
      expect(replayed.at(-1)).toMatchObject({
        type: "result",
        sessionId: "session_replay",
        status: "finished"
      });
    } finally {
      clockSpy.mockRestore();
      server.stop(true);
      await rm(root, { recursive: true, force: true });
    }
  });

  test("manages SDK session metadata, filters, message slices, and forks", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-sdk-session-management-"));
    let clock = Date.now();
    const clockSpy = spyOn(Date, "now").mockImplementation(() => ++clock);
    try {
      const settings = await loadSettings(root);
      const store = new JsonStateStore(path.join(root, "state.json"));
      const client = new AgentSdkClient({ settings, store });
      const firstManagedRunId = await createStoredSdkRun(store, {
        sessionId: "session_manage",
        userMessageId: "message_manage_1",
        prompt: "first managed prompt",
        cwd: "/workspace/manage",
        assistantMessageId: "assistant_manage_1",
        answer: "managed answer 1",
        tenantId: "tenant_manage",
        userId: "user_manage",
        agentId: "agent_manage",
        includeSystemState: true
      });
      await createStoredSdkRun(store, {
        sessionId: "session_manage",
        userMessageId: "message_manage_2",
        prompt: "second managed prompt",
        cwd: "/workspace/manage",
        assistantMessageId: "assistant_manage_2",
        answer: "managed answer 2",
        tenantId: "tenant_manage",
        userId: "user_manage",
        agentId: "agent_manage"
      });
      await createStoredSdkRun(store, {
        sessionId: "session_other",
        userMessageId: "message_other",
        prompt: "other prompt",
        cwd: "/workspace/other",
        assistantMessageId: "assistant_other",
        answer: "other answer",
        tenantId: "tenant_other",
        userId: "user_other",
        agentId: "agent_other"
      });
      const standaloneRunId = await createStoredSdkRun(store, {
        userMessageId: "message_standalone",
        prompt: "standalone prompt",
        cwd: "/workspace/standalone",
        assistantMessageId: "assistant_standalone",
        answer: "standalone answer"
      });

      const session = client.createSession({ sessionId: "session_manage" });
      await client.rename_session("session_manage", "Managed Session");
      await client.tag_session("session_manage", "important");

      expect(await client.list_sessions({ cwd: "/workspace/manage" })).toEqual([
        expect.objectContaining({
          sessionId: "session_manage",
          summary: "Managed Session",
          customTitle: "Managed Session",
          tag: "important",
          cwd: "/workspace/manage",
          runCount: 2
        })
      ]);
      expect(await client.listSessions({ tenant_id: "tenant_manage", user_id: "user_manage", agent_id: "agent_manage" })).toEqual([
        expect.objectContaining({ sessionId: "session_manage" })
      ]);
      const limitedSessionIds = (await client.listSessions({ limit: 2 })).map((info) => info.sessionId);
      expect(limitedSessionIds).toHaveLength(2);
      expect(new Set(limitedSessionIds).size).toBe(2);
      expect(limitedSessionIds).toContain("session_manage");
      expect((await client.listSessions({ offset: 1, limit: 1 })).map((info) => info.sessionId)).toHaveLength(1);
      expect(await client.get_session_info(standaloneRunId)).toMatchObject({
        sessionId: standaloneRunId,
        firstPrompt: "standalone prompt",
        runCount: 1,
        metadata: { run_count: 1 }
      });
      expect((await client.get_session_messages(standaloneRunId))
        .filter((message) => message.type === "assistant_message")
        .map((message: any) => message.content)).toEqual(["standalone answer"]);

      const slicedMessages = await session.messages({ offset: 1, limit: 3, include_system_messages: false });
      expect(slicedMessages.map((message) => message.type)).toEqual([
        "run_started",
        "assistant_message",
        "result"
      ]);
      expect(slicedMessages.some((message) => message.type === "system")).toBe(false);
      await expect(client.listSessions({ limit: 201 })).rejects.toThrow("SDK option limit must be an integer between 0 and 200");
      await expect(client.listSessions({ offset: -1 })).rejects.toThrow("SDK option offset must be a non-negative integer");
      await expect(client.getSessionMessages(standaloneRunId, { limit: 1001 })).rejects.toThrow("SDK option limit must be an integer between 0 and 1000");
      await expect(client.getSessionMessages(standaloneRunId, { offset: -1 })).rejects.toThrow("SDK option offset must be a non-negative integer");
      expect(await client.getSessionInfo(firstManagedRunId)).toMatchObject({
        sessionId: "session_manage",
        firstPrompt: "first managed prompt"
      });

      const forked = await session.fork({ title: "Managed Fork", up_to_message_id: "assistant_manage_1" });
      const forkedInfo = await forked.info();
      expect(forkedInfo).toMatchObject({
        customTitle: "Managed Fork",
        runCount: 1,
        firstPrompt: "first managed prompt"
      });
      expect(forkedInfo?.metadata).toMatchObject({
        sdk_forked_from_session_id: "session_manage"
      });

      const forkedMessages = await forked.messages();
      expect(forkedMessages.filter((message) => message.type === "assistant_message").map((message: any) => message.content)).toEqual([
        "managed answer 1"
      ]);
      expect(forkedMessages.some((message: any) => message.content === "managed answer 2")).toBe(false);

      const clientFork = await client.fork_session("session_manage", {
        title: "Client Alias Fork",
        up_to_message_id: "assistant_manage_1"
      });
      expect(clientFork.sessionId).toMatch(/^session_/);
      expect(clientFork.session_id).toBe(clientFork.sessionId);
      expect(clientFork.runIds).toHaveLength(1);
      expect(clientFork.run_ids).toEqual(clientFork.runIds);
      expect(Object.keys(clientFork)).not.toContain("session_id");
      expect(Object.keys(clientFork)).not.toContain("run_ids");
    } finally {
      clockSpy.mockRestore();
      await rm(root, { recursive: true, force: true });
    }
  });

  test("resumes stored SDK sessions with validated defaults", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-sdk-session-resume-"));
    try {
      const settings = await loadSettings(root);
      const store = new JsonStateStore(path.join(root, "state.json"));
      const client = new AgentSdkClient({ settings, store });
      await createStoredSdkRun(store, {
        sessionId: "session_resume",
        userMessageId: "message_resume_1",
        prompt: "resume prompt",
        cwd: "/workspace/resume",
        assistantMessageId: "assistant_resume_1",
        answer: "resume answer"
      });

      const resumed = await client.resume_session("session_resume", {
        model: "resume-model",
        permissionMode: "dontAsk",
        metadata: { source: "resume-test" }
      });
      const settingsPayload = controlPayload(await resumed.handleControlRequest({
        type: "control_request",
        requestId: "resume_settings_1",
        request: { subtype: "get_settings" }
      }));

      expect(await resumed.info()).toMatchObject({
        sessionId: "session_resume",
        firstPrompt: "resume prompt"
      });
      expect(settingsPayload).toMatchObject({
        effective: {
          model: "resume-model",
          permissionMode: "dontAsk",
          permissionProfile: "deny",
          sessionId: "session_resume"
        },
        sources: [
          { source: "flagSettings", settings: {} },
          { source: "sdkOptions", settings: { source: "resume-test" } }
        ]
      });
      await expect(client.resume_session("missing_session")).rejects.toThrow("session not found: missing_session");
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  test("replays SDK system init messages from stored run metadata", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-sdk-system-init-replay-"));
    try {
      const settings = await loadSettings(root);
      const store = new JsonStateStore(path.join(root, "state.json"));
      const client = new AgentSdkClient({ settings, store });
      await createStoredSdkRun(store, {
        sessionId: "session_system_init",
        userMessageId: "message_system_init",
        prompt: "system init replay",
        cwd: "/workspace/system-init",
        assistantMessageId: "assistant_system_init",
        answer: "system init answer",
        model: "spec-model",
        enabledTools: ["filesystem.read"],
        permissionProfile: "deny",
        metadata: {
          sdk_init_model: "metadata-model",
          sdk_init_tools_json: "[\"filesystem.write\"]",
          sdk_skills: "review,docs",
          sdk_betas: "[\"beta-a\"]",
          apiKeySource: "user",
          output_style: "compact",
          fast_mode_state: "on",
          sdk_plugins: "[{\"name\":\"plugin-a\",\"path\":\"/plugins/a\",\"source\":\"test\"}]"
        }
      });

      const messages = await client.getSessionMessages("session_system_init");
      const initMessage = messages.find((message) => message.type === "system" && (message as any).subtype === "init");

      expect(messages[0]).toMatchObject({ type: "system", subtype: "init" });
      expect(initMessage).toMatchObject({
        type: "system",
        subtype: "init",
        sessionId: "session_system_init",
        model: "metadata-model",
        tools: ["filesystem.write"],
        skills: ["review", "docs"],
        betas: ["beta-a"],
        apiKeySource: "user",
        permissionMode: "dontAsk",
        outputStyle: "compact",
        fastModeState: "on",
        plugins: [{ name: "plugin-a", path: "/plugins/a", source: "test" }]
      });
      expect((await client.getSessionMessages("session_system_init", { include_system_messages: false }))
        .some((message) => message.type === "system")).toBe(false);
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  test("replays SDK system init messages from stored spec metadata fallback", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-sdk-system-init-spec-metadata-"));
    const stateFile = path.join(root, "state.json");
    try {
      const settings = await loadSettings(root);
      const store = new JsonStateStore(stateFile);
      const client = new AgentSdkClient({ settings, store });
      const runId = await createStoredSdkRun(store, {
        sessionId: "session_system_init_spec",
        userMessageId: "message_system_init_spec",
        prompt: "system init spec replay",
        cwd: "/workspace/system-init-spec",
        assistantMessageId: "assistant_system_init_spec",
        answer: "system init spec answer",
        metadata: {
          sdk_init_model: "spec-metadata-model",
          sdk_init_tools_json: "[\"filesystem.write\"]",
          sdk_betas: "[\"beta-spec\"]",
          apiKeySource: "oauth",
          output_style: "compact"
        }
      });
      await removeStoredRunMetadataKeys(stateFile, runId, [
        "sdk_init_model",
        "sdk_init_tools_json",
        "sdk_betas",
        "apiKeySource",
        "output_style"
      ]);

      const messages = await client.getSessionMessages("session_system_init_spec");
      const initMessage = messages.find((message) => message.type === "system" && (message as any).subtype === "init");

      expect(initMessage).toMatchObject({
        type: "system",
        subtype: "init",
        sessionId: "session_system_init_spec",
        model: "spec-metadata-model",
        tools: ["filesystem.write"],
        betas: ["beta-spec"],
        apiKeySource: "oauth",
        outputStyle: "compact"
      });
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  test("coalesces session info from latest metadata and first non-empty fields", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-sdk-session-info-coalesce-"));
    try {
      const settings = await loadSettings(root);
      const store = new JsonStateStore(path.join(root, "state.json"));
      const client = new AgentSdkClient({ settings, store });
      const firstRun = await store.startRun(specFromPayload({
        message: "",
        metadata: {
          sdk_session_id: "session_info_coalesce",
          sdk_cwd: "/workspace/first"
        }
      }));
      await store.finishRun(firstRun.run_id, "finished");
      await nextClockTick();
      const secondRun = await store.startRun(specFromPayload({
        message: "first visible prompt",
        metadata: {
          sdk_session_id: "session_info_coalesce",
          sdk_first_prompt: "first visible prompt"
        }
      }));
      await store.finishRun(secondRun.run_id, "finished");
      await nextClockTick();
      await store.updateRunMetadata(firstRun.run_id, {
        sdk_title: "Latest Metadata",
        sdk_tag: "latest",
        sdk_cwd: "/workspace/latest"
      });

      expect(await client.getSessionInfo("session_info_coalesce")).toMatchObject({
        sessionId: "session_info_coalesce",
        summary: "Latest Metadata",
        customTitle: "Latest Metadata",
        firstPrompt: "first visible prompt",
        cwd: "/workspace/latest",
        tag: "latest",
        runCount: 2,
        metadata: {
          sdk_title: "Latest Metadata",
          sdk_tag: "latest",
          run_count: 2
        }
      });
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  test("queues, cancels, and drains SDK async user messages by priority", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-sdk-async-messages-"));
    const requests: any[] = [];
    const server = Bun.serve({
      port: 0,
      async fetch(request) {
        const body = await request.json();
        requests.push(body);
        const user = (body.messages || []).find((message: any) => message.role === "user");
        return Response.json({ choices: [{ message: { content: `async answer: ${user?.content || ""}` } }] });
      }
    });
    try {
      const settings = await loadSettings(root);
      const store = new JsonStateStore(path.join(root, "state.json"));
      const client = new AgentSdkClient({ settings, store });
      const session = client.createSession({
        sessionId: "session_async",
        protocol: "openai-chat",
        model: "mock",
        baseUrl: `http://127.0.0.1:${server.port}/v1`,
        apiKey: "test"
      });

      const later = session.enqueueAsyncMessage("queued later", "later");
      expect(later.uuid.startsWith("msg_")).toBe(true);
      session.enqueueAsyncMessage({ uuid: "queued_next", content: "queued next" }, "next");
      const legacy = session.enqueueAsyncMessage({
        type: "user",
        session_id: "wrong_session",
        uuid: "queued_legacy",
        message: {
          role: "user",
          content: [{ type: "text", text: "queued " }, { type: "text", text: "legacy" }]
        },
        priority: "next",
        isReplay: false
      });
      session.enqueueAsyncMessage("queued now", "now");

      expect(legacy).toMatchObject({
        type: "user_message",
        uuid: "queued_legacy",
        sessionId: "session_async",
        content: "queued legacy",
        priority: "next",
        isReplay: false
      });

      expect(session.listAsyncMessages().map((message) => message.content)).toEqual([
        "queued now",
        "queued next",
        "queued legacy",
        "queued later"
      ]);
      expect(() => session.enqueueAsyncMessage({ content: "bad priority", priority: "soon" as any })).toThrow(
        "async message priority must be now, next, or later"
      );
      expect(() => client.enqueueAsyncMessage("bad option priority", {
        session_id: "session_async",
        priority: "soon" as any
      })).toThrow("async message priority must be now, next, or later");
      expect(client.cancelAsyncMessage(later.uuid)).toEqual({ cancelled: true, queued: 1 });
      const controlCancelled = session.enqueueAsyncMessage("queued control cancel", "later");
      expect(controlPayload(await session.handleControlRequest({
        type: "control_request",
        requestId: "cancel_queued_control",
        request: { subtype: "cancel_async_message", messageUuid: controlCancelled.uuid }
      }))).toEqual({ cancelled: true });
      expect(session.listAsyncMessages().map((message) => message.content)).toEqual([
        "queued now",
        "queued next",
        "queued legacy"
      ]);
      session.enqueueAsyncMessage("queued later again", "later");

      const messages = [];
      for await (const message of session.query("initial async prompt")) messages.push(message);

      expect(messages.filter((message) => message.type === "user_message").map((message: any) => message.content)).toEqual([
        "initial async prompt",
        "queued now",
        "queued next",
        "queued legacy",
        "queued later again"
      ]);
      expect(messages.filter((message) => message.type === "result").map((message: any) => message.content)).toEqual([
        "async answer: initial async prompt",
        "async answer: queued now",
        "async answer: queued next",
        "async answer: queued legacy",
        "async answer: queued later again"
      ]);
      const replayedUserMessages = (await session.messages())
        .filter((message) => message.type === "user_message") as any[];
      expect(replayedUserMessages.map((message) => message.content)).toEqual([
        "initial async prompt",
        "queued now",
        "queued next",
        "queued legacy",
        "queued later again"
      ]);
      expect(replayedUserMessages.find((message) => message.uuid === "queued_legacy")).toMatchObject({
        sessionId: "session_async",
        message: {
          role: "user",
          content: [{ type: "text", text: "queued " }, { type: "text", text: "legacy" }]
        },
        priority: "next",
        isReplay: false
      });
      expect(session.listAsyncMessages()).toEqual([]);
      client.enqueue_async_message("queued snake option", { session_id: "session_async", priority: "next" });
      expect(client.list_async_messages({ session_id: "session_async" }).map((message) => message.content)).toEqual([
        "queued snake option"
      ]);
      expect(client.dequeue_async_message({ session_id: "session_async" })?.content).toBe("queued snake option");
      expect(client.list_async_messages({ session_id: "session_async" })).toEqual([]);
      expect(requests).toHaveLength(5);
    } finally {
      server.stop(true);
      await rm(root, { recursive: true, force: true });
    }
  });

  test("wakes SDK sleep waits when async user messages are queued", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-sdk-async-sleep-wake-"));
    const requests: any[] = [];
    let issuedSleepCall = false;
    const server = Bun.serve({
      port: 0,
      async fetch(request) {
        const body = await request.json();
        requests.push(body);
        const messages = body.messages || [];
        const lastMessage = messages.at(-1);
        if (lastMessage?.role === "tool") {
          return Response.json({ choices: [{ message: { content: `sleep result: ${lastMessage.content}` } }] });
        }
        const users = messages.filter((message: any) => message.role === "user");
        const user = users.at(-1);
        if (user?.content === "sleep before async" && !issuedSleepCall) {
          issuedSleepCall = true;
          return Response.json({
            choices: [{
              message: {
                content: "",
                tool_calls: [{
                  id: "call_sleep_wait",
                  type: "function",
                  function: {
                    name: "sleep__wait",
                    arguments: JSON.stringify({
                      duration_seconds: 5,
                      reason: "waiting for async message"
                    })
                  }
                }]
              }
            }]
          });
        }
        return Response.json({ choices: [{ message: { content: `async answer: ${user?.content || ""}` } }] });
      }
    });
    try {
      const settings = await loadSettings(root);
      const store = new JsonStateStore(path.join(root, "state.json"));
      const client = new AgentSdkClient({ settings, store });
      const session = client.createSession({
        sessionId: "session_async_sleep",
        protocol: "openai-chat",
        model: "mock",
        baseUrl: `http://127.0.0.1:${server.port}/v1`,
        apiKey: "test",
        permissionProfile: "auto",
        enabledTools: ["sleep.wait"]
      });

      const messages: SdkWireMessage[] = [];
      const queryDone = (async () => {
        for await (const message of session.query("sleep before async")) messages.push(message);
        return messages;
      })();

      await waitFor(() => requests.length === 1);
      session.enqueueAsyncMessage("queued wake", "next");
      const completedMessages = await Promise.race([
        queryDone,
        delay(1500).then(() => {
          throw new Error("timed out waiting for sleep wake");
        })
      ]);

      expect(completedMessages
        .filter((message) => message.type === "user_message")
        .map((message: any) => message.content)).toEqual([
          "sleep before async",
          "queued wake"
        ]);
      expect(completedMessages
        .filter((message) => message.type === "result")
        .map((message: any) => message.content)
        .at(-1)).toBe("async answer: queued wake");
      const sleepFollowUpRequest = requests.find((requestBody) => (requestBody.messages || []).at(-1)?.role === "tool");
      const sleepToolPayload = JSON.parse(sleepFollowUpRequest.messages.at(-1).content);
      expect(sleepToolPayload).toMatchObject({
        requested_seconds: 5,
        reason: "waiting for async message",
        woke_for_notification: true
      });
      expect(sleepToolPayload.slept_seconds).toBeLessThan(1.5);
      expect(requests).toHaveLength(3);
    } finally {
      server.stop(true);
      await rm(root, { recursive: true, force: true });
    }
  });

  test("session prompt drains queued async messages and returns the final result", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-sdk-prompt-async-drain-"));
    const requests: any[] = [];
    const server = Bun.serve({
      port: 0,
      async fetch(request) {
        const body = await request.json();
        requests.push(body);
        const users = (body.messages || []).filter((message: any) => message.role === "user");
        const user = users.at(-1);
        return Response.json({ choices: [{ message: { content: `prompt answer: ${user?.content || ""}` } }] });
      }
    });
    try {
      const settings = await loadSettings(root);
      const store = new JsonStateStore(path.join(root, "state.json"));
      const client = new AgentSdkClient({ settings, store });
      const session = client.createSession({
        sessionId: "session_prompt_async",
        protocol: "openai-chat",
        model: "mock",
        baseUrl: `http://127.0.0.1:${server.port}/v1`,
        apiKey: "test"
      });

      session.enqueueAsyncMessage("queued prompt follow-up", "next");

      const result = await session.prompt("initial prompt");

      expect(result).toMatchObject({
        type: "result",
        sessionId: "session_prompt_async",
        content: "prompt answer: queued prompt follow-up"
      });
      expect(session.listAsyncMessages()).toEqual([]);
      expect((await session.messages())
        .filter((message) => message.type === "user_message")
        .map((message: any) => message.content)).toEqual([
          "initial prompt",
          "queued prompt follow-up"
        ]);
      expect(requests).toHaveLength(2);
    } finally {
      server.stop(true);
      await rm(root, { recursive: true, force: true });
    }
  });

  test("compacts SDK session replay around compact boundaries", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-sdk-session-compaction-"));
    try {
      const settings = await loadSettings(root);
      const store = new JsonStateStore(path.join(root, "state.json"));
      const client = new AgentSdkClient({ settings, store });
      const droppedRun = await store.startRun(specFromPayload({
        message: "dropped run",
        metadata: {
          sdk_session_id: "session_compact",
          sdk_prompt: "dropped run",
          sdk_user_message_uuid: "message_drop_run"
        }
      }));
      await store.recordEvent(droppedRun.run_id, {
        type: "model_message",
        name: "assistant",
        payload: { uuid: "msg_old_run", content: "old run before compact" }
      });
      await store.finishRun(droppedRun.run_id, "finished");

      const run = await store.startRun(specFromPayload({
        message: "compact replay",
        metadata: {
          sdk_session_id: "session_compact",
          sdk_prompt: "compact replay",
          sdk_user_message_uuid: "message_compact"
        }
      }));
      await store.recordEvent(run.run_id, {
        type: "model_message",
        name: "assistant",
        payload: { uuid: "msg_drop", content: "drop before compact" }
      });
      await store.recordEvent(run.run_id, {
        type: "model_message",
        name: "assistant",
        payload: { uuid: "msg_keep_head", content: "keep head" }
      });
      await store.recordEvent(run.run_id, {
        type: "model_message",
        name: "assistant",
        payload: { uuid: "msg_keep_tail", content: "keep tail" }
      });
      await store.recordEvent(run.run_id, {
        type: "compact_boundary",
        name: "context",
        payload: {
          uuid: "compact_1",
          trigger: "auto",
          pre_tokens: 100,
          post_tokens: 40,
          before_messages: 3,
          after_messages: 2,
          dropped_messages: 1,
          preserved_segment: {
            head_uuid: "msg_keep_head",
            tail_uuid: "msg_keep_tail"
          }
        }
      });
      await store.recordEvent(run.run_id, {
        type: "model_message",
        name: "assistant",
        payload: { uuid: "msg_after", content: "after compact" }
      });
      await store.recordEvent(run.run_id, {
        type: "done",
        name: "assistant",
        payload: { status: "finished", content: "after compact" }
      });
      await store.finishRun(run.run_id, "finished");

      const messages = await client.getSessionMessages("session_compact");

      expect(messages.find((message) => message.type === "system" && (message as any).subtype === "compact_boundary")).toMatchObject({
        compactMetadata: {
          trigger: "auto",
          preTokens: 100,
          postTokens: 40,
          beforeMessages: 3,
          afterMessages: 2,
          droppedMessages: 1,
          preservedSegment: {
            head_uuid: "msg_keep_head",
            tail_uuid: "msg_keep_tail"
          }
        },
        uuid: "compact_1"
      });
      expect(messages.filter((message) => message.type === "assistant_message").map((message: any) => message.content)).toEqual([
        "keep head",
        "keep tail",
        "after compact"
      ]);
      expect(messages.filter((message) => message.type === "user_message").map((message: any) => message.content)).toEqual([
        "compact replay"
      ]);
      expect(messages.some((message: any) => message.content === "old run before compact")).toBe(false);
      expect(messages.some((message: any) => message.content === "drop before compact")).toBe(false);
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  test("keeps compact replay order when preserved segments span runs", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-sdk-session-cross-run-compaction-"));
    try {
      const settings = await loadSettings(root);
      const store = new JsonStateStore(path.join(root, "state.json"));
      const client = new AgentSdkClient({ settings, store });
      const preservedRun = await store.startRun(specFromPayload({
        message: "preserved run",
        metadata: {
          sdk_session_id: "session_cross_compact",
          sdk_prompt: "preserved run",
          sdk_user_message_uuid: "message_preserved_run"
        }
      }));
      await store.recordEvent(preservedRun.run_id, {
        type: "model_message",
        name: "assistant",
        payload: { uuid: "msg_preserved_head", content: "preserved head" }
      });
      await store.recordEvent(preservedRun.run_id, {
        type: "model_message",
        name: "assistant",
        payload: { uuid: "msg_preserved_tail", content: "preserved tail" }
      });
      await store.finishRun(preservedRun.run_id, "finished");

      const compactRun = await store.startRun(specFromPayload({
        message: "compact run",
        metadata: {
          sdk_session_id: "session_cross_compact",
          sdk_prompt: "compact run",
          sdk_user_message_uuid: "message_compact_run"
        }
      }));
      await store.recordEvent(compactRun.run_id, {
        type: "model_message",
        name: "assistant",
        payload: { uuid: "msg_before_boundary", content: "before boundary" }
      });
      await store.recordEvent(compactRun.run_id, {
        type: "compact_boundary",
        name: "context",
        payload: {
          uuid: "compact_cross_run",
          preserved_segment: {
            head_uuid: "msg_preserved_head",
            tail_uuid: "msg_preserved_tail"
          }
        }
      });
      await store.recordEvent(compactRun.run_id, {
        type: "model_message",
        name: "assistant",
        payload: { uuid: "msg_after_boundary", content: "after boundary" }
      });
      await store.finishRun(compactRun.run_id, "finished");

      const messages = await client.getSessionMessages("session_cross_compact");
      const compactBoundaryIndex = messages.findIndex(
        (message) => message.type === "system" && (message as any).subtype === "compact_boundary"
      );
      const preservedHeadIndex = messages.findIndex((message: any) => message.content === "preserved head");
      const afterBoundaryIndex = messages.findIndex((message: any) => message.content === "after boundary");

      expect(compactBoundaryIndex).toBeGreaterThanOrEqual(0);
      expect(compactBoundaryIndex).toBeLessThan(preservedHeadIndex);
      expect(preservedHeadIndex).toBeLessThan(afterBoundaryIndex);
      expect(messages.some((message: any) => message.content === "before boundary")).toBe(false);
      expect(messages.filter((message) => message.type === "assistant_message").map((message: any) => message.content)).toEqual([
        "preserved head",
        "preserved tail",
        "after boundary"
      ]);
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  test("resumes pending approvals through the SDK session", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-sdk-approval-"));
    const requests: any[] = [];
    const server = Bun.serve({
      port: 0,
      async fetch(request) {
        const body = await request.json();
        requests.push(body);
        if (requests.length === 1) {
          return Response.json({
            choices: [{
              message: {
                content: "",
                tool_calls: [{
                  id: "call_sdk_approval_read",
                  type: "function",
                  function: { name: "filesystem__read", arguments: JSON.stringify({ path: "approval.txt" }) }
                }]
              }
            }]
          });
        }
        return Response.json({ choices: [{ message: { content: `approved sdk: ${body.messages.at(-1).content}` } }] });
      }
    });
    try {
      await writeFile(path.join(root, "approval.txt"), "approval content");
      const settings = await loadSettings(root);
      const store = new JsonStateStore(path.join(root, "state.json"));
      const client = new AgentSdkClient({ settings, store });
      const session = client.createSession({
        sessionId: "session_approval",
        protocol: "openai-chat",
        model: "mock",
        baseUrl: `http://127.0.0.1:${server.port}/v1`,
        apiKey: "test",
        permissionProfile: "ask",
        enabledTools: ["filesystem.read"]
      });

      const pausedMessages = [];
      for await (const message of session.query("read with approval")) pausedMessages.push(message);
      const pausedResult = pausedMessages.at(-1);
      const approval = pausedMessages.find((message) => message.type === "approval_required");

      expect(approval).toMatchObject({
        type: "approval_required",
        sessionId: "session_approval",
        toolName: "filesystem__read",
        approvalId: "call_sdk_approval_read"
      });
      expect(pausedResult).toMatchObject({
        type: "result",
        sessionId: "session_approval",
        status: "awaiting_approval"
      });

      const runId = (pausedResult as any).runId;
      const resumedMessages = [];
      for await (const message of session.resumeApproval(runId, true)) resumedMessages.push(message);

      expect(resumedMessages.map((message) => message.type)).toEqual([
        "tool_progress",
        "tool_progress",
        "tool_result",
        "assistant_message",
        "result"
      ]);
      expect(resumedMessages.filter((message) => message.type === "tool_progress").map((message: any) => message.status)).toEqual([
        "started",
        "completed"
      ]);
      expect(resumedMessages.at(-1)).toMatchObject({
        type: "result",
        sessionId: "session_approval",
        status: "finished"
      });
      expect((resumedMessages.at(-1) as any).content).toContain("approval content");

      const stored = await store.loadRun(runId);
      expect(stored?.status).toBe("finished");
      expect(stored?.pending_approval).toBeUndefined();
      expect((await session.messages()).some((message) => message.type === "approval_required")).toBe(true);
    } finally {
      server.stop(true);
      await rm(root, { recursive: true, force: true });
    }
  });

  test("projects persisted tool events into structured SDK system messages", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-sdk-event-projection-"));
    try {
      const settings = await loadSettings(root);
      const store = new JsonStateStore(path.join(root, "state.json"));
      const client = new AgentSdkClient({ settings, store });
      const run = await store.startRun(specFromPayload({
        message: "project task event",
        metadata: {
          sdk_session_id: "session_projection",
          sdk_prompt: "project task event",
          sdk_user_message_uuid: "message_projection"
        }
      }));
      await store.recordEvent(run.run_id, {
        type: "tool_start",
        name: "task.update",
        payload: {
          tool_call_id: "call_task",
          name: "task.update",
          arguments: { task_id: "task_1" }
        }
      });
      await store.recordEvent(run.run_id, {
        type: "tool_result",
        name: "task.update",
        payload: {
          tool_call_id: "call_task",
          name: "task.update",
          is_error: false,
          content: JSON.stringify({
            task: { task_id: "task_1", title: "Implement SDK projection", status: "running" },
            step: { name: "shell.run", output: "compiled" },
            usage: { total_tokens: 12, tool_uses: 2, duration_ms: 34 },
            artifact: {
              artifact_id: "file_1",
              filename: "projection.md",
              processed_at: "2026-06-08T00:00:00.000Z"
            }
          })
        }
      });
      await store.finishRun(run.run_id, "finished");

      const messages = await client.getSessionMessages("session_projection");

      expect(messages.find((message) => message.type === "tool_progress" && (message as any).status === "started")).toMatchObject({
        toolCallId: "call_task",
        name: "task.update",
        input: { task_id: "task_1" }
      });
      expect(messages.find((message) => message.type === "tool_progress" && (message as any).status === "completed")).toMatchObject({
        toolCallId: "call_task",
        name: "task.update"
      });
      expect(messages.find((message) => message.type === "system" && (message as any).subtype === "task_progress")).toMatchObject({
        taskId: "task_1",
        toolUseId: "call_task",
        lastToolName: "shell.run",
        summary: "compiled",
        usage: { totalTokens: 12, toolUses: 2, durationMs: 34 }
      });
      expect(messages.find((message) => message.type === "system" && (message as any).subtype === "files_persisted")).toMatchObject({
        files: [{ filename: "projection.md", fileId: "file_1" }],
        failed: [],
        processedAt: "2026-06-08T00:00:00.000Z"
      });
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });
});

async function createStoredSdkRun(
  store: JsonStateStore,
  options: {
    sessionId?: string;
    userMessageId: string;
    prompt: string;
    cwd: string;
    assistantMessageId: string;
    answer: string;
    tenantId?: string;
    userId?: string;
    agentId?: string;
    includeSystemState?: boolean;
    model?: string;
    enabledTools?: string[];
    permissionProfile?: string;
    metadata?: Record<string, string>;
  }
): Promise<string> {
  const run = await store.startRun(specFromPayload({
    message: options.prompt,
    model: options.model,
    enabled_tools: options.enabledTools,
    permission_profile: options.permissionProfile,
    tenant_id: options.tenantId || "",
    user_id: options.userId || "",
    agent_id: options.agentId || "",
    metadata: {
      ...(options.sessionId ? { sdk_session_id: options.sessionId } : {}),
      sdk_first_prompt: options.prompt,
      sdk_prompt: options.prompt,
      sdk_user_message_uuid: options.userMessageId,
      sdk_cwd: options.cwd,
      ...(options.metadata || {})
    }
  }));
  if (options.includeSystemState) {
    await store.recordEvent(run.run_id, {
      type: "session_state_changed",
      name: "session",
      payload: { state: "running" }
    });
  }
  await store.recordEvent(run.run_id, {
    type: "model_message",
    name: "assistant",
    payload: {
      uuid: options.assistantMessageId,
      content: options.answer
    }
  });
  await store.recordEvent(run.run_id, {
    type: "done",
    name: "assistant",
    payload: {
      status: "finished",
      content: options.answer
    }
  });
  await store.finishRun(run.run_id, "finished");
  return run.run_id;
}

async function removeStoredRunMetadataKeys(
  stateFile: string,
  runId: string,
  keys: string[]
): Promise<void> {
  const state = JSON.parse(await readFile(stateFile, "utf8"));
  const run = Array.isArray(state.runs)
    ? state.runs.find((item: any) => item.run_id === runId)
    : undefined;
  if (!run?.metadata) throw new Error(`stored run not found: ${runId}`);
  for (const key of keys) delete run.metadata[key];
  await writeFile(stateFile, JSON.stringify(state, null, 2));
}

async function nextClockTick(): Promise<void> {
  await delay(2);
}

function delay(milliseconds: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

async function waitFor(predicate: () => boolean): Promise<void> {
  for (let attempt = 0; attempt < 100; attempt += 1) {
    if (predicate()) return;
    await delay(10);
  }
  throw new Error("condition was not reached");
}

function controlPayload(message: any): Record<string, any> {
  if (message.type !== "control_response" || message.response.subtype !== "success") {
    throw new Error("expected control success response");
  }
  return message.response.response as Record<string, any>;
}

async function collectSdkWireMessages(messages: AsyncIterable<SdkWireMessage>): Promise<SdkWireMessage[]> {
  const collected: SdkWireMessage[] = [];
  for await (const message of messages) collected.push(message);
  return collected;
}
