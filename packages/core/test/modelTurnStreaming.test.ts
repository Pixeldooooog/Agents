import { describe, expect, test } from "bun:test";
import type { ModelStreamEvent, ModelTurn } from "../src/types/modelTypes.js";
import type { ModelClientConfig } from "../src/models/modelClientTypes.js";
import { streamModelTurn } from "../src/models/modelClients.js";
import { chatTurnStream } from "../src/models/chatTurnStream.js";
import { responsesTurnStream } from "../src/models/responsesTurnStream.js";
import { messagesTurnStream } from "../src/models/messagesTurnStream.js";
import { parseResponsesTurn, responsesRequestBody } from "../src/models/openaiProtocolPayloads.js";
import { parseClaudeMessagesTurn, claudeMessagesRequestBody } from "../src/models/anthropicProtocolPayloads.js";
import type { TurnStreamDecoder } from "../src/models/modelTurnStreamState.js";
import { ModelProtocolError } from "../src/models/modelErrors.js";

const config: ModelClientConfig = { protocol: "openai-chat", model: "fixture", baseUrl: "http://fixture", apiKey: "fixture", maxTokens: 256, timeoutMs: 1000 };
const frame = (value: unknown) => ({ event: "message", data: typeof value === "string" ? value : JSON.stringify(value) });
function decode(decoder: TurnStreamDecoder, values: unknown[]): { turn?: ModelTurn; events: ModelStreamEvent[] } {
  const events: ModelStreamEvent[] = [];
  let turn: ModelTurn | undefined;
  for (const value of values) { const step = decoder(frame(value)); events.push(...step.events); turn = step.turn ?? turn; }
  return { turn, events };
}
const chat = (delta: unknown, finish_reason: unknown = null) => ({ choices: [{ index: 0, delta, finish_reason }] });
const toolDelta = (index: number, args: string, id?: string, name?: string) => ({ index, ...(id ? { id, type: "function" } : {}), function: { arguments: args, ...(name ? { name } : {}) } });
const call = { type: "function_call", id: "fc_1", call_id: "call_1", name: "read_file", arguments: '{"path":"a"}', status: "completed" };
const reasoning = { type: "reasoning", id: "rs_1", summary: [], encrypted_content: "opaque-state" };
const responseEvents = () => [
  { type: "response.created", response: { id: "resp_1" } },
  { type: "response.output_item.added", output_index: 0, item: reasoning },
  { type: "response.output_item.done", output_index: 0, item: reasoning },
  { type: "response.output_item.added", output_index: 1, item: { ...call, arguments: "", status: "in_progress" } },
  { type: "response.function_call_arguments.delta", output_index: 1, item_id: "fc_1", delta: '{"path":' },
  { type: "response.function_call_arguments.delta", output_index: 1, item_id: "fc_1", delta: '"a"}' },
  { type: "response.output_item.done", output_index: 1, item: call },
  { type: "response.completed", response: { id: "resp_1", status: "completed", output: [reasoning, call], usage: { input_tokens: 3, output_tokens: 2 } } }
];
const messagesEvents = () => [
  { type: "message_start", message: { content: [], usage: { input_tokens: 3 } } },
  { type: "content_block_start", index: 0, content_block: { type: "thinking", thinking: "" } },
  { type: "content_block_delta", index: 0, delta: { type: "thinking_delta", thinking: "private reasoning" } },
  { type: "content_block_delta", index: 0, delta: { type: "signature_delta", signature: "sig" } },
  { type: "content_block_stop", index: 0 },
  { type: "content_block_start", index: 1, content_block: { type: "tool_use", id: "call_1", name: "read_file", input: {} } },
  { type: "content_block_delta", index: 1, delta: { type: "input_json_delta", partial_json: '{"path":' } },
  { type: "content_block_delta", index: 1, delta: { type: "input_json_delta", partial_json: '"a"}' } },
  { type: "content_block_stop", index: 1 },
  { type: "message_delta", delta: { stop_reason: "tool_use" }, usage: { output_tokens: 2 } },
  { type: "message_stop" }
];

