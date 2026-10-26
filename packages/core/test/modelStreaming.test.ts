import { describe, expect, test } from "bun:test";
import { readSseEvents } from "../src/models/modelSse.js";
import { streamText } from "../src/models/modelClients.js";
import { ModelProtocolError } from "../src/models/modelErrors.js";
import type { ModelClientConfig } from "../src/models/modelClientTypes.js";

const encoder = new TextEncoder();
const config: ModelClientConfig = {
  protocol: "openai-chat", model: "fixture", baseUrl: "", apiKey: "fixture",
  maxTokens: 256, timeoutMs: 1000
};
function bytes(chunks: Uint8Array[], cancelled?: () => void): ReadableStream<Uint8Array> {
  let index = 0;
  return new ReadableStream({
    pull(controller) {
      if (index < chunks.length) controller.enqueue(chunks[index++]);
      else controller.close();
    },
    cancel: cancelled
  });
}
async function frames(body: ReadableStream<Uint8Array>) {
  const events = [];
  for await (const event of readSseEvents(body)) events.push(event);
  return events;
}
const event = (data: unknown) => `data:${JSON.stringify(data)}\r\n\r\n`;
const chatDelta = (content: unknown, finish: unknown = null) => event({ choices: [{ index: 0, delta: { content }, finish_reason: finish }] });
const chatFinish = chatDelta(null, "stop");
const done = "data:[DONE]\r\n\r\n";
const messageStart = event({ type: "message_start", message: { role: "assistant", content: [], usage: { input_tokens: 1 } } });
const blockStart = event({ type: "content_block_start", index: 0, content_block: { type: "text", text: "" } });
const blockStop = event({ type: "content_block_stop", index: 0 });
const messageFinish = event({ type: "message_delta", delta: { stop_reason: "end_turn" }, usage: { output_tokens: 1 } });
const messageStop = event({ type: "message_stop" });

async function withServer(body: string, run: (local: ModelClientConfig) => Promise<void>, contentType = "text/event-stream") {
  const server = Bun.serve({ port: 0, hostname: "127.0.0.1", fetch: () => new Response(body, { headers: { "Content-Type": contentType } }) });
  try { await run({ ...config, baseUrl: `http://127.0.0.1:${server.port}` }); }
  finally { await server.stop(true); }
}

describe("SSE framing", () => {
  test("handles byte-fragmented UTF-8, CRLF, CR, LF, comments and multiline data", async () => {
    const input = encoder.encode('\uFEFF:keepalive\r\nevent: delta\r\ndata:{\r\ndata: "text":"你好"}\r\n\r\ndata:next\r\rdata:last\n\n');
    expect(await frames(bytes(Array.from(input, byte => new Uint8Array([byte]))))).toEqual([
      { event: "delta", data: '{\n"text":"你好"}' }, { event: "message", data: "next" }, { event: "message", data: "last" }
    ]);
  });
  test("requires a blank line to dispatch final data", async () => {
    for (const input of ["data:unfinished", "data:unfinished\n"]) {
      await expect(frames(bytes([encoder.encode(input)]))).rejects.toBeInstanceOf(ModelProtocolError);
    }
  });
  test("rejects invalid and truncated UTF-8", async () => {
    for (const input of [new Uint8Array([255]), new Uint8Array([0xe4, 0xbd])]) {
      await expect(frames(bytes([input]))).rejects.toThrow("invalid UTF-8");
    }
  });
  test("bounds unfinished lines and accumulated multiline events", async () => {
    for (const input of ['data:' + 'x'.repeat(1024 * 1024), 'data:\n'.repeat(180000)]) {
      await expect(frames(bytes([encoder.encode(input)]))).rejects.toThrow("size limit");
    }
  });
  test("early consumer return cancels and unlocks the source", async () => {
    let cancelled = false;
    const body = new ReadableStream<Uint8Array>({
      start(controller) { controller.enqueue(encoder.encode('data:first\n\ndata:second\n\n')); },
      cancel() { cancelled = true; }
    });
    for await (const frame of readSseEvents(body)) { expect(frame.data).toBe("first"); break; }
    expect(cancelled).toBe(true);
    expect(body.locked).toBe(false);
  });
});

