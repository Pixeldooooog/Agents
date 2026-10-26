import { describe, expect, test } from "bun:test";
import {
  decodeSdkJsonlLine,
  derive_sse_post_url,
  derive_sse_stream_url,
  deriveSsePostUrl,
  deriveSseStreamUrl,
  encodeSdkJsonlMessage,
  parse_sse_frames,
  parseSseFrames,
  SDKSSEJsonlTransport,
  SdkSseJsonlTransport,
  type SdkMessage
} from "@kevin/core/sdk";

describe("SDK SSE JSONL transport", () => {
  test("parses SSE frames and derives remote SDK URLs", () => {
    const payload = JSON.stringify({
      payload: {
        type: "keep_alive"
      }
    });
    const parsed = parseSseFrames(`: ping\n\nid: 7\nevent: client_event\ndata: ${payload}\n\npartial`);

    expect(parsed.frames).toEqual([
      {},
      {
        id: "7",
        event: "client_event",
        data: payload
      }
    ]);
    expect(parsed.rest).toBe("partial");
    expect(deriveSseStreamUrl("wss://relay.test/session?token=1")).toBe(
      "https://relay.test/session/worker/events/stream?token=1"
    );
    expect(deriveSsePostUrl("https://relay.test/session/worker/events/stream?token=1#frag")).toBe(
      "https://relay.test/session/worker/events"
    );
    expect(deriveSseStreamUrl("/session?token=1#frag")).toBe(
      "/session/worker/events/stream?token=1#frag"
    );
    expect(deriveSsePostUrl("/session/worker/events/stream?token=1#frag")).toBe(
      "/session/worker/events"
    );
    expect(deriveSsePostUrl("https://relay.test/stream?token=1")).toBe("https://relay.test");
    expect(derive_sse_stream_url("wss://relay.test/session?token=1")).toBe(
      "https://relay.test/session/worker/events/stream?token=1"
    );
    expect(derive_sse_post_url("https://relay.test/session/worker/events/stream?token=1#frag")).toBe(
      "https://relay.test/session/worker/events"
    );
    expect(parse_sse_frames(`event: client_event\ndata: ${payload}\n\npartial`)).toEqual({
      frames: [{ event: "client_event", data: payload }],
      rest: "partial"
    });
  });

  test("reads SDK JSONL payloads from SSE client events", async () => {
    const userMessage: SdkMessage = {
      type: "user_message",
      uuid: "sse_message_1",
      sessionId: "sse_session",
      content: "from sse"
    };
    const observedEvents: Record<string, unknown>[] = [];
    let observedUrl = "";
    let observedHeaders: Record<string, string> = {};
    let observedConnectedStatus = false;
    const transport = new SDKSSEJsonlTransport("https://relay.test/events/stream", {
      headers: { Authorization: "Bearer static" },
      initial_sequence_num: 5,
      reconnect: false,
      read_chunks_factory(url, headers) {
        observedConnectedStatus = transport.is_connected_status();
        observedUrl = url;
        observedHeaders = headers;
        return sseChunks([
          `event: ignored\ndata: ${JSON.stringify({ payload: { type: "keep_alive" } })}\n\n`,
          `id: 7\nevent: client_event\ndata: ${JSON.stringify({ payload: userMessage, trace: "event_1" })}\n\n`
        ]);
      }
    });
    transport.set_on_event((event) => observedEvents.push(event));

    const line = await transport.read();
    const end = await transport.read();

    expect(decodeSdkJsonlLine(String(line).trim())).toEqual(userMessage);
    expect(end).toBeUndefined();
    expect(transport.last_sequence_num).toBe(7);
    expect(transport.get_last_sequence_num()).toBe(7);
    expect(observedConnectedStatus).toBe(true);
    expect(transport.is_closed_status()).toBe(true);
    expect(observedUrl).toBe("https://relay.test/events/stream?from_sequence_num=5");
    expect(observedHeaders).toMatchObject({
      Authorization: "Bearer static",
      Accept: "text/event-stream",
      "Last-Event-ID": "5"
    });
    expect(observedEvents).toEqual([{ payload: userMessage, trace: "event_1" }]);
  });

  test("posts SDK JSONL output through the SSE transport with retry headers", async () => {
    const resultMessage: SdkMessage = {
      type: "result",
      runId: "run_sse_1",
      sessionId: "sse_session",
      status: "finished",
      content: "posted",
      isError: false,
      eventCount: 1
    };
    const posts: Array<{ url: string; headers: Record<string, string>; message: Record<string, unknown> }> = [];
    const transport = new SdkSseJsonlTransport("https://relay.test/events/stream", {
      headers: { Authorization: "Bearer static" },
      session_id: "sse_session_attr",
      post_max_retries: 2,
      post_base_delay_seconds: 0,
      post_max_delay_seconds: 2,
      post_message: async (url, headers, message) => {
        posts.push({ url, headers, message });
        return posts.length === 1 ? 429 : 201;
      }
    });

    expect(transport.headers).toEqual({ Authorization: "Bearer static" });
    expect(transport.sessionId).toBe("sse_session_attr");
    expect(transport.session_id).toBe("sse_session_attr");
    expect(transport.postUrl).toBe("https://relay.test/events");
    expect(transport.post_url).toBe(transport.postUrl);
    expect(transport.postMaxRetries).toBe(2);
    expect(transport.post_max_retries).toBe(2);
    expect(transport.postBaseDelayMs).toBe(0);
    expect(transport.post_base_delay_seconds).toBe(0);
    expect(transport.postMaxDelayMs).toBe(2000);
    expect(transport.post_max_delay_seconds).toBe(2);

    await transport.write(encodeSdkJsonlMessage(resultMessage));

    expect(posts).toEqual([
      {
        url: "https://relay.test/events",
        headers: {
          Authorization: "Bearer static",
          "Content-Type": "application/json",
          "anthropic-version": "2023-06-01",
          "User-Agent": "kevin-sdk"
        },
        message: resultMessage
      },
      {
        url: "https://relay.test/events",
        headers: {
          Authorization: "Bearer static",
          "Content-Type": "application/json",
          "anthropic-version": "2023-06-01",
          "User-Agent": "kevin-sdk"
        },
        message: resultMessage
      }
    ]);
  });

  test("supports relative SSE stream URLs with sequence cursors", async () => {
    const userMessage: SdkMessage = {
      type: "user_message",
      uuid: "relative_sse_message",
      sessionId: "relative_sse_session",
      content: "from relative sse"
    };
    let observedUrl = "";
    const transport = new SdkSseJsonlTransport("/events/stream?token=1", {
      initial_sequence_num: 9,
      reconnect: false,
      read_chunks_factory(url) {
        observedUrl = url;
        return sseChunks([
          `id: 10\nevent: client_event\ndata: ${JSON.stringify({ payload: userMessage })}\n\n`
        ]);
      }
    });

    const line = await transport.read();
    const end = await transport.read();

    expect(decodeSdkJsonlLine(String(line).trim())).toEqual(userMessage);
    expect(end).toBeUndefined();
    expect(observedUrl).toBe("/events/stream?token=1&from_sequence_num=9");
    expect(transport.getLastSequenceNum()).toBe(10);
  });

  test("routes Python-style SSE close handlers", async () => {
    const closeCodes: Array<number | undefined> = [];
    const transport = new SDKSSEJsonlTransport("https://relay.test/events/stream", {
      reconnect_give_up_seconds: 0,
      read_chunks_factory() {
        throw new Error("stream failed");
      }
    });
    transport.set_on_close((closeCode) => closeCodes.push(closeCode));

    expect(await transport.read()).toBeUndefined();
    expect(closeCodes).toEqual([undefined]);
  });

  test("uses Python-style monotonic seconds for reconnect budgets", async () => {
    const calls: string[] = [];
    const closeCodes: Array<number | undefined> = [];
    const ticks = [0, 601];
    const transport = new SDKSSEJsonlTransport("https://relay.test/events/stream", {
      reconnect_base_delay_seconds: 0,
      reconnect_give_up_seconds: 600,
      monotonic: () => ticks.shift() ?? 601,
      sleep: async () => undefined,
      read_chunks_factory(url) {
        calls.push(url);
        throw new Error("stream failed");
      }
    });
    transport.set_on_close((closeCode) => closeCodes.push(closeCode));

    expect(await transport.read()).toBeUndefined();
    expect(calls).toHaveLength(2);
    expect(closeCodes).toEqual([undefined]);
    expect(transport.is_closed_status()).toBe(true);
  });
});

async function* sseChunks(chunks: string[]): AsyncIterable<string | Uint8Array> {
  for (const chunk of chunks) yield chunk;
}