describe("streamed tool turn assembly", () => {
  test("Chat assembles interleaved calls by index and validates before completing", () => {
    const result = decode(chatTurnStream(), [
      chat({ tool_calls: [toolDelta(1, '{"path":', "b", "read_file"), toolDelta(0, '{"path":', "a", "read_file")] }),
      chat({ tool_calls: [toolDelta(0, '"a"}'), toolDelta(1, '"b"}')] }),
      chat({}, "tool_calls"), { choices: [], usage: { prompt_tokens: 3, completion_tokens: 2 } }, "[DONE]"
    ]);
    expect(result.turn?.tool_calls).toEqual([{ id: "a", name: "read_file", arguments: { path: "a" } }, { id: "b", name: "read_file", arguments: { path: "b" } }]);
    expect(result.turn?.usage?.totalTokens).toBe(5);
    expect(result.events.filter(event => event.type === "tool_call_delta")).toHaveLength(4);
  });
  for (const [name, values] of [
    ["identity mutation", [chat({ tool_calls: [toolDelta(0, "", "a", "read_file")] }), chat({ tool_calls: [toolDelta(0, "{}", "b")] })]],
    ["malformed arguments", [chat({ tool_calls: [toolDelta(0, "{", "a", "read_file")] }), chat({}, "tool_calls"), "[DONE]"]],
    ["duplicate IDs", [chat({ tool_calls: [toolDelta(0, "{}", "a", "read_file"), toolDelta(1, "{}", "a", "read_file")] }), chat({}, "tool_calls"), "[DONE]"]],
    ["missing indexes", [chat({ tool_calls: [toolDelta(1, "{}", "a", "read_file")] }), chat({}, "tool_calls"), "[DONE]"]],
    ["inconsistent stop reason", [chat({ tool_calls: [toolDelta(0, "{}", "a", "read_file")] }), chat({}, "stop"), "[DONE]"]]
  ] as const) {
    test(`Chat rejects ${name}`, () => expect(() => decode(chatTurnStream(), [...values])).toThrow(ModelProtocolError));
  }
  test("Responses uses call_id and preserves ordered opaque reasoning", () => {
    const { turn } = decode(responsesTurnStream(config), responseEvents());
    expect(turn?.tool_calls[0]).toEqual({ id: "call_1", name: "read_file", arguments: { path: "a" } });
    expect(turn?.model_context?.items).toEqual([reasoning, call]);
    expect(turn?.usage?.totalTokens).toBe(5);
  });
  test("Responses rejects unmatched deltas and final argument replacement", () => {
    const values = responseEvents();
    expect(() => decode(responsesTurnStream(config), [values[1], { type: "response.output_item.added", output_index: 1, item: reasoning }])).toThrow(ModelProtocolError);
    expect(() => decode(responsesTurnStream(config), [values[4]])).toThrow(ModelProtocolError);
    expect(() => decode(responsesTurnStream(config), [...values.slice(0, 6), { type: "response.output_item.done", output_index: 1, item: { ...call, arguments: "{}" } }])).toThrow(ModelProtocolError);
    expect(() => decode(responsesTurnStream(config), [...values.slice(0, 7), { type: "response.completed", response: { status: "completed", output: [reasoning, { ...call, name: "other" }] } }])).toThrow(ModelProtocolError);
  });
  test("Messages combines usage and preserves signed thinking without exposing it as text", () => {
    const { turn, events } = decode(messagesTurnStream(config), messagesEvents());
    expect(turn?.tool_calls[0].arguments).toEqual({ path: "a" });
    expect(turn?.usage?.totalTokens).toBe(5);
    expect(turn?.model_context?.items[0]).toEqual({ type: "thinking", thinking: "private reasoning", signature: "sig" });
    expect(events.some(event => event.type === "text_delta")).toBe(false);
  });
  test("Messages rejects unsigned thinking, malformed tool JSON and truncated stops", () => {
    const values = messagesEvents();
    expect(() => decode(messagesTurnStream(config), values.filter((_, index) => index !== 3))).toThrow(ModelProtocolError);
    expect(() => decode(messagesTurnStream(config), values.filter((_, index) => index !== 7))).toThrow(ModelProtocolError);
    expect(() => decode(messagesTurnStream(config), [...values.slice(0, 9), values[10]])).toThrow(ModelProtocolError);
  });
});

