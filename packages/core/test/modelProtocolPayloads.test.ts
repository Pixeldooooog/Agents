import { describe, expect, test } from "bun:test";
import type { ModelToolDefinition } from "../src/types/modelTypes.js";
import type { Message } from "../src/types/runtimeTypes.js";
import type { ModelClientConfig } from "../src/models/modelClients.js";
import { completeModelTurn } from "../src/models/modelClients.js";
import {
  claudeMessagesRequestBody,
  parseClaudeMessagesTurn
} from "../src/models/anthropicProtocolPayloads.js";
import {
  openAIChatRequestBody,
  parseOpenAIChatTurn,
  parseResponsesTurn,
  responsesRequestBody
} from "../src/models/openaiProtocolPayloads.js";

describe("model protocol payloads", () => {
  const skillTool: ModelToolDefinition = {
    name: "skill__invoke",
    description: "Invoke a local skill.",
    parameters: {
      type: "object",
      properties: {
        skill: { type: "string" },
        args: { type: "string" }
      },
      required: ["skill"]
    }
  };

  const messages: Message[] = [
    { role: "system", content: "Available skills: release-helper. Call the skill__invoke tool before using it." },
    { role: "user", content: "Draft release notes" },
    {
      role: "assistant",
      content: "",
      tool_calls: [{ id: "call_skill", name: "skill__invoke", arguments: { skill: "release-helper", args: "v2" } }]
    },
    { role: "tool", tool_call_id: "call_skill", name: "skill__invoke", content: "{\"prompt\":\"Use release helper\"}" }
  ];

  test("renders canonical tool names for OpenAI Chat, Responses, and Claude Messages", () => {
    const chat = openAIChatRequestBody(config("openai-chat"), messages, [skillTool]);
    expect((chat.tools as any[])[0]).toEqual({ type: "function", function: skillTool });
    expect((chat.messages as any[])[2].tool_calls[0].function.name).toBe("skill__invoke");
    expect((chat.messages as any[])[3]).toMatchObject({ role: "tool", tool_call_id: "call_skill" });

    const responses = responsesRequestBody(config("openai-responses"), messages, [skillTool]);
    expect((responses.tools as any[])[0]).toMatchObject({ type: "function", name: "skill__invoke" });
    expect((responses.input as any[])[2]).toMatchObject({ type: "function_call", call_id: "call_skill", name: "skill__invoke" });
    expect((responses.input as any[])[3]).toMatchObject({ type: "function_call_output", call_id: "call_skill" });

    const claude = claudeMessagesRequestBody(config("claude-messages"), messages, [skillTool]);
    expect((claude.tools as any[])[0]).toMatchObject({ name: "skill__invoke", input_schema: skillTool.parameters });
    expect(String(claude.system)).toContain("Available skills");
    expect((claude.messages as any[])[1].content[0]).toMatchObject({ type: "tool_use", id: "call_skill", name: "skill__invoke" });
    expect((claude.messages as any[])[2].content[0]).toMatchObject({ type: "tool_result", tool_use_id: "call_skill" });

    const thinkingClaude = claudeMessagesRequestBody({
      ...config("claude-messages"),
      maxTokens: 4096,
      maxThinkingTokens: 2048
    }, messages.slice(0, 2));
    expect(thinkingClaude.thinking).toEqual({
      type: "enabled",
      budget_tokens: 2048
    });
  });

  test("parses native tool calls back into internal ModelTurn values", () => {
    expect(parseOpenAIChatTurn({
      choices: [{
        message: {
          content: "",
          tool_calls: [{ id: "chat_call", function: { name: "skill__invoke", arguments: "{\"skill\":\"release-helper\"}" } }]
        }
      }]
    }).tool_calls).toEqual([{ id: "chat_call", name: "skill__invoke", arguments: { skill: "release-helper" } }]);

    expect(parseResponsesTurn({
      output: [{ type: "function_call", call_id: "responses_call", name: "skill__invoke", arguments: "{\"skill\":\"release-helper\"}" }]
    }).tool_calls).toEqual([{ id: "responses_call", name: "skill__invoke", arguments: { skill: "release-helper" } }]);

    expect(parseClaudeMessagesTurn({
      content: [{ type: "tool_use", id: "claude_call", name: "skill__invoke", input: { skill: "release-helper" } }]
    }).tool_calls).toEqual([{ id: "claude_call", name: "skill__invoke", arguments: { skill: "release-helper" } }]);
  });

  test("parses provider usage into internal model usage", () => {
    expect(parseOpenAIChatTurn({
      choices: [{ message: { content: "chat answer" } }],
      usage: { prompt_tokens: 11, completion_tokens: 7, total_tokens: 18 }
    }).usage).toMatchObject({
      inputTokens: 11,
      outputTokens: 7,
      totalTokens: 18
    });

    expect(parseResponsesTurn({
      output: [{ type: "message", content: [{ type: "output_text", text: "responses answer" }] }],
      usage: { input_tokens: 13, output_tokens: 5, total_tokens: 18 }
    }).usage).toMatchObject({
      inputTokens: 13,
      outputTokens: 5,
      totalTokens: 18
    });

    expect(parseClaudeMessagesTurn({
      content: [{ type: "text", text: "claude answer" }],
      usage: { input_tokens: 17, output_tokens: 6 }
    }).usage).toMatchObject({
      inputTokens: 17,
      outputTokens: 6,
      totalTokens: 23
    });
  });

  test("completeModelTurn sends tools through Responses and Claude protocol clients", async () => {
    const originalFetch = globalThis.fetch;
    const requests: { url: string; body: any }[] = [];
    globalThis.fetch = (async (url: string | URL | Request, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body || "{}"));
      requests.push({ url: String(url), body });
      if (String(url).endsWith("/responses")) {
        return new Response(JSON.stringify({
          output: [{ type: "function_call", call_id: "responses_call", name: "skill__invoke", arguments: "{\"skill\":\"release-helper\"}" }],
          usage: { input_tokens: 4, output_tokens: 2, total_tokens: 6 }
        }), { status: 200 });
      }
      return new Response(JSON.stringify({
        content: [{ type: "tool_use", id: "claude_call", name: "skill__invoke", input: { skill: "release-helper" } }],
        usage: { input_tokens: 5, output_tokens: 3 }
      }), { status: 200 });
    }) as typeof fetch;
    try {
      const responsesTurn = await completeModelTurn(config("openai-responses"), messages.slice(0, 2), [skillTool]);
      expect(requests[0].url).toContain("/responses");
      expect(requests[0].body.tools[0]).toMatchObject({ type: "function", name: "skill__invoke" });
      expect(responsesTurn.tool_calls).toEqual([{ id: "responses_call", name: "skill__invoke", arguments: { skill: "release-helper" } }]);
      expect(responsesTurn.usage).toMatchObject({ inputTokens: 4, outputTokens: 2, totalTokens: 6 });

      const claudeTurn = await completeModelTurn(config("claude-messages"), messages.slice(0, 2), [skillTool]);
      expect(requests[1].url).toContain("/messages");
      expect(requests[1].body.tools[0]).toMatchObject({ name: "skill__invoke", input_schema: skillTool.parameters });
      expect(claudeTurn.tool_calls).toEqual([{ id: "claude_call", name: "skill__invoke", arguments: { skill: "release-helper" } }]);
      expect(claudeTurn.usage).toMatchObject({ inputTokens: 5, outputTokens: 3, totalTokens: 8 });
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});

function config(protocol: string): ModelClientConfig {
  return {
    protocol,
    model: "test-model",
    apiKey: "test-key",
    baseUrl: "http://example.test",
    maxTokens: 1000,
    timeoutMs: 1000
  };
}
