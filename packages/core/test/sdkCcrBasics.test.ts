import { describe, expect, test } from "bun:test";
import {
  CCR_GET_BASE_DELAY_SECONDS,
  CCR_GET_MAX_ATTEMPTS,
  CCR_GET_MAX_DELAY_SECONDS,
  CCR_HEARTBEAT_INTERVAL_SECONDS,
  CCR_MAX_CONSECUTIVE_AUTH_FAILURES,
  CCR_STREAM_EVENT_FLUSH_INTERVAL_SECONDS,
  CCR_UPLOAD_BASE_DELAY_SECONDS,
  CCR_UPLOAD_MAX_DELAY_SECONDS,
  CCR_WORKER_STATE_BASE_DELAY_SECONDS,
  CCR_WORKER_STATE_MAX_DELAY_SECONDS,
  SDKCCRAuthFailureError,
  SDKCCRClient,
  SDKCCREpochMismatchError,
  SDKCCRInitError,
  SDKCCRRequestResult,
  SDKCCRShutdownError,
  SDKCCRStreamAccumulator,
  SDKWorkerStateUploader,
  SdkCcrClient,
  SdkCcrStreamAccumulator,
  SdkCcrWorkerStateUploader,
  accumulate_stream_events,
  accumulateCcrStreamEvents,
  clear_stream_accumulator_for_message,
  clearCcrStreamAccumulatorForMessage,
  coalesce_worker_state_patches,
  coalesceCcrWorkerStatePatches,
  decode_jwt_expiry,
  decodeJwtExpiry,
  extract_bearer_token,
  extractBearerToken
} from "@agents/core/sdk";
import type {
  SDKCCRDeliveryStatus,
  SDKCCRRequestHandler,
  SDKCCRShutdownReason
} from "@agents/core/sdk";

