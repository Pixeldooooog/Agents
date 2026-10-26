import { describe, expect, test } from "bun:test";
import { completeModelTurn, streamText } from "../src/models/modelClients.js";
import type { ModelClientConfig } from "../src/models/modelClientTypes.js";
import { ModelConfigError, ModelHttpError, ModelProtocolError } from "../src/models/modelErrors.js";
import { normalizeProtocol } from "../src/models/modelProfiles.js";
import { postJson, streamSse } from "../src/models/modelHttp.js";
import { parseClaudeMessagesTurn } from "../src/models/anthropicProtocolPayloads.js";
import { parseOpenAIChatTurn, parseResponsesTurn, responsesRequestBody } from "../src/models/openaiProtocolPayloads.js";

const config: ModelClientConfig = {
  protocol: "openai-chat", model: "fixture", baseUrl: "http://127.0.0.1:1", apiKey: "fixture",
  maxTokens: 256, timeoutMs: 1000
};
const tools = [{ name: "read_file", description: "Read a file", parameters: { type: "object" } }];
const chat = (argumentsValue: unknown, id: unknown = "call_1") => ({
  choices: [{ message: { content: null, tool_calls: [{ id, type: "function", function: { name: "read_file", arguments: argumentsValue } }] } }]
});
const responses = (argumentsValue: unknown, id: unknown = "call_1") => ({
  output: [{ type: "function_call", call_id: id, name: "read_file", arguments: argumentsValue }]
});