describe("text stream protocol completion", () => {
  test("Chat emits text and accepts finish plus DONE, including usage-only chunks", async () => {
    await withServer(chatDelta("你好") + chatFinish + event({ choices: [], usage: { total_tokens: 3 } }) + done, async local => {
      const deltas: string[] = [];
      expect(await streamText(local, [], delta => deltas.push(delta))).toBe("你好");
      expect(deltas).toEqual(["你好"]);
    });
  });
  for (const [name, body] of [
    ["EOF before finish", chatDelta("partial")],
    ["missing DONE", chatDelta("partial") + chatFinish],
    ["DONE without finish", chatDelta("partial") + done],
    ["token limit", chatDelta("partial", "length") + done],
    ["content filter", chatDelta(null, "content_filter") + done],
    ["non-string delta", chatDelta({ text: "invalid" }) + chatFinish + done],
    ["post-finish text", chatFinish + chatDelta("late") + done],
    ["provider error", event({ error: { message: "failed" } })],
    ["unexpected tools", event({ choices: [{ index: 0, delta: { tool_calls: [] } }] })],
    ["malformed JSON", "data:{broken}\n\n"]
  ]) {
    test(`Chat rejects ${name}`, async () => {
      await withServer(body, async local => {
        await expect(streamText(local, [], () => {})).rejects.toBeInstanceOf(ModelProtocolError);
      });
    });
  }
  test("Responses requires completed status and emits typed text deltas", async () => {
    const item = { type: "message", id: "msg_1", role: "assistant", content: [{ type: "output_text", text: "hello" }] };
    await withServer(event({ type: "response.output_item.added", output_index: 0, item: { ...item, content: [] } }) + event({ type: "response.output_text.delta", output_index: 0, item_id: "msg_1", content_index: 0, delta: "hello" }) + event({ type: "response.output_item.done", output_index: 0, item }) + event({ type: "response.completed", response: { status: "completed", output: [item] } }), async local => {
      expect(await streamText({ ...local, protocol: "responses" }, [], () => {})).toBe("hello");
    });
    for (const body of [event({ type: "response.output_text.delta", delta: "partial" }), event({ type: "response.incomplete" }), event({ type: "response.completed", response: { status: "in_progress", output: [] } })]) {
      await withServer(body, async local => {
        await expect(streamText({ ...local, protocol: "responses" }, [], () => {})).rejects.toBeInstanceOf(ModelProtocolError);
      });
    }
  });
  test("Messages uses native stream requests and ordered text blocks", async () => {
    const body = messageStart + blockStart + event({ type: "content_block_delta", index: 0, delta: { type: "text_delta", text: "hello" } }) + blockStop + messageFinish + messageStop;
    const server = Bun.serve({ port: 0, hostname: "127.0.0.1", async fetch(request) {
      expect(new URL(request.url).pathname).toBe("/messages");
      expect(request.headers.get("x-api-key")).toBe("fixture");
      expect(await request.json()).toMatchObject({ stream: true });
      return new Response(body, { headers: { "Content-Type": "text/event-stream" } });
    } });
    try {
      const deltas: string[] = [];
      expect(await streamText({ ...config, protocol: "anthropic", baseUrl: `http://127.0.0.1:${server.port}` }, [], delta => deltas.push(delta))).toBe("hello");
      expect(deltas).toEqual(["hello"]);
    } finally { await server.stop(true); }
  });
  test("Messages rejects truncation, missing stop reasons and unmatched block deltas", async () => {
    for (const body of [messageStart + blockStart, messageStart + messageStop, messageStart + event({ type: "content_block_delta", index: 7, delta: { type: "text_delta", text: "bad" } }), messageStart + event({ type: "message_delta", delta: { stop_reason: "max_tokens" } }) + messageStop]) {
      await withServer(body, async local => {
        await expect(streamText({ ...local, protocol: "anthropic" }, [], () => {})).rejects.toBeInstanceOf(ModelProtocolError);
      });
    }
  });
  test("rejects successful HTTP responses with the wrong media type", async () => {
    await withServer('{}', async local => {
      await expect(streamText(local, [], () => {})).rejects.toThrow("text/event-stream");
    }, "application/json");
  });
  test("preserves consumer cancellation during delivery", async () => {
    await withServer(chatDelta("hello") + chatFinish + done, async local => {
      const controller = new AbortController();
      await expect(streamText({ ...local, signal: controller.signal }, [], () => controller.abort()))
        .rejects.toMatchObject({ name: "AbortError" });
    });
  });
  test("times out while waiting for a stalled response body", async () => {
    const server = Bun.serve({ port: 0, hostname: "127.0.0.1", fetch: () => new Response(new ReadableStream({ start(controller) { controller.enqueue(encoder.encode(": keepalive\n\n")); } }), { headers: { "Content-Type": "text/event-stream" } }) });
    try {
      await expect(streamText({ ...config, timeoutMs: 100, baseUrl: `http://127.0.0.1:${server.port}` }, [], () => {})).rejects.toMatchObject({ name: "TimeoutError" });
    } finally { await server.stop(true); }
  });
});
