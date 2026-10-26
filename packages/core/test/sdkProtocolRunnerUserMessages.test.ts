import { describe, expect, test } from "bun:test";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import {
  AgentSdkClient,
  type SdkMessage,
  type SdkQueryOptions,
  type SdkUserMessage,
  type SdkWireMessage
} from "@kevin/core/sdk";
import { JsonStateStore, loadSettings } from "../src/index.js";

describe("SDK protocol runner user messages", () => {
  test("acknowledges duplicate replay user frames without running them twice", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-sdk-wire-users-"));
    const requests: unknown[] = [];
    const server = Bun.serve({
      port: 0,
      async fetch(request) {
        const body = await request.json();
        requests.push(body);
        return Response.json({ choices: [{ message: { content: `wire answer: ${userContentFromRequestBody(body)}` } }] });
      }
    });

    try {
      const client = await sdkClient(root);
      const outputs = await collectWireMessages(client.runWireMessages([
        {
          type: "user_message",
          uuid: "duplicate_user_1",
          sessionId: "duplicate_session",
          content: "first",
          isReplay: false
        },
        {
          type: "user_message",
          uuid: "duplicate_user_1",
          sessionId: "duplicate_session",
          content: "duplicate",
          isReplay: false
        }
      ], {
        ...modelOptions(server.port),
        replayUserMessages: true
      }));

      const userAcks = outputs.filter(isUserMessage);
      const results = outputs.filter((message): message is SdkMessage => message.type === "result");
      expect(userAcks.map((message) => message.uuid)).toEqual(["duplicate_user_1", "duplicate_user_1"]);
      expect(userAcks.every((message) => message.isReplay === true)).toBe(true);
      expect(results).toHaveLength(1);
      expect(requests).toHaveLength(1);
      expect(userContentFromRequestBody(requests[0])).toBe("first");

      const replay = await client.getSessionMessages("duplicate_session", { includeSystemMessages: false });
      expect(replay.filter(isUserMessage).map((message) => message.content)).toEqual(["first"]);
    } finally {
      server.stop(true);
      await rm(root, { recursive: true, force: true });
    }
  });

  test("drops duplicate user frames when replay is disabled", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-sdk-wire-users-no-replay-"));
    const requests: unknown[] = [];
    const server = Bun.serve({
      port: 0,
      async fetch(request) {
        const body = await request.json();
        requests.push(body);
        return Response.json({ choices: [{ message: { content: `wire answer: ${userContentFromRequestBody(body)}` } }] });
      }
    });

    try {
      const client = await sdkClient(root);
      const outputs = await collectWireMessages(client.runWireMessages([
        {
          type: "user_message",
          uuid: "duplicate_user_no_replay",
          sessionId: "duplicate_no_replay_session",
          content: "first",
          isReplay: false
        },
        {
          type: "user_message",
          uuid: "duplicate_user_no_replay",
          sessionId: "duplicate_no_replay_session",
          content: "duplicate",
          isReplay: false
        }
      ], modelOptions(server.port)));

      const userAcks = outputs.filter(isUserMessage);
      const results = outputs.filter((message): message is SdkMessage => message.type === "result");
      expect(userAcks.map((message) => message.content)).toEqual(["first"]);
      expect(results).toHaveLength(1);
      expect(requests).toHaveLength(1);
      expect(userContentFromRequestBody(requests[0])).toBe("first");

      const replay = await client.getSessionMessages("duplicate_no_replay_session", { includeSystemMessages: false });
      expect(replay.filter(isUserMessage).map((message) => message.content)).toEqual(["first"]);
    } finally {
      server.stop(true);
      await rm(root, { recursive: true, force: true });
    }
  });
});

async function sdkClient(root: string): Promise<AgentSdkClient> {
  const settings = await loadSettings(root);
  return new AgentSdkClient({
    settings,
    store: new JsonStateStore(path.join(root, "state.json"))
  });
}

function modelOptions(port: number): SdkQueryOptions {
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

function isUserMessage(message: SdkWireMessage | SdkMessage): message is SdkUserMessage {
  return message.type === "user_message";
}

function userContentFromRequestBody(body: unknown): string {
  if (!body || typeof body !== "object") return "";
  const messages = (body as { messages?: unknown }).messages;
  if (!Array.isArray(messages)) return "";
  const userMessage = messages.find((message) => {
    return Boolean(message) && typeof message === "object" && (message as { role?: unknown }).role === "user";
  });
  if (!userMessage || typeof userMessage !== "object") return "";
  const content = (userMessage as { content?: unknown }).content;
  return typeof content === "string" ? content : "";
}