describe("model boundary validation", () => {
  test("normalizes supported aliases and rejects unknown protocols before network I/O", async () => {
    expect(normalizeProtocol(" ANTHROPIC ")).toBe("claude-messages");
    expect(normalizeProtocol("responses")).toBe("openai-responses");
    expect(() => normalizeProtocol("typo-protocol")).toThrow(ModelConfigError);
    await expect(completeModelTurn({ ...config, protocol: "typo-protocol" }, [])).rejects.toBeInstanceOf(ModelConfigError);
    await expect(streamText({ ...config, protocol: "typo-protocol" }, [], () => {})).rejects.toBeInstanceOf(ModelConfigError);
  });

  test("does not silently drop Gemini tools or prior tool messages", async () => {
    const gemini = { ...config, protocol: "gemini" };
    await expect(completeModelTurn(gemini, [], tools)).rejects.toBeInstanceOf(ModelConfigError);
    await expect(completeModelTurn(gemini, [{ role: "tool", tool_call_id: "a", content: "data" }])).rejects.toBeInstanceOf(ModelConfigError);
  });

  for (const [name, parse, payload] of [
    ["Chat", parseOpenAIChatTurn, chat],
    ["Responses", parseResponsesTurn, responses]
  ] as const) {
    test(`${name} rejects malformed/non-object function arguments instead of executing an empty object`, () => {
      for (const value of ["{", "null", "[]", "1", '"text"', "", undefined, {}]) {
        expect(() => parse(payload(value))).toThrow(ModelProtocolError);
      }
      expect(parse(payload("{}" )).tool_calls[0].arguments).toEqual({});
      expect(parse(payload('{"path":"hello.txt"}')).tool_calls[0].arguments).toEqual({ path: "hello.txt" });
    });
    test(`${name} requires provider correlation IDs`, () => {
      for (const id of [null, "", 1]) expect(() => parse(payload("{}", id))).toThrow(ModelProtocolError);
    });
  }

  test("Responses output item id is not a substitute for call_id", () => {
    expect(() => parseResponsesTurn({ output: [{ type: "function_call", id: "fc_item", name: "read_file", arguments: "{}" }] })).toThrow(ModelProtocolError);
    const turn = parseResponsesTurn({ output: [{ type: "function_call", id: "fc_item", call_id: "call_link", name: "read_file", arguments: "{}" }] });
    const body = responsesRequestBody(config, [
      { role: "assistant", content: "", tool_calls: turn.tool_calls },
      { role: "tool", tool_call_id: turn.tool_calls[0].id, content: "file content" }
    ]);
    expect(body.input).toEqual([
      { type: "function_call", call_id: "call_link", name: "read_file", arguments: "{}" },
      { type: "function_call_output", call_id: "call_link", output: "file content" }
    ]);
  });

  test("Messages input must be an object and tool IDs must be unique", () => {
    for (const input of [undefined, null, [], "{}", 42]) {
      expect(() => parseClaudeMessagesTurn({ content: [{ type: "tool_use", id: "a", name: "read_file", input }] })).toThrow(ModelProtocolError);
    }
    const call = { type: "tool_use", id: "a", name: "read_file", input: {} };
    expect(() => parseClaudeMessagesTurn({ content: [call, call] })).toThrow(ModelProtocolError);
    const responseCall = responses("{}").output[0];
    expect(() => parseResponsesTurn({ output: [responseCall, responseCall] })).toThrow(ModelProtocolError);
    const chatCall = chat("{}").choices[0].message.tool_calls[0];
    expect(() => parseOpenAIChatTurn({ choices: [{ message: { content: null, tool_calls: [chatCall, chatCall] } }] })).toThrow(ModelProtocolError);
  });

  test("missing response envelopes and incomplete turns are not successful empty answers", () => {
    expect(() => parseOpenAIChatTurn({})).toThrow(ModelProtocolError);
    expect(() => parseOpenAIChatTurn({ choices: [] })).toThrow(ModelProtocolError);
    expect(() => parseOpenAIChatTurn({ choices: [{ message: {} }] })).toThrow(ModelProtocolError);
    expect(() => parseResponsesTurn({})).toThrow(ModelProtocolError);
    expect(() => parseClaudeMessagesTurn({})).toThrow(ModelProtocolError);
    expect(() => parseOpenAIChatTurn({ choices: [{ finish_reason: "length", message: { content: "partial" } }] })).toThrow(ModelProtocolError);
    expect(() => parseResponsesTurn({ status: "incomplete", output: [] })).toThrow(ModelProtocolError);
    expect(() => parseClaudeMessagesTurn({ stop_reason: "max_tokens", content: [] })).toThrow(ModelProtocolError);
  });

  test("text streaming propagates consumer failures without swallowing them", async () => {
    const server = Bun.serve({ port: 0, hostname: "127.0.0.1", fetch() {
      return new Response('data: {"text":"hello"}\n\n', { headers: { "Content-Type": "text/event-stream" } });
    } });
    try {
      const local = { ...config, baseUrl: `http://127.0.0.1:${server.port}` };
      await expect(streamSse(local, "/stream", {}, () => "hello", () => { throw new Error("consumer failed"); }))
        .rejects.toThrow("consumer failed");
    } finally { await server.stop(true); }
  });

  test("HTTP errors retain status, successful malformed JSON fails, and abort is preserved", async () => {
    const server = Bun.serve({ port: 0, hostname: "127.0.0.1", fetch(request) {
      const path = new URL(request.url).pathname;
      if (path === "/limited") return new Response('{"error":{"message":"rate limited"}}', { status: 429 });
      if (path === "/gateway") return new Response("<html>provider unavailable</html>", { status: 502 });
      if (path === "/broken") return new Response("{broken");
      return Response.json({ ok: true });
    } });
    const local = { ...config, baseUrl: `http://127.0.0.1:${server.port}` };
    try {
      await expect(postJson(local, "/limited", {})).rejects.toMatchObject({ name: "ModelHttpError", status: 429, message: "rate limited" });
      await expect(postJson(local, "/gateway", {})).rejects.toBeInstanceOf(ModelHttpError);
      await expect(postJson(local, "/broken", {})).rejects.toBeInstanceOf(ModelProtocolError);
      expect(await postJson(local, "/ok", {})).toEqual({ ok: true });
      const controller = new AbortController();
      controller.abort();
      await expect(postJson({ ...local, signal: controller.signal }, "/ok", {})).rejects.toMatchObject({ name: "AbortError" });
    } finally { await server.stop(true); }
  });
});
