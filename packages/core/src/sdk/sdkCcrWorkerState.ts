import { ccrWorkerStateBaseDelayMs, ccrWorkerStateMaxDelayMs } from "./sdkCcrTypes.js";
import { ccrMillisecondsOption } from "./sdkCcrTiming.js";

export type SdkCcrWorkerStatePatch = Record<string, unknown>;
export type SdkCcrWorkerStateSendHandler = (patch: SdkCcrWorkerStatePatch) => Promise<boolean>;

export type SdkCcrWorkerStateUploaderOptions = {
  baseDelayMs?: number;
  base_delay_seconds?: number;
  maxDelayMs?: number;
  max_delay_seconds?: number;
  sleep?: (milliseconds: number) => Promise<void>;
};

export class SdkCcrWorkerStateUploader {
  private readonly send: SdkCcrWorkerStateSendHandler;
  private readonly baseDelayMs: number;
  private readonly maxDelayMs: number;
  private readonly sleep: (milliseconds: number) => Promise<void>;
  private pending: SdkCcrWorkerStatePatch | undefined;
  private drainTask?: Promise<void>;
  private closed = false;
  private closeWaiters: Array<() => void> = [];

  constructor(send: SdkCcrWorkerStateSendHandler, options: SdkCcrWorkerStateUploaderOptions = {}) {
    this.send = send;
    this.baseDelayMs = ccrMillisecondsOption(options.baseDelayMs, options.base_delay_seconds, ccrWorkerStateBaseDelayMs);
    this.maxDelayMs = ccrMillisecondsOption(options.maxDelayMs, options.max_delay_seconds, ccrWorkerStateMaxDelayMs);
    this.sleep = options.sleep || ((milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds)));
  }

  get pendingCount(): number {
    return this.pending ? 1 : 0;
  }

  get pending_count(): number {
    return this.pendingCount;
  }

  enqueue(patch: SdkCcrWorkerStatePatch): void {
    if (this.closed) return;
    this.pending = coalesceCcrWorkerStatePatches(this.pending || {}, patch);
    if (!this.drainTask) {
      this.drainTask = this.drain().finally(() => {
        this.drainTask = undefined;
      });
    }
  }

  async flush(): Promise<void> {
    await this.drainTask;
  }

  close(): void {
    if (this.closed) return;
    this.closed = true;
    this.pending = undefined;
    this.releaseCloseWaiters();
  }

  private async drain(): Promise<void> {
    while (this.pending && !this.closed) {
      let current = this.pending;
      this.pending = undefined;
      let failures = 0;
      while (!this.closed) {
        if (await this.send(current)) break;
        failures += 1;
        await this.waitForRetryDelay(Math.min(this.baseDelayMs * (2 ** (failures - 1)), this.maxDelayMs));
        if (this.pending) {
          current = coalesceCcrWorkerStatePatches(current, this.pending);
          this.pending = undefined;
        }
      }
    }
  }

  private async waitForRetryDelay(milliseconds: number): Promise<void> {
    if (this.closed) return;
    let closeResolver: (() => void) | undefined;
    const closePromise = new Promise<void>((resolve) => {
      closeResolver = resolve;
      this.closeWaiters.push(resolve);
    });
    try {
      await Promise.race([this.sleep(milliseconds), closePromise]);
    } finally {
      if (closeResolver) this.closeWaiters = this.closeWaiters.filter((waiter) => waiter !== closeResolver);
    }
  }

  private releaseCloseWaiters(): void {
    const waiters = [...this.closeWaiters];
    this.closeWaiters = [];
    for (const waiter of waiters) waiter();
  }
}

export function coalesceCcrWorkerStatePatches(
  base: SdkCcrWorkerStatePatch,
  overlay: SdkCcrWorkerStatePatch
): SdkCcrWorkerStatePatch {
  const merged = { ...base };
  for (const [key, value] of Object.entries(overlay)) {
    if (
      ["external_metadata", "internal_metadata"].includes(key)
      && isRecord(merged[key])
      && isRecord(value)
    ) {
      merged[key] = { ...merged[key], ...value };
      continue;
    }
    merged[key] = value;
  }
  return merged;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export const SDKWorkerStateUploader = SdkCcrWorkerStateUploader;
export type SDKWorkerStateUploader = SdkCcrWorkerStateUploader;
export const coalesce_worker_state_patches = coalesceCcrWorkerStatePatches;
