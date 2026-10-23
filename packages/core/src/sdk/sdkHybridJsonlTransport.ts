import type { SdkJsonlTransport } from "./sdkJsonlTransport.js";
import {
  SdkRetryableBatchError,
  SdkSerialBatchUploader,
  type SdkBatchDropHandler
} from "./sdkSerialBatchUploader.js";
import { formatSdkTransportUrl, parseSdkTransportUrl } from "./sdkTransportUrls.js";
import { SdkWebSocketJsonlTransport } from "./sdkWebSocketJsonlTransport.js";

export type SdkHybridPostHandler = (
  url: string,
  headers: Record<string, string>,
  body: Record<string, unknown>
) => Promise<number>;

export type SdkHybridJsonlTransportOptions = {
  headers?: Record<string, string>;
  refreshHeaders?: () => Record<string, string>;
  refresh_headers?: () => Record<string, string>;
  reader?: SdkJsonlTransport;
  postUrl?: string;
  post_url?: string;
  postMessage?: SdkHybridPostHandler;
  post_message?: SdkHybridPostHandler;
  streamEventFlushIntervalMs?: number;
  stream_event_flush_interval_seconds?: number;
  maxBatchSize?: number;
  max_batch_size?: number;
  maxQueueSize?: number;
  max_queue_size?: number;
  postBaseDelayMs?: number;
  post_base_delay_seconds?: number;
  postMaxDelayMs?: number;
  post_max_delay_seconds?: number;
  maxConsecutiveFailures?: number;
  max_consecutive_failures?: number;
  onBatchDropped?: SdkBatchDropHandler;
  on_batch_dropped?: SdkBatchDropHandler;
  sleep?: (milliseconds: number) => Promise<void>;
  closeGraceMs?: number;
  close_grace_seconds?: number;
};

const hybridBatchFlushIntervalMs = 100;
const hybridCloseGraceMs = 3000;
const hybridPostBaseDelayMs = 500;
const hybridPostMaxDelayMs = 8000;
const hybridPostMaxBatchSize = 500;
const hybridPostMaxQueueSize = 100000;

export class SdkHybridJsonlTransport implements SdkJsonlTransport {
  private readonly headers: Record<string, string>;
  private readonly refreshHeaders?: () => Record<string, string>;
  readonly postUrl: string;
  private readonly postMessage?: SdkHybridPostHandler;
  readonly streamEventFlushIntervalMs: number;
  readonly closeGraceMs: number;
  private readonly reader: SdkJsonlTransport;
  private readonly uploader: SdkSerialBatchUploader;
  private readonly sleep: (milliseconds: number) => Promise<void>;
  private streamEventBuffer: Record<string, unknown>[] = [];
  private streamEventTimer?: ReturnType<typeof setTimeout>;
  closed = false;