describe("native context replay", () => {
  test("Responses round-trips through serialized history without duplicating calls", () => {
    const turn = parseResponsesTurn({ output: [reasoning, call] }, config);
    const history = [{ role: "assistant" as const, ...turn }, { role: "tool" as const, content: "result", tool_call_id: "call_1" }];
    const body = responsesRequestBody(config, structuredClone(history));
    expect(body.input).toEqual([reasoning, call, { type: "function_call_output", call_id: "call_1", output: "result" }]);
    expect(body).toMatchObject({ store: false, include: ["reasoning.encrypted_content"] });
    expect(responsesRequestBody({ ...config, baseUrl: "http://other" }, history).input).not.toContainEqual(reasoning);
    expect(responsesRequestBody({ ...config, model: "other" }, history).input).not.toContainEqual(reasoning);
    expect(JSON.stringify(claudeMessagesRequestBody(config, history))).not.toContain("opaque-state");
  });
  test("Messages replays signatures and redacted blocks before tool results", () => {
    const content = [{ type: "thinking", thinking: "private", signature: "signed" }, { type: "redacted_thinking", data: "encrypted" }, { type: "tool_use", id: "a", name: "read_file", input: {} }];
    const turn = parseClaudeMessagesTurn({ content }, config);
    const history = [{ role: "assistant" as const, ...turn }, { role: "tool" as const, content: "result", tool_call_id: "a" }];
    expect(claudeMessagesRequestBody(config, history).messages).toEqual([{ role: "assistant", content }, { role: "user", content: [{ type: "tool_result", tool_use_id: "a", content: "result" }] }]);
    expect(JSON.stringify(claudeMessagesRequestBody({ ...config, model: "other" }, history))).not.toContain("signed");
    expect(JSON.stringify(responsesRequestBody(config, history))).not.toContain("signed");
  });
});

for (const [protocol, values] of [
  ["openai-chat", [chat({ tool_calls: [toolDelta(0, '{"path":"a"}', "call_1", "read_file")] }), chat({}, "tool_calls"), "[DONE]"]],
  ["openai-responses", responseEvents()],
  ["claude-messages", messagesEvents()]
] as const) {
  test(`${protocol} streams through HTTP with awaited callbacks and a validated completion`, async () => {
    const server = Bun.serve({ port: 0, hostname: "127.0.0.1", async fetch(request) {
      expect(await request.json()).toMatchObject({ stream: true });
      return new Response(values.map(value => `data: ${frame(value).data}\n\n`).join(""), { headers: { "Content-Type": "text/event-stream" } });
    } });
    try {
      const events: ModelStreamEvent[] = [];
      const local = { ...config, protocol, baseUrl: `http://127.0.0.1:${server.port}` };
      const turn = await streamModelTurn(local, [], [{ name: "read_file", description: "read", parameters: { type: "object" } }], async event => { await Promise.resolve(); events.push(event); });
      expect(turn.tool_calls).toEqual([{ id: "call_1", name: "read_file", arguments: { path: "a" } }]);
      expect(events.at(-1)).toEqual({ type: "completed", turn });
      await expect(streamModelTurn(local, [], [], () => { throw new Error("consumer failed"); })).rejects.toThrow("consumer failed");
      const abort = new AbortController();
      await expect(streamModelTurn({ ...local, signal: abort.signal }, [], [], () => abort.abort())).rejects.toMatchObject({ name: "AbortError" });
    } finally { await server.stop(true); }
  });
}
