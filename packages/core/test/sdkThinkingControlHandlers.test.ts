import { describe, expect, test } from "bun:test";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { AgentSdkClient, type SdkWireMessage } from "@kevin/core/sdk";
import { JsonStateStore, loadSettings } from "../src/index.js";

describe("SDK thinking control handlers", () => {
  test("applies thinking token controls to later Claude messages", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-sdk-thinking-control-"));
    const requests: any[] = [];
    const server = Bun.serve({
      port: 0,
      async fetch(request) {
        const body = await request.json();
        requests.push(body);
        return Response.json({ content: [{ type: "text", text: "claude answer" }] });
      }
    });
    try {
      const settings = await loadSettings(root);
      const client = new AgentSdkClient({
        settings,
        store: new JsonStateStore(path.join(root, "state.json"))
      });
      const outputs = await collectWireMessages(client.runWireMessages([
        {
          type: "control_request",
          requestId: "thinking_1",
          request: { subtype: "set_max_thinking_tokens", maxThinkingTokens: 2048 }
        },
        {
          type: "control_request",
          requestId: "settings_1",
          request: { subtype: "get_settings" }
        },
        {
          type: "user_message",
          uuid: "thinking_message_1",
          sessionId: "thinking_session",
          content: "use thinking budget"
        }
      ], {
        protocol: "claude-messages",
        model: "mock-claude",
        baseUrl: `http://127.0.0.1:${server.port}`,
        apiKey: "test"
      }));

      expect(controlPayload(outputs[0])).toMatchObject({
        maxThinkingTokens: 2048,
        max_thinking_tokens: 2048
      });
      expect(controlPayload(outputs[1])).toMatchObject({
        effective: { maxThinkingTokens: 2048 }
      });
      expect(requests[0].thinking).toEqual({
        type: "enabled",
        budget_tokens: 2048
      });
      expect(outputs.at(-1)).toMatchObject({
        type: "result",
        status: "finished",
        content: "claude answer"
      });
    } finally {
      server.stop(true);
      await rm(root, { recursive: true, force: true });
    }
  });
});

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