describe("SDK CCR basics", () => {
  test("exposes Python-style CCR public names", async () => {
    const token = jwtWithPayload({ exp: 1780912383 });
    const status: SDKCCRDeliveryStatus = "received";
    const shutdownReason: SDKCCRShutdownReason = "auth_expired";
    const requestHandler: SDKCCRRequestHandler = async () => new SDKCCRRequestResult(false, {
      status: 429,
      data: { retry: true },
      retry_after_seconds: 2
    });
    const requestResult = await requestHandler("get", "/worker", {}, undefined);

    expect(status).toBe("received");
    expect(shutdownReason).toBe("auth_expired");
    expect(requestResult).toBeInstanceOf(SDKCCRRequestResult);
    expect(requestResult).toMatchObject({
      ok: false,
      status: 429,
      data: { retry: true },
      retry_after_seconds: 2
    });
    expect(new SDKCCRInitError("init")).toBeInstanceOf(SDKCCRInitError);
    expect(new SDKCCRShutdownError("auth_expired")).toBeInstanceOf(SDKCCRShutdownError);
    expect(new SDKCCREpochMismatchError()).toBeInstanceOf(SDKCCRShutdownError);
    expect(new SDKCCRAuthFailureError()).toBeInstanceOf(SDKCCRShutdownError);
    expect(SDKCCRClient).toBe(SdkCcrClient);
    expect(SDKCCRStreamAccumulator).toBe(SdkCcrStreamAccumulator);
    expect(SDKWorkerStateUploader).toBe(SdkCcrWorkerStateUploader);
    expect(accumulate_stream_events).toBe(accumulateCcrStreamEvents);
    expect(clear_stream_accumulator_for_message).toBe(clearCcrStreamAccumulatorForMessage);
    expect(coalesce_worker_state_patches).toBe(coalesceCcrWorkerStatePatches);
    expect(extract_bearer_token({ Authorization: `Bearer ${token}` })).toBe(token);
    expect(decode_jwt_expiry(token)).toBe(1780912383);
    expect(CCR_HEARTBEAT_INTERVAL_SECONDS).toBe(20);
    expect(CCR_UPLOAD_BASE_DELAY_SECONDS).toBe(0.5);
    expect(CCR_UPLOAD_MAX_DELAY_SECONDS).toBe(30);
    expect(CCR_WORKER_STATE_BASE_DELAY_SECONDS).toBe(0.5);
    expect(CCR_WORKER_STATE_MAX_DELAY_SECONDS).toBe(30);
    expect(CCR_STREAM_EVENT_FLUSH_INTERVAL_SECONDS).toBe(0.1);
    expect(CCR_GET_MAX_ATTEMPTS).toBe(10);
    expect(CCR_GET_BASE_DELAY_SECONDS).toBe(0.5);
    expect(CCR_GET_MAX_DELAY_SECONDS).toBe(30);
    expect(CCR_MAX_CONSECUTIVE_AUTH_FAILURES).toBe(10);
  });

  test("extracts bearer tokens and decodes JWT expiries", () => {
    const token = jwtWithPayload({ exp: 1780912383 });

    expect(extractBearerToken({ Authorization: `Bearer ${token}` })).toBe(token);
    expect(extractBearerToken({ authorization: "Basic test" })).toBeUndefined();
    expect(decodeJwtExpiry(token)).toBe(1780912383);
    expect(decodeJwtExpiry("not-a-jwt")).toBeUndefined();
  });

  test("accumulates text deltas within stream event scopes", () => {
    const state = new SdkCcrStreamAccumulator();
    const firstBatch = accumulateCcrStreamEvents([
      {
        type: "stream_event",
        sessionId: "session_1",
        event: {
          type: "message_start",
          message: { id: "message_1" }
        }
      },
      textDelta("session_1", 0, "hel", "delta_1"),
      textDelta("session_1", 0, "lo", "delta_2")
    ], state);
    const secondBatch = accumulateCcrStreamEvents([
      textDelta("session_1", 0, " world", "delta_3")
    ], state);

    expect(firstBatch).toEqual([
      {
        type: "stream_event",
        sessionId: "session_1",
        event: {
          type: "message_start",
          message: { id: "message_1" }
        }
      },
      {
        type: "stream_event",
        uuid: "delta_1",
        sessionId: "session_1",
        parentToolUseId: undefined,
        event: {
          type: "content_block_delta",
          index: 0,
          delta: { type: "text_delta", text: "hello" }
        }
      }
    ]);
    expect(secondBatch).toEqual([
      {
        type: "stream_event",
        uuid: "delta_3",
        sessionId: "session_1",
        parentToolUseId: undefined,
        event: {
          type: "content_block_delta",
          index: 0,
          delta: { type: "text_delta", text: "hello world" }
        }
      }
    ]);
  });

  test("clears stream accumulator state for completed assistant messages", () => {
    const state = new SdkCcrStreamAccumulator();
    accumulateCcrStreamEvents([
      {
        type: "stream_event",
        sessionId: "session_1",
        parentToolUseId: "tool_1",
        event: {
          type: "message_start",
          message: { id: "message_1" }
        }
      }
    ], state);

    clearCcrStreamAccumulatorForMessage(state, {
      sessionId: "session_1",
      parentToolUseId: "tool_1",
      message: { id: "message_1" }
    });

    expect(state.byMessage.has("message_1")).toBe(false);
    expect(state.scopeToMessage.has("session_1:tool_1")).toBe(false);
  });

  test("accumulates snake_case CCR stream event scopes", () => {
    const state = new SdkCcrStreamAccumulator();
    const output = accumulateCcrStreamEvents([
      {
        type: "stream_event",
        session_id: "session_1",
        parent_tool_use_id: "tool_1",
        event: {
          type: "message_start",
          message: { id: "message_1" }
        }
      },
      snakeTextDelta("session_1", "tool_1", 0, "py", "delta_1"),
      snakeTextDelta("session_1", "tool_1", 0, "thon", "delta_2")
    ], state);

    expect(output.at(-1)).toEqual({
      type: "stream_event",
      uuid: "delta_1",
      session_id: "session_1",
      parent_tool_use_id: "tool_1",
      event: {
        type: "content_block_delta",
        index: 0,
        delta: { type: "text_delta", text: "python" }
      }
    });

    clearCcrStreamAccumulatorForMessage(state, {
      session_id: "session_1",
      parent_tool_use_id: "tool_1",
      message: { id: "message_1" }
    });
    expect(state.byMessage.has("message_1")).toBe(false);
    expect(state.scopeToMessage.has("session_1:tool_1")).toBe(false);
  });

  test("coalesces worker state metadata patches", () => {
    expect(coalesceCcrWorkerStatePatches(
      {
        worker_status: "idle",
        external_metadata: { pending_action: "approve" },
        internal_metadata: { epoch: 1 }
      },
      {
        worker_status: "busy",
        external_metadata: { task_summary: "running" },
        internal_metadata: { last_event_id: "evt_1" }
      }
    )).toEqual({
      worker_status: "busy",
      external_metadata: {
        pending_action: "approve",
        task_summary: "running"
      },
      internal_metadata: {
        epoch: 1,
        last_event_id: "evt_1"
      }
    });
  });

  test("uploads worker state patches with retry-time coalescing", async () => {
    const sent: Record<string, unknown>[] = [];
    let uploader: SdkCcrWorkerStateUploader;
    let enqueuedDuringBackoff = false;
    uploader = new SdkCcrWorkerStateUploader(async (patch) => {
      sent.push(structuredClone(patch));
      return sent.length >= 2;
    }, {
      baseDelayMs: 0,
      sleep: async () => {
        if (enqueuedDuringBackoff) return;
        enqueuedDuringBackoff = true;
        uploader.enqueue({
          worker_status: "busy",
          external_metadata: { task_summary: "running" }
        });
      }
    });

    expect(uploader.pending_count).toBe(0);

    uploader.enqueue({
      worker_status: "idle",
      external_metadata: { pending_action: "approve" }
    });
    expect(uploader.pending_count).toBe(uploader.pendingCount);
    await uploader.flush();
    expect(uploader.pending_count).toBe(0);

    expect(sent).toEqual([
      {
        worker_status: "idle",
        external_metadata: { pending_action: "approve" }
      },
      {
        worker_status: "busy",
        external_metadata: {
          pending_action: "approve",
          task_summary: "running"
        }
      }
    ]);
  });

  test("accepts worker state uploader second-based delay aliases", async () => {
    const sleeps: number[] = [];
    let attempts = 0;
    const uploader = new SdkCcrWorkerStateUploader(async () => {
      attempts += 1;
      return attempts >= 2;
    }, {
      base_delay_seconds: 0.25,
      max_delay_seconds: 1,
      sleep: async (milliseconds) => {
        sleeps.push(milliseconds);
      }
    });

    uploader.enqueue({ worker_status: "idle" });
    await uploader.flush();

    expect(sleeps).toEqual([250]);
  });

  test("releases worker state retry waits when closed", async () => {
    const sleeps: number[] = [];
    const uploader = new SdkCcrWorkerStateUploader(async () => false, {
      baseDelayMs: 1000,
      sleep: async (milliseconds) => {
        sleeps.push(milliseconds);
        await new Promise(() => undefined);
      }
    });

    uploader.enqueue({ worker_status: "idle" });
    await waitFor(() => sleeps.length > 0);
    uploader.close();

    const result = await Promise.race([
      uploader.flush().then(() => "flushed"),
      delay(50).then(() => "timeout")
    ]);

    expect(result).toBe("flushed");
    expect(sleeps).toEqual([1000]);
  });
});

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

function snakeTextDelta(
  sessionId: string,
  parentToolUseId: string,
  index: number,
  text: string,
  uuid: string
): Record<string, unknown> {
  return {
    type: "stream_event",
    uuid,
    session_id: sessionId,
    parent_tool_use_id: parentToolUseId,
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

async function waitFor(predicate: () => boolean): Promise<void> {
  for (let attempt = 0; attempt < 50; attempt += 1) {
    if (predicate()) return;
    await delay(5);
  }
  throw new Error("condition not reached");
}

function delay(milliseconds: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

function base64Url(value: Record<string, unknown>): string {
  return Buffer
    .from(JSON.stringify(value), "utf8")
    .toString("base64")
    .replace(/=/g, "")
    .replace(/\+/g, "-")
    .replace(/\//g, "_");
}
