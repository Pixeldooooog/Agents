import { describe, expect, test } from "bun:test";
import {
  SDKSerialBatchUploader,
  SdkRetryableBatchError,
  SdkSerialBatchUploader
} from "@agents/core/sdk";

describe("SDK serial batch uploader", () => {
  test("honors retry-after seconds aliases on retryable batch errors", async () => {
    const sleeps: number[] = [];
    const sentBatches: Array<Record<string, unknown>[]> = [];
    const uploader = new SdkSerialBatchUploader({
      maxBatchSize: 1,
      maxQueueSize: 10,
      baseDelayMs: 500,
      maxDelayMs: 8000,
      sleep: async (milliseconds) => {
        sleeps.push(milliseconds);
      },
      send: async (messages) => {
        sentBatches.push(messages);
        if (sentBatches.length === 1) {
          throw new SdkRetryableBatchError("retry", { retry_after_seconds: 0.75 });
        }
      }
    });

    await uploader.enqueue([{ type: "result", uuid: "batch_1" }]);
    await uploader.flush();

    expect(sentBatches).toEqual([
      [{ type: "result", uuid: "batch_1" }],
      [{ type: "result", uuid: "batch_1" }]
    ]);
    expect(sleeps).toEqual([750]);
  });

  test("keeps positional retry-after milliseconds for existing callers", () => {
    const error = new SdkRetryableBatchError("retry", 2500);

    expect(error.retryAfterMs).toBe(2500);
    expect(error.retryAfterSeconds).toBeUndefined();
    expect(error.retry_after_seconds).toBeUndefined();
  });

  test("mirrors Python-style uploader option and counter names", async () => {
    const dropped: Array<{ batchSize: number; failures: number }> = [];
    const sentBatches: Array<Record<string, unknown>[]> = [];
    const uploader = new SDKSerialBatchUploader({
      max_batch_size: 1,
      max_queue_size: 10,
      base_delay_seconds: 0,
      max_delay_seconds: 1,
      max_consecutive_failures: 1,
      on_batch_dropped: (batchSize, failures) => dropped.push({ batchSize, failures }),
      send: async (messages) => {
        sentBatches.push(messages);
        throw new Error("drop");
      }
    });

    await uploader.enqueue([{ type: "result", uuid: "batch_python_1" }]);
    await uploader.flush();

    expect(sentBatches).toEqual([[{ type: "result", uuid: "batch_python_1" }]]);
    expect(dropped).toEqual([{ batchSize: 1, failures: 1 }]);
    expect(uploader.dropped_batch_count).toBe(1);
    expect(uploader.pending_count).toBe(0);
  });
});
