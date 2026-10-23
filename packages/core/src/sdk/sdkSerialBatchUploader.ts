export type SdkBatchSendHandler = (messages: Record<string, unknown>[]) => Promise<void>;
export type SdkBatchDropHandler = (batchSize: number, failures: number) => void;

export type SdkSerialBatchUploaderOptions = {
  maxBatchSize?: number;
  max_batch_size?: number;
  maxQueueSize?: number;
  max_queue_size?: number;
  baseDelayMs?: number;
  base_delay_seconds?: number;
  maxDelayMs?: number;
  max_delay_seconds?: number;
  send: SdkBatchSendHandler;
  maxConsecutiveFailures?: number;
  max_consecutive_failures?: number;
  onBatchDropped?: SdkBatchDropHandler;
  on_batch_dropped?: SdkBatchDropHandler;
  sleep?: (milliseconds: number) => Promise<void>;
};

export type SdkRetryableBatchErrorOptions = {
  retryAfterMs?: number;
  retryAfterSeconds?: number;
  retry_after_seconds?: number;
};

export class SdkRetryableBatchError extends Error {
  readonly retryAfterMs?: number;
  readonly retryAfterSeconds?: number;
  readonly retry_after_seconds?: number;

  constructor(message: string, retryAfter?: number | SdkRetryableBatchErrorOptions) {
    super(message);
    this.name = "SdkRetryableBatchError";
    this.retryAfterMs = retryAfterMilliseconds(retryAfter);
    this.retryAfterSeconds = retryAfterSeconds(retryAfter);
    this.retry_after_seconds = this.retryAfterSeconds;
  }
}

export class SdkSerialBatchUploader {
  private readonly maxBatchSize: number;
  private readonly maxQueueSize: number;
  private readonly baseDelayMs: number;
  private readonly maxDelayMs: number;
  private readonly send: SdkBatchSendHandler;
  private readonly maxConsecutiveFailures?: number;
  private readonly onBatchDropped?: SdkBatchDropHandler;
  private readonly sleep: (milliseconds: number) => Promise<void>;
  private pending: Record<string, unknown>[] = [];
  private drainTask?: Promise<void>;
  private closed = false;
  private backpressureWaiters: Array<() => void> = [];
  private flushWaiters: Array<() => void> = [];
  private droppedBatches = 0;

  constructor(options: SdkSerialBatchUploaderOptions) {
    this.maxBatchSize = requiredIntegerOption(options.maxBatchSize ?? options.max_batch_size, "maxBatchSize");
    this.maxQueueSize = requiredIntegerOption(options.maxQueueSize ?? options.max_queue_size, "maxQueueSize");
    this.baseDelayMs = requiredMillisecondsOption(options.baseDelayMs, options.base_delay_seconds, "baseDelayMs");
    this.maxDelayMs = requiredMillisecondsOption(options.maxDelayMs, options.max_delay_seconds, "maxDelayMs");
    this.send = options.send;
    this.maxConsecutiveFailures = options.maxConsecutiveFailures ?? options.max_consecutive_failures;
    this.onBatchDropped = options.onBatchDropped ?? options.on_batch_dropped;
    this.sleep = options.sleep || ((milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds)));
  }

  get droppedBatchCount(): number {
    return this.droppedBatches;
  }

  get dropped_batch_count(): number {
    return this.droppedBatchCount;
  }

  get pendingCount(): number {
    return this.pending.length;
  }

  get pending_count(): number {
    return this.pendingCount;
  }

  async enqueue(messages: Record<string, unknown>[]): Promise<void> {
    if (this.closed || !messages.length) return;
    while (this.pending.length + messages.length > this.maxQueueSize && !this.closed) {
      await new Promise<void>((resolve) => this.backpressureWaiters.push(resolve));
    }
    if (this.closed) return;
    this.pending.push(...messages);
    this.startDrain();
  }

  async flush(): Promise<void> {
    if (!this.pending.length && !this.drainTask) return;
    this.startDrain();
    await new Promise<void>((resolve) => this.flushWaiters.push(resolve));
  }

  close(): void {
    if (this.closed) return;
    this.closed = true;
    this.pending = [];
    this.release(this.backpressureWaiters);
    this.release(this.flushWaiters);
  }

  private startDrain(): void {
    if (this.drainTask || this.closed) return;
    this.drainTask = this.drain().finally(() => {
      this.drainTask = undefined;
      if (this.closed || !this.pending.length) this.release(this.flushWaiters);
    });
  }

  private async drain(): Promise<void> {
    let failures = 0;
    while (this.pending.length && !this.closed) {
      const batch = this.takeBatch();
      if (!batch.length) continue;
      try {
        await this.send(batch);
        failures = 0;
        this.release(this.backpressureWaiters);
      } catch (error) {
        if (this.closed) {
          this.release(this.backpressureWaiters);
          this.release(this.flushWaiters);
          break;
        }
        failures += 1;
        if (this.maxConsecutiveFailures !== undefined && failures >= this.maxConsecutiveFailures) {
          this.droppedBatches += 1;
          this.onBatchDropped?.(batch.length, failures);
          failures = 0;
          this.release(this.backpressureWaiters);
          continue;
        }
        this.pending = [...batch, ...this.pending];
        await this.sleep(this.retryDelay(failures, error));
      }
    }
  }

  private takeBatch(): Record<string, unknown>[] {
    const batch = this.pending.slice(0, this.maxBatchSize);
    this.pending.splice(0, batch.length);
    return batch;
  }

  private retryDelay(failures: number, error: unknown): number {
    if (error instanceof SdkRetryableBatchError && error.retryAfterMs !== undefined) {
      return Math.max(this.baseDelayMs, Math.min(error.retryAfterMs, this.maxDelayMs));
    }
    return Math.min(this.baseDelayMs * (2 ** (failures - 1)), this.maxDelayMs);
  }

  private release(waiters: Array<() => void>): void {
    const pending = [...waiters];
    waiters.length = 0;
    for (const waiter of pending) waiter();
  }
}

function retryAfterMilliseconds(value: number | SdkRetryableBatchErrorOptions | undefined): number | undefined {
  if (isFiniteNumber(value)) return value;
  if (!isRecord(value)) return undefined;
  if (isFiniteNumber(value.retryAfterMs)) return value.retryAfterMs;
  const seconds = retryAfterSeconds(value);
  return seconds === undefined ? undefined : seconds * 1000;
}

function retryAfterSeconds(value: number | SdkRetryableBatchErrorOptions | undefined): number | undefined {
  if (!isRecord(value)) return undefined;
  if (isFiniteNumber(value.retryAfterSeconds)) return value.retryAfterSeconds;
  if (isFiniteNumber(value.retry_after_seconds)) return value.retry_after_seconds;
  return undefined;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function requiredIntegerOption(value: unknown, name: string): number {
  if (typeof value === "number" && Number.isInteger(value) && value >= 0) return value;
  throw new TypeError(`${name} is required`);
}

function requiredMillisecondsOption(milliseconds: unknown, seconds: unknown, name: string): number {
  if (isFiniteNumber(milliseconds)) return milliseconds;
  if (isFiniteNumber(seconds)) return seconds * 1000;
  throw new TypeError(`${name} is required`);
}
