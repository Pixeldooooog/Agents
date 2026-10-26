import { describe, expect, test } from "bun:test";
import {
  SDKCCRClient,
  SdkCcrAuthFailureError,
  SdkCcrClient,
  SdkCcrEpochMismatchError,
  SdkCcrInitError,
  normalizeCcrSessionUrl,
  pathWithQuery,
  type SdkCcrRequestHandler
} from "@kevin/core/sdk";

describe("SDK CCR client", () => {
  test("initializes worker state and acks transport delivery events", async () => {
    const requests: RequestRecord[] = [];
    let onTransportEvent: ((event: Record<string, unknown>) => void) | undefined;
    expect(SDKCCRClient).toBe(SdkCcrClient);
    const client = new SDKCCRClient("https://api.example.com/v1/code/sessions/session-1?token=drop", {
      transport: {
        setOnEvent(handler) {
          onTransportEvent = handler;
        }
      },
      getAuthHeaders: () => ({ Authorization: "Bearer token" }),
      heartbeatIntervalMs: 0,
      request: async (method, path, headers, body) => {
        requests.push({ method, path, headers, body });
        if (method === "get" && path === "/worker") {
          return { ok: true, data: { worker: { external_metadata: { pending_action: "approve" } } } };
        }
        return { ok: true, status: 200 };
      }
    });

    expect(client.session_base_url).toBe(client.sessionBaseUrl);
    expect(client.session_id).toBe(client.sessionId);
    expect(client.worker_state).toBe(client.workerState);
    expect(client.event_uploader).toBe(client.eventUploader);
    expect(client.internal_event_uploader).toBe(client.internalEventUploader);
    expect(client.delivery_uploader).toBe(client.deliveryUploader);
    expect(client.worker_epoch).toBe(0);
    expect(client.current_state).toBeUndefined();
    expect(client.shutdown_reason).toBeUndefined();
    expect(client.internal_events_pending).toBe(client.internalEventsPending);

    const restored = await client.initialize(7);
    onTransportEvent?.({ event_id: "evt-1" });
    await client.flushDelivery();
    await client.close();

    expect(client.sessionBaseUrl).toBe("https://api.example.com/v1/code/sessions/session-1");
    expect(client.sessionId).toBe("session-1");
    expect(client.worker_epoch).toBe(7);
    expect(client.current_state).toBe("idle");
    expect(restored).toEqual({ pending_action: "approve" });
    expect(requests[0]).toMatchObject({
      method: "put",
      path: "/worker",
      headers: { Authorization: "Bearer token" },
      body: {
        worker_status: "idle",
        worker_epoch: 7,
        external_metadata: { pending_action: null, task_summary: null }
      }
    });
    expect(requests.some((request) => request.method === "get" && request.path === "/worker")).toBe(true);
    expect(requests.at(-1)).toMatchObject({
      method: "post",
      path: "/worker/events/delivery",
      body: {
        worker_epoch: 7,
        updates: [{ event_id: "evt-1", status: "received" }]
      }
    });
  });

  test("mutates Python-style CCR client state aliases", async () => {
    const client = new SdkCcrClient("https://api.example.com/v1/code/sessions/session-state-alias", {
      getAuthHeaders: () => ({ Authorization: "Bearer token" }),
      heartbeatIntervalMs: 0,
      request: captureOkRequests([])
    });

    client.worker_epoch = 9;
    client.current_state = "busy";
    client.shutdown_reason = "auth_expired";

    expect(client.workerEpoch).toBe(9);
    expect(client.currentState).toBe("busy");
    expect(client.shutdownReason).toBe("auth_expired");
    await client.close();
  });

  test("does not wait for pending worker state restore when initialization fails", async () => {
    const client = new SdkCcrClient("https://api.example.com/v1/code/sessions/session-init-fail", {
      getAuthHeaders: () => ({ Authorization: "Bearer token" }),
      heartbeatIntervalMs: 0,
      request: async (method) => {
        if (method === "get") return new Promise(() => undefined);
        return { ok: false, status: 500 };
      }
    });

    const result = await Promise.race([
      client.initialize(8).then(
        () => "resolved",
        (error) => error
      ),
      delay(50).then(() => "timeout")
    ]);

    expect(result).toBeInstanceOf(SdkCcrInitError);
    await client.close();
  });

  test("writes client stream events and internal events", async () => {
    const requests: RequestRecord[] = [];
    const client = new SdkCcrClient("https://api.example.com/v1/code/sessions/session-2", {
      getAuthHeaders: () => ({ Authorization: "Bearer token" }),
      heartbeatIntervalMs: 0,
      streamEventFlushIntervalMs: 60000,
      request: captureOkRequests(requests)
    });

    await client.writeEvent({
      type: "stream_event",
      sessionId: "session-2",
      event: { type: "message_start", message: { id: "msg-1" } }
    });
    await client.writeEvent(textDelta("session-2", 0, "hel", "delta-1"));
    await client.writeEvent(textDelta("session-2", 0, "lo", "delta-2"));
    await client.writeEvent({ type: "result", sessionId: "session-2", content: "done", uuid: "result-1" });
    await client.flush();

    await client.writeInternalEvent("worker_note", { body: "internal" }, { isCompaction: true, agentId: "agent-1" });
    await client.flushInternalEvents();
    await client.close();

    const clientEventPosts = requests.filter((request) => request.path === "/worker/events");
    const postedEvents = clientEventPosts.flatMap((request) => request.body?.events as any[]);
    expect(postedEvents).toHaveLength(3);
    expect(postedEvents[0]).toMatchObject({
      ephemeral: true,
      payload: {
        type: "stream_event",
        sessionId: "session-2",
        event: { type: "message_start", message: { id: "msg-1" } }
      }
    });
    expect(postedEvents[1]).toMatchObject(
      {
        ephemeral: true,
        payload: {
          type: "stream_event",
          uuid: "delta-1",
          sessionId: "session-2",
          event: {
            type: "content_block_delta",
            index: 0,
            delta: { type: "text_delta", text: "hello" }
          }
        }
      }
    );
    expect(postedEvents[2]).toEqual(
      {
        payload: {
          type: "result",
          uuid: "result-1",
          sessionId: "session-2",
          content: "done"
        }
      }
    );

    const internalPost = requests.find((request) => request.path === "/worker/internal-events");
    expect(internalPost?.body).toMatchObject({
      worker_epoch: 0,
      events: [{
        is_compaction: true,
        agent_id: "agent-1",
        payload: {
          type: "worker_note",
          body: "internal"
        }
      }]
    });
    expect((internalPost?.body?.events as any[])[0].payload.uuid).toEqual(expect.any(String));
  });

  test("reads paginated internal events", async () => {
    const requests: RequestRecord[] = [];
    const client = new SdkCcrClient("https://api.example.com/v1/code/sessions/session-3", {
      getAuthHeaders: () => ({ Authorization: "Bearer token" }),
      heartbeatIntervalMs: 0,
      getBaseDelayMs: 0,
      request: async (method, path, headers, body) => {
        requests.push({ method, path, headers, body });
        if (path === "/worker/internal-events?subagents=true") {
          return { ok: true, data: { data: [{ id: "evt-1" }], next_cursor: "cursor-2" } };
        }
        if (path === "/worker/internal-events?subagents=true&cursor=cursor-2") {
          return { ok: true, data: { data: [{ id: "evt-2" }] } };
        }
        return { ok: false, status: 404 };
      }
    });

    const events = await client.readSubagentInternalEvents();

    expect(events).toEqual([{ id: "evt-1" }, { id: "evt-2" }]);
    expect(requests.map((request) => request.path)).toEqual([
      "/worker/internal-events?subagents=true",
      "/worker/internal-events?subagents=true&cursor=cursor-2"
    ]);
  });

  test("parses CCR HTTP JSON responses without content-type headers", async () => {
    const server = Bun.serve({
      port: 0,
      fetch(request) {
        const url = new URL(request.url);
        if (url.pathname.endsWith("/worker")) {
          return new Response(JSON.stringify({
            worker: { external_metadata: { pending_action: "review" } }
          }));
        }
        return new Response("not found", { status: 404 });
      }
    });
    try {
      const client = new SdkCcrClient(`http://127.0.0.1:${server.port}/v1/code/sessions/session-http`, {
        getAuthHeaders: () => ({ Authorization: "Bearer token" }),
        heartbeatIntervalMs: 0
      });

      expect(await client.getWorkerState()).toEqual({ pending_action: "review" });
      await client.close();
    } finally {
      server.stop(true);
    }
  });

  test("accepts Python-style CCR option aliases and retry-after seconds", async () => {
    const sleeps: number[] = [];
    const shutdowns: string[] = [];
    let onTransportEvent: ((event: Record<string, unknown>) => void) | undefined;
    let eventPostAttempts = 0;
    let deliveryPosts = 0;
    const client = new SdkCcrClient("https://api.example.com/v1/code/sessions/session-alias", {
      transport: {
        set_on_event(handler) {
          onTransportEvent = handler;
        }
      },
      get_auth_headers: () => ({ Authorization: "Bearer token" }),
      heartbeat_interval_seconds: null,
      stream_event_flush_interval_seconds: 60,
      get_base_delay_seconds: 0.25,
      get_max_delay_seconds: 1,
      on_shutdown: async (reason) => {
        shutdowns.push(reason);
      },
      sleep: async (milliseconds) => {
        sleeps.push(milliseconds);
      },
      request: async (method, path) => {
        if (method === "post" && path === "/worker/events") {
          eventPostAttempts += 1;
          if (eventPostAttempts === 1) return { ok: false, status: 429, retry_after_seconds: 0.75 };
        }
        if (method === "post" && path === "/worker/events/delivery") deliveryPosts += 1;
        return { ok: true, status: 200 };
      }
    });

    await client.writeEvent({ type: "result", session_id: "session-alias", content: "done" });
    await client.flush();
    onTransportEvent?.({ event_id: "evt-alias" });
    await client.flushDelivery();

    expect(eventPostAttempts).toBe(2);
    expect(deliveryPosts).toBe(1);
    expect(sleeps).toEqual([750]);
    expect(shutdowns).toEqual([]);

    const shutdownClient = new SdkCcrClient("https://api.example.com/v1/code/sessions/session-shutdown", {
      get_auth_headers: () => ({ Authorization: "Bearer token" }),
      heartbeat_interval_seconds: null,
      on_shutdown: async (reason) => {
        shutdowns.push(reason);
      },
      request: async () => ({ ok: false, status: 409 })
    });

    await shutdownClient.writeEvent({ type: "result", content: "done" });
    await shutdownClient.flush();
    expect(shutdowns).toEqual(["epoch_mismatch"]);
  });

  test("shuts down on epoch mismatch", async () => {
    const shutdowns: string[] = [];
    const client = new SdkCcrClient("https://api.example.com/v1/code/sessions/session-4", {
      getAuthHeaders: () => ({ Authorization: "Bearer token" }),
      heartbeatIntervalMs: 0,
      onShutdown: (reason) => shutdowns.push(reason),
      request: async () => ({ ok: false, status: 409 })
    });

    await client.writeEvent({ type: "result", content: "done" });

    await client.flush();
    expect(client.closed).toBe(true);
    expect(client.shutdownReason).toBe("epoch_mismatch");
    expect(shutdowns).toEqual(["epoch_mismatch"]);
  });

  test("throws epoch mismatch errors on direct CCR reads", async () => {
    const client = new SdkCcrClient("https://api.example.com/v1/code/sessions/session-4b", {
      getAuthHeaders: () => ({ Authorization: "Bearer token" }),
      heartbeatIntervalMs: 0,
      request: async () => ({ ok: false, status: 409 })
    });

    await expect(client.getWorkerState()).rejects.toBeInstanceOf(SdkCcrEpochMismatchError);
    expect(client.shutdownReason).toBe("epoch_mismatch");
  });

  test("shuts down on expired auth tokens", async () => {
    const shutdowns: string[] = [];
    const expiredToken = jwtWithPayload({ exp: 10 });
    const client = new SdkCcrClient("https://api.example.com/v1/code/sessions/session-5", {
      getAuthHeaders: () => ({ Authorization: `Bearer ${expiredToken}` }),
      heartbeatIntervalMs: 0,
      now: () => 20,
      onShutdown: (reason) => shutdowns.push(reason),
      request: async () => ({ ok: false, status: 401 })
    });

    await expect(client.getWorkerState()).rejects.toBeInstanceOf(SdkCcrAuthFailureError);
    expect(client.closed).toBe(true);
    expect(client.shutdownReason).toBe("auth_expired");
    expect(shutdowns).toEqual(["auth_expired"]);
  });

  test("normalizes CCR paths", () => {
    expect(normalizeCcrSessionUrl("https://api.example.com/v1/code/sessions/session-6/?token=drop#x")).toBe(
      "https://api.example.com/v1/code/sessions/session-6"
    );
    expect(normalizeCcrSessionUrl("/v1/code/sessions/session-6/?token=drop#x")).toBe(
      "/v1/code/sessions/session-6"
    );
    expect(pathWithQuery("/worker/internal-events", { subagents: "true" }, "cursor-1")).toBe(
      "/worker/internal-events?subagents=true&cursor=cursor-1"
    );
  });
});

type RequestRecord = {
  method: string;
  path: string;
  headers: Record<string, string>;
  body?: Record<string, unknown>;
};

function captureOkRequests(requests: RequestRecord[]): SdkCcrRequestHandler {
  return async (method, path, headers, body) => {
    requests.push({ method, path, headers, body });
    return { ok: true, status: 200 };
  };
}

function delay(milliseconds: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

function textDelta(sessionId: string, index: number, text: string, uuid: string): Record<string, unknown> {
  return {
    type: "stream_event",
    uuid,
    sessionId,
    event: {
      type: "content_block_delta",
      index,
      delta: { type: "text_delta", text }
    }
  };
}

function jwtWithPayload(payload: Record<string, unknown>): string {
  return `${base64Url({ alg: "none" })}.${base64Url(payload)}.`;
}

function base64Url(value: Record<string, unknown>): string {
  return Buffer
    .from(JSON.stringify(value), "utf8")
    .toString("base64")
    .replace(/=/g, "")
    .replace(/\+/g, "-")
    .replace(/\//g, "_");
}
