import { describe, expect, test } from "bun:test";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { AgentSdkClient, type SdkWireMessage } from "@kevin/core/sdk";
import { JsonStateStore, loadSettings } from "../src/index.js";

describe("SDK context usage", () => {
  test("reports estimated usage from persisted SDK session runs", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-sdk-context-usage-"));
    const server = Bun.serve({
      port: 0,
      async fetch(request) {
        const body = await request.json();
        const user = (body.messages || []).find((message: any) => message.role === "user");
        return Response.json({
          choices: [{ message: { content: `answer for ${user?.content || ""}` } }],
          usage: { prompt_tokens: 20, completion_tokens: 10, total_tokens: 30 }
        });
      }
    });
    try {
      const client = await sdkClient(root);
      const session = client.createSession({
        sessionId: "usage_session",
        ...modelOptions(server.port),
        systemPrompt: "usage system prompt"
      });

      const runOutputs = await collectWireMessages(session.runWireMessages([{
        type: "user_message",
        uuid: "usage_message_1",
        sessionId: "usage_session",
        content: "measure this session"
      }]));
      expect(runOutputs.at(-1)).toMatchObject({
        type: "result",
        modelUsage: {
          inputTokens: 20,
          outputTokens: 10,
          totalTokens: 30
        }
      });

      const usageOutputs = await collectWireMessages(session.runWireMessages([{
        type: "control_request",
        requestId: "usage_1",
        request: { subtype: "get_context_usage" }
      }]));
      const usage = controlPayload(usageOutputs[0]);

      expect(usage).toMatchObject({
        estimated: true,
        source: "sdk_session_events",
        sessionId: "usage_session",
        runCount: 1,
        model: "mock",
        maxTokens: expect.any(Number),
        rawMaxTokens: expect.any(Number),
        apiUsage: {
          inputTokens: 20,
          outputTokens: 10,
          totalTokens: 30
        }
      });
      expect(usage.totalTokens).toBeGreaterThan(0);
      expect(usage.percentage).toBeGreaterThan(0);
      expect((usage.categories as any[]).map((category) => category.name)).toEqual(["system", "user", "assistant"]);
      expect((usage.gridRows as any[]).map((row) => row.type)).toEqual(["system", "user", "assistant"]);
    } finally {
      server.stop(true);
      await rm(root, { recursive: true, force: true });
    }
  });

  test("keeps empty usage explicit when no SDK session is selected", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-sdk-empty-context-usage-"));
    try {
      const client = await sdkClient(root);
      await expect(client.getContextUsage({ model: "mock" })).resolves.toMatchObject({
        estimated: true,
        source: "sdk_session_events",
        sessionId: "",
        runCount: 0,
        totalTokens: 0,
        model: "mock",
        categories: []
      });
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  test("includes tool calls and tool results in estimated usage", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-sdk-tool-context-usage-"));
    const server = Bun.serve({
      port: 0,
      async fetch(request) {
        const body = await request.json();
        if ((body.messages || []).some((message: any) => message.role === "tool")) {
          return Response.json({
            choices: [{ message: { content: "tool answer" } }],
            usage: { prompt_tokens: 9, completion_tokens: 3, total_tokens: 12 }
          });
        }
        return Response.json({
          choices: [{
            message: {
              content: "",
              tool_calls: [{
                id: "call_usage_read",
                type: "function",
                function: {
                  name: "filesystem__read",
                  arguments: JSON.stringify({ path: "usage.txt" })
                }
              }]
            }
          }],
          usage: { prompt_tokens: 6, completion_tokens: 2, total_tokens: 8 }
        });
      }
    });
    try {
      await writeFile(path.join(root, "usage.txt"), "usage file content");
      const client = await sdkClient(root);
      const session = client.createSession({
        sessionId: "tool_usage_session",
        ...modelOptions(server.port),
        permissionProfile: "auto",
        enabledTools: ["filesystem.read"]
      });

      await collectWireMessages(session.runWireMessages([{
        type: "user_message",
        uuid: "tool_usage_message_1",
        sessionId: "tool_usage_session",
        content: "read for usage"
      }]));
      const usage = await session.contextUsage();

      expect((usage.categories as any[]).map((category) => category.name)).toEqual([
        "user",
        "assistant",
        "tool_calls",
        "tool_results"
      ]);
      expect(usage).toMatchObject({
        model: "mock",
        toolCallCount: 1,
        toolResultCount: 1,
        apiUsage: {
          inputTokens: 15,
          outputTokens: 5,
          totalTokens: 20
        }
      });
      expect(usage.totalTokens).toBeGreaterThan(0);
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

async function collectWireMessages(messages: AsyncIterable<SdkWireMessage>): Promise<SdkWireMessage[]> {
  const collected: SdkWireMessage[] = [];
  for await (const message of messages) collected.push(message);
  return collected;
}

function controlPayload(message: SdkWireMessage): Record<string, any> {
  if (message.type !== "control_response" || message.response.subtype !== "success") {
    throw new Error("expected control success response");
  }
  return message.response.response as Record<string, any>;
}
