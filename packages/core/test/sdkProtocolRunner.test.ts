import { modelStreamResponse } from "./fixtures/modelResponse.js";
import { describe, expect, test } from "bun:test";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import {
  AgentSdkClient,
  createSdkControlSuccessResponse,
  decodeSdkJsonlLine,
  encodeSdkJsonlMessage,
  SdkHybridJsonlTransport,
  SdkQueueJsonlTransport,
  SdkSseJsonlTransport,
  SdkStructuredIo,
  type SdkWireMessage
} from "@kevin/core/sdk";
import { JsonStateStore, loadSettings, specFromPayload } from "../src/index.js";

describe("SDK protocol runner", () => {
  test("runs wire user messages through the AgentSdkClient", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-sdk-wire-"));
    const server = Bun.serve({
      port: 0,
      async fetch(request) {
        const body = await request.json();
        const user = (body.messages || []).find((message: any) => message.role === "user");
        return modelStreamResponse({ choices: [{ message: { content: `wire answer: ${user?.content || ""}` } }] });
      }
    });
    try {
      const client = await sdkClient(root);
      const outputs = await collectWireMessages(client.runWireMessages([{
        type: "user_message",
        uuid: "wire_message_1",
        sessionId: "wire_session",
        content: "hello wire"
      }], modelOptions(server.port)));

      expect(outputs.map((message) => message.type)).toEqual([
        "user_message",
        "run_started",
        "stream_event",
        "assistant_message",
        "result"
      ]);
      expect(outputs.at(-1)).toMatchObject({
        type: "result",
        sessionId: "wire_session",
        status: "finished",
        content: "wire answer: hello wire"
      });
    } finally {
      server.stop(true);
      await rm(root, { recursive: true, force: true });
    }
  });

  test("runs src-origin user wire messages through the AgentSdkClient", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-sdk-src-user-wire-"));
    const server = Bun.serve({
      port: 0,
      async fetch(request) {
        const body = await request.json();
        const user = (body.messages || []).find((message: any) => message.role === "user");
        return modelStreamResponse({ choices: [{ message: { content: `wire answer: ${user?.content || ""}` } }] });
      }
    });
    try {
      const client = await sdkClient(root);
      const outputs = await collectWireMessages(client.runWireMessages([{
        type: "user",
        uuid: "wire_message_2",
        session_id: "wire_session",
        message: { role: "user", content: [{ type: "text", text: "hello src user" }] },
        isReplay: false
      }] as any, modelOptions(server.port)));

      expect(outputs[0]).toMatchObject({
        type: "user_message",
        uuid: "wire_message_2",
        sessionId: "wire_session",
        content: "hello src user",
        isReplay: false
      });
      expect(outputs.at(-1)).toMatchObject({
        type: "result",
        sessionId: "wire_session",
        status: "finished",
        content: "wire answer: hello src user"
      });
    } finally {
      server.stop(true);
      await rm(root, { recursive: true, force: true });
    }
  });

  test("handles default SDK control requests", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-sdk-control-"));
    try {
      await mkdir(path.join(root, ".kevin/commands"), { recursive: true });
      await writeFile(path.join(root, ".kevin/commands/review.md"), "---\ndescription: Review code\nargumentHint: file\naliases: inspect\n---\nReview.");
      const client = await sdkClient(root);
      const outputs = await collectWireMessages(client.runWireMessages([
        {
          type: "control_request",
          requestId: "init_1",
          request: {
            subtype: "initialize",
            agents: {
              reviewer: { description: "Review focused agent", model: "mock-reviewer" }
            }
          }
        },
        {
          type: "control_request",
          requestId: "permission_1",
          request: {
            subtype: "can_use_tool",
            toolName: "filesystem__read",
            toolUseId: "tool_1"
          }
        },
        {
          type: "control_request",
          requestId: "usage_1",
          request: { subtype: "get_context_usage" }
        }
      ], {
        sessionId: "control_session",
        protocol: "openai-chat",
        model: "mock",
        approvalRequiredTools: ["filesystem.read"],
        metadata: { apiKeySource: "user" }
      }));

      const initPayload = controlPayload(outputs[0]);
      expect(initPayload).toMatchObject({
        outputStyle: "default",
        output_style: "default",
        availableOutputStyles: ["default"],
        available_output_styles: ["default"],
        account: { apiKeySource: "user" },
        model: "mock"
      });
      expect(initPayload.commands).toContainEqual(expect.objectContaining({
        name: "review",
        description: "Review code",
        argumentHint: "file",
        aliases: ["inspect"]
      }));
      expect(initPayload.agents).toContainEqual({
        name: "reviewer",
        description: "Review focused agent",
        model: "mock-reviewer"
      });
      expect((initPayload.tools as any[]).some((tool) => tool.name === "filesystem.read")).toBe(true);
      expect((initPayload.models as any[]).some((model) => model.displayName === "openai")).toBe(true);

      expect(outputs[1]).toMatchObject({
        type: "control_response",
        response: {
          subtype: "success",
          requestId: "permission_1",
          response: {
            behavior: "ask",
            allowed: true,
            requiresApproval: true,
            requires_approval: true,
            reason: "tool requires approval",
            metadata: {
              toolName: "filesystem.read",
              requestedToolName: "filesystem__read"
            }
          }
        }
      });
      expect(controlPayload(outputs[2])).toMatchObject({
        totalTokens: 0,
        maxTokens: expect.any(Number),
        rawMaxTokens: expect.any(Number),
        isAutoCompactEnabled: true
      });
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  test("accepts Python-style protocol option aliases", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-sdk-option-aliases-"));
    try {
      const client = await sdkClient(root);
      const structuredIo = new SdkStructuredIo();
      let usedCallerStructuredIo = false;
      const outputs = await collectWireMessages(client.runWireMessages([{
        type: "control_request",
        requestId: "settings_alias_1",
        request: { subtype: "get_settings" }
      }], {
        structured_io: structuredIo,
        controlHandler: async (_request, { structuredIo: handlerStructuredIo }) => {
          usedCallerStructuredIo = handlerStructuredIo === structuredIo;
          return { ok: true };
        }
      }));

      expect(usedCallerStructuredIo).toBe(true);
      expect(outputs[0]).toMatchObject({
        type: "control_response",
        response: {
          subtype: "success",
          requestId: "settings_alias_1",
          response: { ok: true }
        }
      });
      expect(structuredIo.isClosed).toBe(true);
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  test("pumps direct structured IO control requests while waiting for host responses", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-sdk-direct-structured-"));
    try {
      const client = await sdkClient(root);
      let deliverHostResponse: (message: SdkWireMessage) => void = () => undefined;
      const hostResponse = new Promise<SdkWireMessage>((resolve) => {
        deliverHostResponse = resolve;
      });
      async function* messages(): AsyncIterable<SdkWireMessage> {
        yield {
          type: "control_request",
          requestId: "outer_1",
          request: { subtype: "get_settings" }
        };
        yield await hostResponse;
      }

      const iterator = client.runWireMessages(messages(), {
        replayUserMessages: true,
        controlHandler: async (request, { structuredIo }) => {
          expect(request.requestId).toBe("outer_1");
          const hostSettings = await structuredIo.sendRequest({ subtype: "get_settings" }, { requestId: "host_settings_1" });
          return { hostSettings };
        }
      })[Symbol.asyncIterator]();

      const nestedRequest = await iterator.next();
      expect(nestedRequest.value).toMatchObject({
        type: "control_request",
        requestId: "host_settings_1",
        request: { subtype: "get_settings" }
      });

      const hostSettingsResponse = createSdkControlSuccessResponse("host_settings_1", { model: "host-model" });
      deliverHostResponse(hostSettingsResponse);
      const tail = [await iterator.next(), await iterator.next()].map((result) => result.value);
      const outerResponse = tail.find(
        (message) => message?.type === "control_response" && message.response.requestId === "outer_1"
      );
      const replayedResponse = tail.find(
        (message) => message?.type === "control_response" && message.response.requestId === "host_settings_1"
      );

      expect(controlPayload(outerResponse as SdkWireMessage)).toEqual({
        hostSettings: { model: "host-model" }
      });
      expect(replayedResponse).toEqual(hostSettingsResponse);
      expect((await iterator.next()).done).toBe(true);
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  test("applies SDK control settings to later wire user messages", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-sdk-control-settings-"));
    const requests: any[] = [];
    const server = Bun.serve({
      port: 0,
      async fetch(request) {
        const body = await request.json();
        requests.push(body);
        const system = (body.messages || []).find((message: any) => message.role === "system");
        return modelStreamResponse({ choices: [{ message: { content: `model=${body.model}; system=${system?.content || ""}` } }] });
      }
    });
    try {
      const settings = await loadSettings(root);
      const store = new JsonStateStore(path.join(root, "state.json"));
      const client = new AgentSdkClient({ settings, store });
      const outputs = await collectWireMessages(client.runWireMessages([
        {
          type: "control_request",
          requestId: "model_1",
          request: { subtype: "set_model", model: "control-model" }
        },
        {
          type: "control_request",
          requestId: "permission_mode_1",
          request: { subtype: "set_permission_mode", mode: "bypass-permissions" }
        },
        {
          type: "control_request",
          requestId: "flags_1",
          request: {
            subtype: "apply_flag_settings",
            settings: {
              model: "flag-model",
              base_url: `http://127.0.0.1:${server.port}/v1`,
              system_prompt: "flag system prompt",
              permission_mode: "bypass_permissions",
              max_turns: 0,
              max_thinking_tokens: 512,
              cwd: "/workspace/control",
              allowed_tools: ["filesystem.read"],
              skills: ["review"],
              output_format: {
                type: "json_schema",
                schema: { type: "object", properties: { ok: { type: "boolean" } } }
              },
              replay_user_messages: true
            }
          }
        },
        {
          type: "control_request",
          requestId: "settings_1",
          request: { subtype: "get_settings" }
        },
        {
          type: "control_request",
          requestId: "permission_1",
          request: {
            subtype: "can_use_tool",
            toolName: "filesystem.read",
            toolUseId: "tool_1"
          }
        },
        {
          type: "user_message",
          uuid: "message_1",
          sessionId: "settings_session",
          content: "use updated settings"
        }
      ], {
        ...modelOptions(server.port),
        model: "initial-model",
        permissionProfile: "ask",
        approvalRequiredTools: ["filesystem.read"]
      }));

      expect(controlPayload(outputs[0])).toEqual({ model: "control-model" });
      expect(controlPayload(outputs[1])).toEqual({ mode: "bypassPermissions", permissionProfile: "auto" });
      expect(controlPayload(outputs[2])).toMatchObject({
        applied: {
          model: "flag-model",
          baseUrl: `http://127.0.0.1:${server.port}/v1`,
          systemPrompt: "flag system prompt",
          permissionMode: "bypassPermissions",
          permissionProfile: "auto",
          maxToolIterations: 0,
          maxThinkingTokens: 512,
          cwd: "/workspace/control",
          allowedTools: ["filesystem.read"],
          skills: ["review"],
          outputFormat: {
            type: "json_schema",
            schema: { type: "object", properties: { ok: { type: "boolean" } } }
          },
          replayUserMessages: true
        }
      });
      expect(controlPayload(outputs[3])).toMatchObject({
        effective: {
          model: "flag-model",
          cwd: "/workspace/control",
          permissionMode: "bypassPermissions",
          permissionProfile: "auto",
          systemPrompt: "flag system prompt",
          allowedTools: ["filesystem.read"],
          skills: ["review"],
          maxToolIterations: 0,
          maxThinkingTokens: 512,
          replayUserMessages: true
        }
      });
      expect(controlPayload(outputs[4])).toMatchObject({
        behavior: "allow",
        allowed: true,
        requiresApproval: false,
        requires_approval: false
      });
      expect(requests[0].model).toBe("flag-model");
      expect(requests[0].messages[0].content).toContain("flag system prompt");
      expect(outputs.at(-1)).toMatchObject({
        type: "result",
        content: expect.stringContaining("model=flag-model")
      });
      const storedRuns = await store.listRuns();
      expect(JSON.parse(storedRuns[0].metadata.flagSettings || "{}")).toMatchObject({
        model: "flag-model",
        system_prompt: "flag system prompt",
        permission_mode: "bypass_permissions",
        replay_user_messages: true
      });
    } finally {
      server.stop(true);
      await rm(root, { recursive: true, force: true });
    }
  });

  test("normalizes snake_case SDK control messages in direct wire runners", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-sdk-control-snake-"));
    try {
      const client = await sdkClient(root);
      const outputs = await collectWireMessages(client.runWireMessages([
        {
          type: "control_request",
          request_id: "thinking_1",
          request: { subtype: "set_max_thinking_tokens", max_thinking_tokens: 2048 }
        },
        {
          type: "control_request",
          request_id: "permission_1",
          request: { subtype: "can_use_tool", tool_name: "filesystem.read", tool_use_id: "tool_1" }
        },
        {
          type: "control_request",
          request_id: "settings_1",
          request: { subtype: "get_settings" }
        }
      ] as any, {
        session_id: "snake_session",
        permission_profile: "auto",
        enabled_tools: ["filesystem.read"]
      }));

      expect(controlPayload(outputs[0])).toMatchObject({
        maxThinkingTokens: 2048,
        max_thinking_tokens: 2048
      });
      expect(controlPayload(outputs[1])).toMatchObject({
        behavior: "allow",
        requiresApproval: false,
        requires_approval: false,
        metadata: {
          toolName: "filesystem.read",
          requestedToolName: "filesystem.read"
        }
      });
      expect(controlPayload(outputs[2])).toMatchObject({
        effective: {
          sessionId: "snake_session",
          permissionProfile: "auto",
          enabledTools: ["filesystem.read"],
          maxThinkingTokens: 2048
        }
      });
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  test("stops scoped tasks through SDK control requests", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-sdk-task-control-"));
    try {
      const settings = await loadSettings(root);
      const store = new JsonStateStore(path.join(root, "state.json"));
      const client = new AgentSdkClient({ settings, store });
      const scope = {
        tenant_id: "tenant_1",
        user_id: "user_1",
        agent_id: "agent_1",
        workspace_id: "workspace_1"
      };
      const spec = specFromPayload({
        message: "task",
        tenant_id: scope.tenant_id,
        user_id: scope.user_id,
        agent_id: scope.agent_id,
        workspace_id: scope.workspace_id
      });
      const task = await store.createTask(spec, "Review SDK task control", "Review SDK task control");
      const shortTaskId = task.task_id.slice("task_".length, "task_".length + 12);

      const outputs = await collectWireMessages(client.runWireMessages([{
        type: "control_request",
        requestId: "stop_task_1",
        request: { subtype: "stop_task", taskId: shortTaskId }
      }], scope));

      const stoppedPayload = controlPayload(outputs[0]);
      expect(stoppedPayload).toMatchObject({
        stopped: true,
        task: {
          task_id: task.task_id,
          short_id: shortTaskId,
          title: "Review SDK task control",
          input: "Review SDK task control",
          status: "canceled",
          agent_id: scope.agent_id,
          workspace_id: scope.workspace_id,
          metadata: {}
        }
      });
      expect(stoppedPayload.task).not.toHaveProperty("tenant_id");
      expect(stoppedPayload.task).not.toHaveProperty("user_id");
      expect(stoppedPayload.task).not.toHaveProperty("spec");
      expect((await store.loadTask(task.task_id))?.status).toBe("canceled");

      const wrongScopeOutputs = await collectWireMessages(client.runWireMessages([{
        type: "control_request",
        requestId: "stop_task_2",
        request: { subtype: "stop_task", taskId: task.task_id }
      }], {
        ...scope,
        userId: "user_2"
      }));

      expect(wrongScopeOutputs[0]).toMatchObject({
        type: "control_response",
        response: {
          subtype: "error",
          requestId: "stop_task_2",
          error: `task not found: ${task.task_id}`
        }
      });
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  test("reports SDK MCP status from persisted server records", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-sdk-mcp-control-"));
    try {
      const settings = await loadSettings(root);
      const store = new JsonStateStore(path.join(root, "state.json"));
      await store.saveMcpServer({
        name: "docs",
        command: "",
        transport: "sse",
        url: "http://localhost:3555/sse",
        headers: {},
        execution_mode: "trusted_control_plane",
        sandbox_profile: "",
        auth_required: true,
        auth_url: "",
        auth_status: "pending",
        auth_message: "",
        enabled: true,
        tenant_id: "tenant_1",
        user_id: "user_1",
        agent_id: "",
        workspace_id: "",
        created_at: 1,
        updated_at: 1
      });
      const client = new AgentSdkClient({ settings, store });
      const outputs = await collectWireMessages(client.runWireMessages([{
        type: "control_request",
        requestId: "mcp_1",
        request: { subtype: "mcp_status" }
      }], {
        tenantId: "tenant_1",
        userId: "user_1"
      }));

      expect(controlPayload(outputs[0])).toMatchObject({
        mcpServers: [{ name: "docs", status: "needs-auth" }],
        servers: [{
          name: "docs",
          transport: "sse",
          url: "http://localhost:3555/sse",
          enabled: true,
          authRequired: true,
          authStatus: "pending",
          status: "needs-auth"
        }],
        active: [{ name: "docs", status: "needs-auth" }]
      });
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  test("sets and toggles SDK MCP servers in scoped state", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-sdk-mcp-state-"));
    try {
      const settings = await loadSettings(root);
      const store = new JsonStateStore(path.join(root, "state.json"));
      const client = new AgentSdkClient({ settings, store });
      const scope = {
        tenantId: "tenant_1",
        userId: "user_1",
        agentId: "agent_1",
        workspaceId: "workspace_1"
      };
      const outputs = await collectWireMessages(client.runWireMessages([
        {
          type: "control_request",
          requestId: "set_mcp_1",
          request: {
            subtype: "mcp_set_servers",
            servers: {
              docs: {
                transport: "sse",
                url: "http://localhost:3555/sse",
                headers: { "X-Test": "yes" },
                authRequired: true,
                authStatus: "pending"
              },
              local: {
                transport: "stdio",
                command: "bunx",
                args: ["mcp-local"],
                enabled: false
              }
            }
          }
        },
        {
          type: "control_request",
          requestId: "set_mcp_2",
          request: {
            subtype: "mcp_set_servers",
            servers: {
              docs: {
                transport: "sse",
                url: "http://localhost:3555/v2/sse",
                authStatus: "authenticated"
              }
            }
          }
        },
        {
          type: "control_request",
          requestId: "toggle_mcp_1",
          request: { subtype: "mcp_toggle", serverName: "docs", enabled: false }
        },
        {
          type: "control_request",
          requestId: "reconnect_mcp_1",
          request: { subtype: "mcp_reconnect", serverName: "docs" }
        }
      ], scope));

      const firstSetPayload = controlPayload(outputs[0]);
      expect(firstSetPayload).toMatchObject({
        added: ["docs", "local"],
        updated: [],
        removed: [],
        errors: {}
      });
      expect(firstSetPayload.mcp.active).toEqual([{ name: "docs", status: "needs-auth" }]);

      const secondSetPayload = controlPayload(outputs[1]);
      expect(secondSetPayload).toMatchObject({
        added: [],
        updated: ["docs"],
        removed: ["local"],
        errors: {}
      });
      expect(secondSetPayload.mcp.active).toEqual([{ name: "docs", status: "connected" }]);

      expect(controlPayload(outputs[2])).toMatchObject({
        serverName: "docs",
        enabled: false,
        status: "disabled",
        mcp: { active: [] }
      });
      expect(controlPayload(outputs[3])).toEqual({
        serverName: "docs",
        status: "disabled",
        reconnected: false,
        reason: "no active SDK turn is attached to this control handler"
      });

      const records = await store.listMcpServers({
        tenant_id: scope.tenantId,
        user_id: scope.userId,
        agent_id: scope.agentId,
        workspace_id: scope.workspaceId
      });
      expect(records).toHaveLength(1);
      expect(records[0]).toMatchObject({
        name: "docs",
        transport: "sse",
        url: "http://localhost:3555/v2/sse",
        auth_status: "authenticated",
        enabled: false
      });

      const missingToggle = await collectWireMessages(client.runWireMessages([{
        type: "control_request",
        requestId: "toggle_missing_1",
        request: { subtype: "mcp_toggle", serverName: "missing", enabled: false }
      }], scope));
      expect(missingToggle[0]).toMatchObject({
        type: "control_response",
        response: {
          subtype: "error",
          requestId: "toggle_missing_1",
          error: "mcp server not found: missing"
        }
      });
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  test("routes SDK MCP messages and reconnects registered SDK MCP servers", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-sdk-mcp-runtime-"));
    try {
      const settings = await loadSettings(root);
      const store = new JsonStateStore(path.join(root, "state.json"));
      const client = new AgentSdkClient({ settings, store });
      const scope = {
        tenantId: "tenant_1",
        userId: "user_1",
        agentId: "agent_1",
        workspaceId: "workspace_1"
      };
      client.registerSdkMcpServer("local-sdk", async (message) => ({
        ok: true,
        echo: message
      }));

      const outputs = await collectWireMessages(client.runWireMessages([
        {
          type: "control_request",
          requestId: "sdk_mcp_status_1",
          request: { subtype: "mcp_status" }
        },
        {
          type: "control_request",
          requestId: "sdk_mcp_message_1",
          request: {
            subtype: "mcp_message",
            serverName: "local-sdk",
            message: { method: "ping" }
          }
        },
        {
          type: "control_request",
          requestId: "sdk_mcp_reconnect_1",
          request: { subtype: "mcp_reconnect", serverName: "local-sdk" }
        },
        {
          type: "control_request",
          requestId: "sdk_mcp_toggle_1",
          request: { subtype: "mcp_toggle", serverName: "local-sdk", enabled: false }
        },
        {
          type: "control_request",
          requestId: "sdk_mcp_message_2",
          request: {
            subtype: "mcp_message",
            serverName: "local-sdk",
            message: { method: "ping" }
          }
        }
      ], scope));

      expect(controlPayload(outputs[0])).toMatchObject({
        mcpServers: [{ name: "local-sdk", status: "connected" }],
        servers: [{
          name: "local-sdk",
          transport: "sdk",
          enabled: true,
          status: "connected"
        }],
        active: [{ name: "local-sdk", status: "connected" }]
      });
      expect(controlPayload(outputs[1])).toEqual({
        serverName: "local-sdk",
        mcpResponse: { ok: true, echo: { method: "ping" } },
        mcp_response: { ok: true, echo: { method: "ping" } }
      });
      expect(controlPayload(outputs[2])).toEqual({
        serverName: "local-sdk",
        status: "connected",
        reconnected: true
      });
      expect(controlPayload(outputs[3])).toMatchObject({
        serverName: "local-sdk",
        enabled: false,
        status: "disabled",
        mcp: { active: [] }
      });
      expect(outputs[4]).toMatchObject({
        type: "control_response",
        response: {
          subtype: "error",
          requestId: "sdk_mcp_message_2",
          error: "SDK MCP server is disabled: local-sdk"
        }
      });
      expect((await store.listMcpServers({
        tenant_id: scope.tenantId,
        user_id: scope.userId,
        agent_id: scope.agentId,
        workspace_id: scope.workspaceId
      }))[0]).toMatchObject({
        name: "local-sdk",
        transport: "sdk",
        enabled: false
      });
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  test("runs wire messages through an SDK session facade", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-sdk-session-wire-"));
    try {
      const client = await sdkClient(root);
      const session = client.createSession({ sessionId: "session_wire_facade", model: "session-model" });
      expect(session.session_id).toBe("session_wire_facade");
      expect(session.options).toMatchObject({
        sessionId: "session_wire_facade",
        session_id: "session_wire_facade",
        model: "session-model"
      });

      const outputs = await collectWireMessages(session.runWireMessages([{
        type: "control_request",
        requestId: "init_session_1",
        request: { subtype: "initialize" }
      }]));

      expect(outputs[0]).toMatchObject({
        type: "control_response",
        response: {
          subtype: "success",
          requestId: "init_session_1",
          response: {
            model: "session-model",
            outputStyle: "default",
            output_style: "default",
            availableOutputStyles: ["default"],
            available_output_styles: ["default"]
          }
        }
      });
      expect((controlPayload(outputs[0]).tools as any[]).some((tool) => tool.name === "filesystem.read")).toBe(true);

      const controlResponse = await session.handle_control_request({
        type: "control_request",
        requestId: "set_model_alias_1",
        request: { subtype: "set_model", model: "alias-model" }
      });
      expect(controlResponse).toMatchObject({
        type: "control_response",
        response: {
          subtype: "success",
          requestId: "set_model_alias_1",
          response: { model: "alias-model" }
        }
      });
      expect(session.options.model).toBe("alias-model");

      const queued = session.enqueue_async_message("queued alias", { priority: "later" });
      expect(queued).toMatchObject({
        sessionId: "session_wire_facade",
        priority: "later"
      });
      expect(session.list_async_messages().map((message) => message.uuid)).toEqual([queued.uuid]);
      expect(session.dequeue_async_message()?.uuid).toBe(queued.uuid);
      expect(session.dequeue_async_message()).toBeUndefined();
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  test("runs AgentSdkClient over a JSONL transport", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-sdk-jsonl-protocol-"));
    const server = Bun.serve({
      port: 0,
      async fetch(request) {
        const body = await request.json();
        const user = (body.messages || []).find((message: any) => message.role === "user");
        return modelStreamResponse({ choices: [{ message: { content: `jsonl answer: ${user?.content || ""}` } }] });
      }
    });
    try {
      const client = await sdkClient(root);
      const transport = new SdkQueueJsonlTransport();
      const run = client.runJsonlTransport(transport, modelOptions(server.port));

      transport.send(encodeSdkJsonlMessage({
        type: "user",
        uuid: "jsonl_message_1",
        session_id: "jsonl_session",
        message: {
          role: "user",
          content: [{ type: "text", text: "hello " }, { type: "text", text: "jsonl" }]
        },
        parent_tool_use_id: "tool_parent_jsonl",
        tool_use_result: { ok: true },
        is_synthetic: true,
        is_replay: false
      }));
      transport.closeInput();
      await run;

      const outputs = decodeTransportOutput(transport);
      expect(outputs.map((message) => message.type)).toEqual([
        "user_message",
        "run_started",
        "stream_event",
        "assistant_message",
        "result"
      ]);
      expect(outputs[0]).toMatchObject({
        type: "user_message",
        uuid: "jsonl_message_1",
        sessionId: "jsonl_session",
        content: "hello jsonl",
        message: {
          role: "user",
          content: [{ type: "text", text: "hello " }, { type: "text", text: "jsonl" }]
        },
        parentToolUseId: "tool_parent_jsonl",
        toolUseResult: { ok: true },
        isSynthetic: true,
        isReplay: false
      });
      expect(outputs.at(-1)).toMatchObject({
        type: "result",
        sessionId: "jsonl_session",
        status: "finished",
        content: "jsonl answer: hello jsonl"
      });
      expect(transport.isClosed).toBe(true);
    } finally {
      server.stop(true);
      await rm(root, { recursive: true, force: true });
    }
  });

  test("replays JSONL host control responses when SDK replay option is enabled", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-sdk-jsonl-replay-control-"));
    try {
      const client = await sdkClient(root);
      const transport = new SdkQueueJsonlTransport();
      const run = client.runJsonlTransport(transport, {
        replayUserMessages: true,
        controlHandler: async (_request, { structuredIo }) => ({
          hostSettings: await structuredIo.sendRequest({ subtype: "get_settings" }, { requestId: "jsonl_host_settings_1" })
        })
      });

      transport.send(encodeSdkJsonlMessage({
        type: "control_request",
        requestId: "jsonl_outer_1",
        request: { subtype: "get_settings" }
      }));

      expect(await receiveTransportMessage(transport)).toMatchObject({
        type: "control_request",
        requestId: "jsonl_host_settings_1",
        request: { subtype: "get_settings" }
      });

      const hostSettingsResponse = createSdkControlSuccessResponse("jsonl_host_settings_1", { model: "jsonl-host-model" });
      transport.send(encodeSdkJsonlMessage(hostSettingsResponse));
      transport.closeInput();
      await run;

      const outputs = decodeTransportOutput(transport);
      const outerResponse = outputs.find(
        (message) => message.type === "control_response" && message.response.requestId === "jsonl_outer_1"
      );
      const replayedResponse = outputs.find(
        (message) => message.type === "control_response" && message.response.requestId === "jsonl_host_settings_1"
      );

      expect(controlPayload(outerResponse as SdkWireMessage)).toEqual({
        hostSettings: { model: "jsonl-host-model" }
      });
      expect(replayedResponse).toEqual(hostSettingsResponse);
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  test("runs AgentSdkClient over split JSONL chunks", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-sdk-jsonl-chunks-"));
    const server = Bun.serve({
      port: 0,
      async fetch(request) {
        const body = await request.json();
        const user = (body.messages || []).find((message: any) => message.role === "user");
        return modelStreamResponse({ choices: [{ message: { content: `chunk answer: ${user?.content || ""}` } }] });
      }
    });
    try {
      const client = await sdkClient(root);
      const input = [
        encodeSdkJsonlMessage({
          type: "control_request",
          requestId: "settings_chunk_1",
          request: { subtype: "get_settings" }
        }),
        encodeSdkJsonlMessage({
          type: "user_message",
          uuid: "chunk_message_1",
          sessionId: "chunk_session",
          content: "hello chunks"
        })
      ].join("");
      const chunks = [
        input.slice(0, 9),
        new TextEncoder().encode(input.slice(9, 37)),
        input.slice(37)
      ];

      const outputs = decodeJsonlOutput(await collectJsonlLines(client.runJsonlChunks(chunks, modelOptions(server.port))));

      expect(outputs.map((message) => message.type)).toEqual([
        "control_response",
        "user_message",
        "run_started",
        "stream_event",
        "assistant_message",
        "result"
      ]);
      expect(controlPayload(outputs[0])).toMatchObject({
        effective: {
          model: "mock",
          protocol: "openai-chat"
        }
      });
      expect(outputs.at(-1)).toMatchObject({
        type: "result",
        sessionId: "chunk_session",
        status: "finished",
        content: "chunk answer: hello chunks"
      });
    } finally {
      server.stop(true);
      await rm(root, { recursive: true, force: true });
    }
  });

  test("runs session JSONL chunks with session defaults", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-sdk-session-jsonl-chunks-"));
    const server = Bun.serve({
      port: 0,
      async fetch(request) {
        const body = await request.json();
        const user = (body.messages || []).find((message: any) => message.role === "user");
        return modelStreamResponse({ choices: [{ message: { content: `session chunk answer: ${user?.content || ""}` } }] });
      }
    });
    try {
      const client = await sdkClient(root);
      const session = client.createSession({ sessionId: "session_chunk_facade" });
      const input = encodeSdkJsonlMessage({
        type: "user_message",
        uuid: "session_chunk_message_1",
        sessionId: "",
        content: "hello session chunks"
      });

      const outputs = decodeJsonlOutput(await collectJsonlLines(session.runJsonlChunks([input], modelOptions(server.port))));

      expect(outputs.map((message) => message.type)).toEqual([
        "user_message",
        "run_started",
        "stream_event",
        "assistant_message",
        "result"
      ]);
      expect(outputs.at(-1)).toMatchObject({
        type: "result",
        sessionId: "session_chunk_facade",
        status: "finished",
        content: "session chunk answer: hello session chunks"
      });
    } finally {
      server.stop(true);
      await rm(root, { recursive: true, force: true });
    }
  });

  test("interrupts active JSONL user messages through SDK controls", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-sdk-jsonl-interrupt-"));
    const server = slowModelServer();
    try {
      const settings = await loadSettings(root);
      const store = new JsonStateStore(path.join(root, "state.json"));
      const client = new AgentSdkClient({ settings, store });
      const transport = new SdkQueueJsonlTransport();
      const run = client.runJsonlTransport(transport, modelOptions(server.port));

      transport.send(encodeSdkJsonlMessage({
        type: "user_message",
        uuid: "interrupt_message_1",
        sessionId: "interrupt_session",
        content: "start slow work"
      }));

      const echoedUserMessage = await receiveTransportMessage(transport);
      const runStartedMessage = await receiveTransportMessage(transport);
      if (runStartedMessage.type !== "run_started") throw new Error("expected run_started message");

      transport.send(encodeSdkJsonlMessage({
        type: "control_request",
        requestId: "interrupt_1",
        request: { subtype: "interrupt" }
      }));
      transport.closeInput();
      await run;

      const outputs = [echoedUserMessage, runStartedMessage, ...decodeTransportOutput(transport)];
      expect(controlPayload(outputs.find((message) => message.type === "control_response")!)).toMatchObject({
        interrupted: true,
        sessionId: "interrupt_session",
        runId: runStartedMessage.runId
      });
      expect(outputs.find((message) => message.type === "result")).toMatchObject({
        type: "result",
        runId: runStartedMessage.runId,
        sessionId: "interrupt_session",
        status: "canceled",
        content: "run canceled",
        isError: false
      });
      expect((await store.loadRun(runStartedMessage.runId))?.status).toBe("canceled");
    } finally {
      server.stop(true);
      await rm(root, { recursive: true, force: true });
    }
  });

  test("cancels active JSONL user messages by message uuid", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-sdk-jsonl-cancel-message-"));
    const server = slowModelServer();
    try {
      const settings = await loadSettings(root);
      const store = new JsonStateStore(path.join(root, "state.json"));
      const client = new AgentSdkClient({ settings, store });
      const transport = new SdkQueueJsonlTransport();
      const run = client.runJsonlTransport(transport, modelOptions(server.port));

      transport.send(encodeSdkJsonlMessage({
        type: "user_message",
        uuid: "cancel_message_1",
        sessionId: "cancel_session",
        content: "start cancelable work"
      }));

      await receiveTransportMessage(transport);
      const runStartedMessage = await receiveTransportMessage(transport);
      if (runStartedMessage.type !== "run_started") throw new Error("expected run_started message");

      transport.send(encodeSdkJsonlMessage({
        type: "control_request",
        requestId: "cancel_message_1",
        request: { subtype: "cancel_async_message", messageUuid: "cancel_message_1" }
      }));
      transport.closeInput();
      await run;

      const outputs = decodeTransportOutput(transport);
      expect(controlPayload(outputs.find((message) => message.type === "control_response")!)).toMatchObject({
        cancelled: true,
        sessionId: "cancel_session",
        runId: runStartedMessage.runId
      });
      expect(outputs.find((message) => message.type === "result")).toMatchObject({
        type: "result",
        runId: runStartedMessage.runId,
        sessionId: "cancel_session",
        status: "canceled",
        content: "run canceled"
      });
      expect((await store.loadRun(runStartedMessage.runId))?.status).toBe("canceled");
    } finally {
      server.stop(true);
      await rm(root, { recursive: true, force: true });
    }
  });

  test("applies JSONL environment variable updates to later user messages", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-sdk-jsonl-env-update-"));
    const envKey = "KEVIN_SDK_JSONL_ENV_TEST";
    const previousValue = process.env[envKey];
    const server = Bun.serve({
      port: 0,
      async fetch(request) {
        const body = await request.json();
        const user = (body.messages || []).find((message: any) => message.role === "user");
        return modelStreamResponse({ choices: [{ message: { content: `env answer: ${user?.content || ""}` } }] });
      }
    });
    try {
      const settings = await loadSettings(root);
      const store = new JsonStateStore(path.join(root, "state.json"));
      const client = new AgentSdkClient({ settings, store });
      const transport = new SdkQueueJsonlTransport();
      const run = client.runJsonlTransport(transport, {
        ...modelOptions(server.port),
        metadata: { environment_variables: { EXISTING_ENV: "old" } }
      });

      transport.send(encodeSdkJsonlMessage({
        type: "update_environment_variables",
        variables: { [envKey]: "updated" }
      }));
      transport.send(encodeSdkJsonlMessage({
        type: "user_message",
        uuid: "env_message_1",
        sessionId: "env_session",
        content: "use env"
      }));
      transport.closeInput();
      await run;

      const outputs = decodeTransportOutput(transport);
      expect(outputs.at(-1)).toMatchObject({
        type: "result",
        sessionId: "env_session",
        content: "env answer: use env"
      });
      expect(process.env[envKey]).toBe("updated");
      const storedRun = (await store.listRuns())[0];
      expect(JSON.parse(storedRun.metadata.environment_variables || "{}")).toEqual({
        EXISTING_ENV: "old",
        [envKey]: "updated"
      });
    } finally {
      if (previousValue === undefined) {
        delete process.env[envKey];
      } else {
        process.env[envKey] = previousValue;
      }
      server.stop(true);
      await rm(root, { recursive: true, force: true });
    }
  });

  test("can leave caller-owned JSONL transports open", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-sdk-jsonl-owned-"));
    try {
      const client = await sdkClient(root);
      const transport = new SdkQueueJsonlTransport();
      const run = client.runJsonlTransport(transport, { close_transport: false });

      transport.send(encodeSdkJsonlMessage({
        type: "control_request",
        requestId: "settings_1",
        request: { subtype: "get_settings" }
      }));
      transport.closeInput();
      await run;

      expect(decodeTransportOutput(transport)[0]).toMatchObject({
        type: "control_response",
        response: {
          subtype: "success",
          requestId: "settings_1"
        }
      });
      expect(transport.isClosed).toBe(false);
      transport.close();
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  test("runs AgentSdkClient over a hybrid JSONL transport", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-sdk-hybrid-protocol-"));
    const server = Bun.serve({
      port: 0,
      async fetch(request) {
        const body = await request.json();
        const user = (body.messages || []).find((message: any) => message.role === "user");
        return modelStreamResponse({ choices: [{ message: { content: `hybrid answer: ${user?.content || ""}` } }] });
      }
    });
    try {
      const client = await sdkClient(root);
      const reader = new SdkQueueJsonlTransport();
      const posted: Record<string, unknown>[] = [];
      const transport = new SdkHybridJsonlTransport("wss://api.example.com/v2/session_ingress/ws/abc", {
        reader,
        post_message: async (_url, _headers, body) => {
          posted.push(body);
          return 200;
        },
        stream_event_flush_interval_seconds: 0
      });
      const run = client.runJsonlTransport(transport, modelOptions(server.port));

      reader.send(encodeSdkJsonlMessage({
        type: "user",
        session_id: "hybrid_runner_session",
        uuid: "hybrid_runner_user",
        message: { role: "user", content: [{ type: "text", text: "hello hybrid runner" }] },
        isReplay: false
      } as any));
      reader.closeInput();
      await run;

      const resultEvents = posted
        .flatMap((body) => Array.isArray(body.events) ? body.events : [])
        .filter((event): event is Record<string, unknown> => {
          return Boolean(event && typeof event === "object" && (event as Record<string, unknown>).type === "result");
        });
      expect(resultEvents[0]).toMatchObject({
        type: "result",
        sessionId: "hybrid_runner_session",
        content: "hybrid answer: hello hybrid runner"
      });
      expect(transport.closed).toBe(true);
    } finally {
      server.stop(true);
      await rm(root, { recursive: true, force: true });
    }
  });

  test("runs AgentSdkClient over an SSE JSONL transport", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-sdk-sse-protocol-"));
    const server = Bun.serve({
      port: 0,
      async fetch(request) {
        const body = await request.json();
        const user = (body.messages || []).find((message: any) => message.role === "user");
        return modelStreamResponse({ choices: [{ message: { content: `sse answer: ${user?.content || ""}` } }] });
      }
    });
    try {
      const client = await sdkClient(root);
      const posted: Record<string, unknown>[] = [];
      const transport = new SdkSseJsonlTransport("https://api.example.com/session/abc/worker/events/stream", {
        reconnect: false,
        read_chunks: sseChunks([
          `id: 9\nevent: client_event\ndata: ${JSON.stringify({
            payload: {
              type: "user",
              session_id: "sse_runner_session",
              uuid: "sse_runner_user",
              message: { role: "user", content: [{ type: "text", text: "hello sse runner" }] },
              isReplay: false
            }
          })}\n\n`
        ]),
        post_base_delay_seconds: 0,
        post_message: async (_url, _headers, message) => {
          posted.push(message);
          return 200;
        }
      });

      await client.runJsonlTransport(transport, modelOptions(server.port));

      const resultEvents = posted.filter((message) => message.type === "result");
      expect(resultEvents[0]).toMatchObject({
        type: "result",
        sessionId: "sse_runner_session",
        content: "sse answer: hello sse runner"
      });
      expect(transport.closed).toBe(true);
      expect(transport.getLastSequenceNum()).toBe(9);
    } finally {
      server.stop(true);
      await rm(root, { recursive: true, force: true });
    }
  });
});

async function sdkClient(root: string): Promise<AgentSdkClient> {
  const settings = await loadSettings(root);
  return new AgentSdkClient({ settings, store: new JsonStateStore(path.join(root, "state.json")) });
}

function modelOptions(port: number) {
  return {
    protocol: "openai-chat",
    model: "mock",
    baseUrl: `http://127.0.0.1:${port}/v1`,
    apiKey: "test"
  };
}

function slowModelServer() {
  return Bun.serve({
    port: 0,
    async fetch() {
      await new Promise((resolve) => setTimeout(resolve, 5000));
      return modelStreamResponse({ choices: [{ message: { content: "too late" } }] });
    }
  });
}

async function collectWireMessages(messages: AsyncIterable<SdkWireMessage>): Promise<SdkWireMessage[]> {
  const collected: SdkWireMessage[] = [];
  for await (const message of messages) collected.push(message);
  return collected;
}

async function collectJsonlLines(lines: AsyncIterable<string>): Promise<string[]> {
  const collected: string[] = [];
  for await (const line of lines) collected.push(line);
  return collected;
}

async function* sseChunks(chunks: string[]): AsyncIterable<string> {
  for (const chunk of chunks) yield chunk;
}

async function receiveTransportMessage(transport: SdkQueueJsonlTransport): Promise<SdkWireMessage> {
  const line = await transport.receive();
  if (!line) throw new Error("expected SDK JSONL output");
  return decodeSdkJsonlLine(line.trim()) as SdkWireMessage;
}

function decodeJsonlOutput(lines: string[]): SdkWireMessage[] {
  return lines.map((line) => decodeSdkJsonlLine(line.trim())).filter(Boolean) as SdkWireMessage[];
}

function decodeTransportOutput(transport: SdkQueueJsonlTransport): SdkWireMessage[] {
  return transport.drainOutput().map((line) => decodeSdkJsonlLine(line.trim())).filter(Boolean) as SdkWireMessage[];
}

function controlPayload(message: SdkWireMessage): Record<string, any> {
  if (message.type !== "control_response" || message.response.subtype !== "success") {
    throw new Error("expected control success response");
  }
  return message.response.response as Record<string, any>;
}
