import { describe, expect, test } from "bun:test";
import {
  SDKHybridJsonlTransport,
  SdkHybridJsonlTransport,
  SdkQueueJsonlTransport,
  derive_hybrid_post_url,
  deriveHybridPostUrl
} from "@kevin/core/sdk";

describe("SDK hybrid JSONL transport", () => {
  test("derives hybrid post URLs from websocket ingress URLs", () => {
    expect(deriveHybridPostUrl("wss://api.example.com/v2/session_ingress/ws/abc?token=1")).toBe(
      "https://api.example.com/v2/session_ingress/session/abc/events?token=1"
    );
    expect(deriveHybridPostUrl("/v2/session_ingress/ws/abc?token=1#frag")).toBe(
      "/v2/session_ingress/session/abc/events?token=1#frag"
    );
    expect(derive_hybrid_post_url("wss://api.example.com/v2/session_ingress/ws/abc?token=1")).toBe(
      "https://api.example.com/v2/session_ingress/session/abc/events?token=1"
    );
  });

  test("reads from the reader and batches ordered posts", async () => {
    const reader = new SdkQueueJsonlTransport();
    const posted: Array<{ url: string; headers: Record<string, string>; body: Record<string, unknown> }> = [];
    const transport = new SdkHybridJsonlTransport("wss://api.example.com/v2/session_ingress/ws/abc?token=1", {
      headers: { Authorization: "Bearer token" },
      refresh_headers: () => ({ "X-Fresh": "yes" }),
      reader,
      stream_event_flush_interval_seconds: 60,
      close_grace_seconds: 2,
      post_message: async (url, headers, body) => {
        posted.push({ url, headers, body });
        return 200;
      }
    });

    expect(transport.post_url).toBe("https://api.example.com/v2/session_ingress/session/abc/events?token=1");
    expect(transport.postUrl).toBe(transport.post_url);
    expect(transport.stream_event_flush_interval_seconds).toBe(60);
    expect(transport.streamEventFlushIntervalMs).toBe(60000);
    expect(transport.close_grace_seconds).toBe(2);
    expect(transport.closeGraceMs).toBe(2000);

    reader.send("{\"type\":\"keep_alive\"}\n");
    const inbound = await transport.read();
    await transport.write("{\"type\":\"stream_event\",\"delta\":\"a\"}\n");
    await transport.write("{\"type\":\"result\",\"result\":\"done\"}\n");
    await transport.close();

    expect(inbound).toBe("{\"type\":\"keep_alive\"}\n");
    expect(posted[0]).toEqual({
      url: "https://api.example.com/v2/session_ingress/session/abc/events?token=1",
      headers: {
        Authorization: "Bearer token",
        "X-Fresh": "yes",
        "Content-Type": "application/json"
      },
      body: {
        events: [
          { type: "stream_event", delta: "a" },
          { type: "result", result: "done" }
        ]
      }
    });
  });

  test("retries retryable posts and tracks dropped batches", async () => {
    const statuses = [500, 500];
    const posted: Record<string, unknown>[] = [];
    const dropped: Array<{ batchSize: number; failures: number }> = [];
    const transport = new SdkHybridJsonlTransport("wss://api.example.com/v2/session_ingress/ws/abc", {
      reader: new SdkQueueJsonlTransport(),
      max_consecutive_failures: 2,
      post_base_delay_seconds: 0,
      sleep: async () => undefined,
      on_batch_dropped: (batchSize, failures) => dropped.push({ batchSize, failures }),
      post_message: async (_url, _headers, body) => {
        posted.push(body);
        return statuses.shift() ?? 200;
      }
    });

    await transport.write("{\"type\":\"result\",\"result\":\"dropped\"}\n");
    await transport.close();

    expect(posted).toEqual([
      { events: [{ type: "result", result: "dropped" }] },
      { events: [{ type: "result", result: "dropped" }] }
    ]);
    expect(dropped).toEqual([{ batchSize: 1, failures: 2 }]);
    expect(transport.droppedBatchCount).toBe(1);
    expect(transport.dropped_batch_count).toBe(1);
  });

  test("posts through relative hybrid ingress URLs", async () => {
    const posted: Array<{ url: string; body: Record<string, unknown> }> = [];
    const transport = new SdkHybridJsonlTransport("/v2/session_ingress/ws/abc?token=1#frag", {
      reader: new SdkQueueJsonlTransport(),
      post_message: async (url, _headers, body) => {
        posted.push({ url, body });
        return 200;
      }
    });

    await transport.write("{\"type\":\"result\",\"result\":\"relative\"}\n");
    await transport.close();

    expect(posted).toEqual([
      {
        url: "/v2/session_ingress/session/abc/events?token=1#frag",
        body: {
          events: [{ type: "result", result: "relative" }]
        }
      }
    ]);
  });

  test("waits for buffered stream events during close even when retry sleep is overridden", async () => {
    let finishPost: (() => void) | undefined;
    const posted: Record<string, unknown>[] = [];
    const transport = new SdkHybridJsonlTransport("wss://api.example.com/v2/session_ingress/ws/abc", {
      reader: new SdkQueueJsonlTransport(),
      stream_event_flush_interval_seconds: 60,
      sleep: async () => undefined,
      post_message: async (_url, _headers, body) => {
        await new Promise<void>((resolve) => {
          finishPost = resolve;
        });
        posted.push(body);
        return 200;
      }
    });

    await transport.write("{\"type\":\"stream_event\",\"delta\":\"pending\"}\n");
    const close = transport.close();
    await Promise.resolve();

    expect(posted).toEqual([]);
    expect(finishPost).toBeDefined();

    finishPost?.();
    await close;

    expect(posted).toEqual([
      {
        events: [{ type: "stream_event", delta: "pending" }]
      }
    ]);
  });

  test("mirrors Python-style hybrid write batch API", async () => {
    const posted: Record<string, unknown>[] = [];
    const transport = new SDKHybridJsonlTransport("wss://api.example.com/v2/session_ingress/ws/abc", {
      reader: new SdkQueueJsonlTransport(),
      post_message: async (_url, _headers, body) => {
        posted.push(body);
        return 200;
      }
    });

    await transport.write_batch([{ type: "result", result: "batched" }]);
    await transport.close();

    expect(posted).toEqual([{ events: [{ type: "result", result: "batched" }] }]);
  });
});