  constructor(readonly url: string, options: SdkHybridJsonlTransportOptions = {}) {
    this.headers = { ...(options.headers || {}) };
    this.refreshHeaders = options.refreshHeaders || options.refresh_headers;
    this.postUrl = options.postUrl || options.post_url || deriveHybridPostUrl(url);
    this.postMessage = options.postMessage || options.post_message;
    this.streamEventFlushIntervalMs = millisecondsOption(
      options.streamEventFlushIntervalMs,
      options.stream_event_flush_interval_seconds,
      hybridBatchFlushIntervalMs
    );
    this.closeGraceMs = millisecondsOption(options.closeGraceMs, options.close_grace_seconds, hybridCloseGraceMs);
    this.reader = options.reader || new SdkWebSocketJsonlTransport(url, { headers: this.headers });
    this.sleep = options.sleep || ((milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds)));
    this.uploader = new SdkSerialBatchUploader({
      maxBatchSize: integerOption(options.maxBatchSize ?? options.max_batch_size, hybridPostMaxBatchSize),
      maxQueueSize: integerOption(options.maxQueueSize ?? options.max_queue_size, hybridPostMaxQueueSize),
      baseDelayMs: millisecondsOption(options.postBaseDelayMs, options.post_base_delay_seconds, hybridPostBaseDelayMs),
      maxDelayMs: millisecondsOption(options.postMaxDelayMs, options.post_max_delay_seconds, hybridPostMaxDelayMs),
      send: (messages) => this.postOnce(messages),
      maxConsecutiveFailures: optionalIntegerOption(options.maxConsecutiveFailures ?? options.max_consecutive_failures),
      onBatchDropped: options.onBatchDropped || options.on_batch_dropped,
      sleep: this.sleep
    });
  }

  get droppedBatchCount(): number {
    return this.uploader.droppedBatchCount;
  }

  get dropped_batch_count(): number {
    return this.droppedBatchCount;
  }

  get post_url(): string {
    return this.postUrl;
  }

  get stream_event_flush_interval_seconds(): number {
    return this.streamEventFlushIntervalMs / 1000;
  }

  get close_grace_seconds(): number {
    return this.closeGraceMs / 1000;
  }

  read(): Promise<string | Uint8Array | undefined> {
    return this.reader.read();
  }

  async write(data: string): Promise<void> {
    for (const line of data.split(/\r?\n/)) {
      if (!line.trim()) continue;
      const message = JSON.parse(line) as unknown;
      if (isRecord(message)) await this.writeMessage(message);
    }
  }

  async writeBatch(messages: Record<string, unknown>[]): Promise<void> {
    await this.uploader.enqueue([...this.takeStreamEvents(), ...messages]);
    await this.uploader.flush();
  }

  write_batch(messages: Record<string, unknown>[]): Promise<void> {
    return this.writeBatch(messages);
  }

  async flush(): Promise<void> {
    await this.uploader.enqueue(this.takeStreamEvents());
    await this.uploader.flush();
  }

  async close(): Promise<void> {
    this.closed = true;
    await this.uploader.enqueue(this.takeStreamEvents());
    if (this.closeGraceMs > 0) {
      await waitForCloseGrace(this.uploader.flush(), this.closeGraceMs);
    } else {
      await this.uploader.flush();
    }
    this.uploader.close();
    await this.reader.close();
  }

  private async writeMessage(message: Record<string, unknown>): Promise<void> {
    if (message.type === "stream_event") {
      this.streamEventBuffer.push(message);
      if (!this.streamEventTimer) this.streamEventTimer = setTimeout(() => void this.flushStreamEventsLater(), this.streamEventFlushIntervalMs);
      return;
    }
    await this.uploader.enqueue([...this.takeStreamEvents(), message]);
    await this.uploader.flush();
  }

  private async flushStreamEventsLater(): Promise<void> {
    this.streamEventTimer = undefined;
    await this.uploader.enqueue(this.takeStreamEvents({ cancelTimer: false }));
  }

  private takeStreamEvents(options: { cancelTimer?: boolean } = {}): Record<string, unknown>[] {
    if (options.cancelTimer !== false && this.streamEventTimer) {
      clearTimeout(this.streamEventTimer);
      this.streamEventTimer = undefined;
    }
    const buffered = this.streamEventBuffer;
    this.streamEventBuffer = [];
    return buffered;
  }

  private async postOnce(events: Record<string, unknown>[]): Promise<void> {
    if (!events.length) return;
    const status = await this.sendPost(this.postUrl, this.postHeaders(), { events });
    if (status >= 200 && status < 300) return;
    if (status >= 400 && status < 500 && status !== 429) return;
    throw new SdkRetryableBatchError(`Hybrid POST failed with ${status}`);
  }

  private async sendPost(url: string, headers: Record<string, string>, body: Record<string, unknown>): Promise<number> {
    if (this.postMessage) return this.postMessage(url, headers, body);
    const response = await fetch(url, {
      method: "POST",
      headers,
      body: JSON.stringify(body)
    });
    return response.status;
  }

  private postHeaders(): Record<string, string> {
    return {
      ...this.headers,
      ...(this.refreshHeaders?.() || {}),
      "Content-Type": "application/json"
    };
  }
}

export function deriveHybridPostUrl(webSocketUrl: string): string {
  const postUrl = parseSdkTransportUrl(webSocketUrl);
  if (postUrl.scheme === "wss:") postUrl.scheme = "https:";
  if (postUrl.scheme === "ws:") postUrl.scheme = "http:";
  postUrl.path = postUrl.path.replace("/ws/", "/session/");
  if (!postUrl.path.endsWith("/events")) postUrl.path = `${postUrl.path.replace(/\/+$/, "")}/events`;
  return formatSdkTransportUrl(postUrl);
}

export const derive_hybrid_post_url = deriveHybridPostUrl;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function integerOption(value: unknown, fallback: number): number {
  if (typeof value === "number" && Number.isInteger(value) && value >= 0) return value;
  return fallback;
}

function optionalIntegerOption(value: unknown): number | undefined {
  return typeof value === "number" && Number.isInteger(value) && value >= 0 ? value : undefined;
}

function millisecondsOption(milliseconds: unknown, seconds: unknown, fallback: number): number {
  if (typeof milliseconds === "number" && Number.isFinite(milliseconds)) return milliseconds;
  if (typeof seconds === "number" && Number.isFinite(seconds)) return seconds * 1000;
  return fallback;
}

async function waitForCloseGrace(flush: Promise<void>, graceMs: number): Promise<void> {
  let timeout: ReturnType<typeof setTimeout> | undefined;
  try {
    await Promise.race([
      flush,
      new Promise<void>((resolve) => {
        timeout = setTimeout(resolve, graceMs);
      })
    ]);
  } finally {
    if (timeout) clearTimeout(timeout);
  }
}
