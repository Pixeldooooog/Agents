import { ndjsonSafeStringify, type SdkJsonlChunk } from "./sdkJsonl.js";
import { SdkMessageQueue } from "./sdkMessageQueue.js";
import { deriveSsePostUrl, parseSseFrames, withSseFromSequenceParam, type SdkSseFrame } from "./sdkSseFrames.js";
import type { SdkJsonlTransport } from "./sdkJsonlTransport.js";

export type SdkSsePostHandler = (
  url: string,
  headers: Record<string, string>,
  message: Record<string, unknown>
) => Promise<number>;

export type SdkSseReadChunksFactory = (
  url: string,
  headers: Record<string, string>
) => AsyncIterable<SdkJsonlChunk>;

export type SdkSseCloseHandler = (closeCode: number | undefined) => void;

export type SdkSseJsonlTransportOptions = {
  headers?: Record<string, string>;
  sessionId?: string;
  session_id?: string;
  refreshHeaders?: () => Record<string, string>;
  refresh_headers?: () => Record<string, string>;
  initialSequenceNumber?: number;
  initial_sequence_num?: number;
  postUrl?: string;
  post_url?: string;
  readChunks?: AsyncIterable<SdkJsonlChunk>;
  read_chunks?: AsyncIterable<SdkJsonlChunk>;
  readChunksFactory?: SdkSseReadChunksFactory;
  read_chunks_factory?: SdkSseReadChunksFactory;
  postMessage?: SdkSsePostHandler;
  post_message?: SdkSsePostHandler;
  postMaxRetries?: number;
  post_max_retries?: number;
  postBaseDelayMs?: number;
  post_base_delay_seconds?: number;
  postMaxDelayMs?: number;
  post_max_delay_seconds?: number;
  reconnect?: boolean;
  reconnectBaseDelayMs?: number;
  reconnect_base_delay_seconds?: number;
  reconnectMaxDelayMs?: number;
  reconnect_max_delay_seconds?: number;
  reconnectGiveUpMs?: number;
  reconnect_give_up_seconds?: number;
  livenessTimeoutMs?: number | null;
  liveness_timeout_seconds?: number | null;
  sleep?: (milliseconds: number) => Promise<void>;
  now?: () => number;
  monotonic?: () => number;
};

const ssePostMaxRetries = 10;
const ssePostBaseDelayMs = 500;
const ssePostMaxDelayMs = 8000;
const sseReconnectBaseDelayMs = 1000;
const sseReconnectMaxDelayMs = 30000;
const sseReconnectGiveUpMs = 600000;
const sseLivenessTimeoutMs = 45000;
const ssePermanentStatusCodes = new Set([401, 403, 404]);
const ssePostSuccessStatusCodes = new Set([200, 201]);

export class SdkSseLivenessTimeoutError extends Error {
  constructor(message = "SSE liveness timeout") {
    super(message);
    this.name = "SdkSseLivenessTimeoutError";
  }
}

export class SdkSseJsonlTransport implements SdkJsonlTransport {
  readonly headers: Record<string, string>;
  readonly sessionId?: string;
  readonly refreshHeaders?: () => Record<string, string>;
  readonly postUrl: string;
  private readonly readChunksFactory?: SdkSseReadChunksFactory;
  private readonly postMessage?: SdkSsePostHandler;
  readonly postMaxRetries: number;
  readonly postBaseDelayMs: number;
  readonly postMaxDelayMs: number;
  private readonly reconnectEnabled: boolean;
  private readonly reconnectBaseDelayMs: number;
  private readonly reconnectMaxDelayMs: number;
  private readonly reconnectGiveUpMs: number;
  private readonly livenessTimeoutMs?: number;
  private readonly sleep: (milliseconds: number) => Promise<void>;
  private readonly now: () => number;
  private readonly inbound = new SdkMessageQueue<string>();
  private readChunks?: AsyncIterable<SdkJsonlChunk>;
  private readerTask?: Promise<void>;
  private buffer = "";
  private seenSequenceNumbers = new Set<number>();
  private lastSequenceNumber: number;
  private onEvent?: (event: Record<string, unknown>) => void;
  private onClose?: SdkSseCloseHandler;
  private reconnectAttempts = 0;
  private reconnectStartedAt?: number;
  private activeAbortController?: AbortController;
  state: "idle" | "connected" | "reconnecting" | "closing" | "closed" = "idle";
  closed = false;

  constructor(readonly url: string, options: SdkSseJsonlTransportOptions = {}) {
    this.headers = { ...(options.headers || {}) };
    this.sessionId = options.sessionId ?? options.session_id;
    this.refreshHeaders = options.refreshHeaders || options.refresh_headers;
    this.postUrl = options.postUrl || options.post_url || deriveSsePostUrl(url);
    this.readChunks = options.readChunks || options.read_chunks;
    this.readChunksFactory = options.readChunksFactory || options.read_chunks_factory;
    this.postMessage = options.postMessage || options.post_message;
    this.postMaxRetries = numberOption(options.postMaxRetries ?? options.post_max_retries, ssePostMaxRetries);
    this.postBaseDelayMs = millisecondsOption(options.postBaseDelayMs, options.post_base_delay_seconds, ssePostBaseDelayMs);
    this.postMaxDelayMs = millisecondsOption(options.postMaxDelayMs, options.post_max_delay_seconds, ssePostMaxDelayMs);
    this.reconnectEnabled = options.reconnect ?? (this.readChunks === undefined || this.readChunksFactory !== undefined);
    this.reconnectBaseDelayMs = millisecondsOption(options.reconnectBaseDelayMs, options.reconnect_base_delay_seconds, sseReconnectBaseDelayMs);
    this.reconnectMaxDelayMs = millisecondsOption(options.reconnectMaxDelayMs, options.reconnect_max_delay_seconds, sseReconnectMaxDelayMs);
    this.reconnectGiveUpMs = millisecondsOption(options.reconnectGiveUpMs, options.reconnect_give_up_seconds, sseReconnectGiveUpMs);
    this.livenessTimeoutMs = optionalMillisecondsOption(options.livenessTimeoutMs, options.liveness_timeout_seconds, sseLivenessTimeoutMs);
    this.sleep = options.sleep || ((milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds)));
    this.now = options.now || (options.monotonic ? () => options.monotonic!() * 1000 : Date.now);
    this.lastSequenceNumber = Math.max(numberOption(options.initialSequenceNumber ?? options.initial_sequence_num, 0), 0);
  }

  get lastSequenceNum(): number {
    return this.lastSequenceNumber;
  }

  get last_sequence_num(): number {
    return this.lastSequenceNum;
  }

  get session_id(): string | undefined {
    return this.sessionId;
  }

  get refresh_headers(): (() => Record<string, string>) | undefined {
    return this.refreshHeaders;
  }

  get post_url(): string {
    return this.postUrl;
  }

  get post_max_retries(): number {
    return this.postMaxRetries;
  }

  get post_base_delay_seconds(): number {
    return this.postBaseDelayMs / 1000;
  }

  get post_max_delay_seconds(): number {
    return this.postMaxDelayMs / 1000;
  }

  getLastSequenceNum(): number {
    return this.lastSequenceNumber;
  }

  get_last_sequence_num(): number {
    return this.getLastSequenceNum();
  }

  setOnEvent(handler: ((event: Record<string, unknown>) => void) | undefined): void {
    this.onEvent = handler;
  }

  set_on_event(handler: ((event: Record<string, unknown>) => void) | undefined): void {
    this.setOnEvent(handler);
  }

  setOnClose(handler: SdkSseCloseHandler | undefined): void {
    this.onClose = handler;
  }

  set_on_close(handler: SdkSseCloseHandler | undefined): void {
    this.setOnClose(handler);
  }

  isConnectedStatus(): boolean {
    return this.state === "connected";
  }

  is_connected_status(): boolean {
    return this.isConnectedStatus();
  }

  isClosedStatus(): boolean {
    return this.state === "closed";
  }

  is_closed_status(): boolean {
    return this.isClosedStatus();
  }

  read(): Promise<string | undefined> {
    if (this.closed && this.state === "closed") return this.inbound.shift();
    this.startReader();
    return this.inbound.shift();
  }

  async write(data: string): Promise<void> {
    for (const line of data.split(/\r?\n/)) {
      if (!line.trim()) continue;
      const value = JSON.parse(line) as unknown;
      if (isRecord(value)) await this.postWithRetry(value);
    }
  }

  async close(): Promise<void> {
    if (this.closed && this.state === "closed") return;
    this.closed = true;
    this.state = "closing";
    this.activeAbortController?.abort();
    this.inbound.close();
    await this.readerTask?.catch(() => undefined);
    this.state = "closed";
  }

  private startReader(): void {
    if (this.readerTask || this.closed) return;
    this.readerTask = this.pumpReadConnections();
  }

  private async pumpReadConnections(): Promise<void> {
    try {
      while (!this.closed) {
        try {
          await this.readOneConnection();
        } catch {
          if (!await this.prepareReconnect()) break;
          continue;
        }
        if (this.closed || !await this.prepareReconnect()) break;
      }
    } finally {
      this.closed = true;
      if (this.state !== "closing") this.state = "closed";
      this.inbound.close();
    }
  }

  private async readOneConnection(): Promise<void> {
    this.state = "reconnecting";
    this.buffer = "";
    this.state = "connected";
    let sawChunk = false;
    for await (const chunk of this.iterReadChunks()) {
      if (!sawChunk) {
        this.reconnectAttempts = 0;
        this.reconnectStartedAt = undefined;
        sawChunk = true;
      }
      this.buffer += chunkToText(chunk);
      const parsed = parseSseFrames(this.buffer);
      this.buffer = parsed.rest;
      for (const frame of parsed.frames) {
        this.trackFrameId(frame);
        const payload = this.clientEventPayload(frame);
        if (payload) this.inbound.push(`${ndjsonSafeStringify(payload)}\n`);
      }
    }
  }

  private async *iterReadChunks(): AsyncIterable<SdkJsonlChunk> {
    const chunks = this.readChunksFactory
      ? this.readChunksFactory(this.streamUrl(), this.sseHeaders())
      : this.readChunks ?? this.iterHttpReadChunks();
    this.readChunks = undefined;
    for await (const chunk of this.iterChunksWithLiveness(chunks)) yield chunk;
  }

  private async *iterHttpReadChunks(): AsyncIterable<Uint8Array> {
    const abortController = new AbortController();
    this.activeAbortController = abortController;
    const response = await fetch(this.streamUrl(), { headers: this.sseHeaders(), signal: abortController.signal });
    if (ssePermanentStatusCodes.has(response.status)) {
      this.closed = true;
      this.notifyClose(response.status);
      return;
    }
    if (!response.ok) throw new Error(`SSE stream failed with HTTP ${response.status}`);
    if (!response.body) return;
    const reader = response.body.getReader();
    try {
      while (!this.closed) {
        const { value, done } = await reader.read();
        if (done) return;
        if (value) yield value;
      }
    } finally {
      reader.releaseLock();
      if (this.activeAbortController === abortController) this.activeAbortController = undefined;
    }
  }

  private async *iterChunksWithLiveness(chunks: AsyncIterable<SdkJsonlChunk>): AsyncIterable<SdkJsonlChunk> {
    const iterator = chunks[Symbol.asyncIterator]();
    while (!this.closed) {
      const next = this.livenessTimeoutMs === undefined || this.livenessTimeoutMs <= 0
        ? iterator.next()
        : withTimeout(iterator.next(), this.livenessTimeoutMs);
      const result = await next;
      if (result.done) return;
      yield result.value;
    }
  }

  private async prepareReconnect(): Promise<boolean> {
    if (this.closed || !this.reconnectEnabled) return false;
    this.state = "reconnecting";
    const currentTime = this.now();
    this.reconnectStartedAt ??= currentTime;
    if (currentTime - this.reconnectStartedAt >= this.reconnectGiveUpMs) {
      this.closed = true;
      this.state = "closed";
      this.notifyClose(undefined);
      return false;
    }
    this.reconnectAttempts += 1;
    const delay = Math.min(
      this.reconnectBaseDelayMs * (2 ** (this.reconnectAttempts - 1)),
      this.reconnectMaxDelayMs
    );
    if (delay > 0) await this.sleep(delay);
    return !this.closed;
  }

  private trackFrameId(frame: SdkSseFrame): void {
    if (!frame.id) return;
    const sequenceNumber = Number(frame.id);
    if (!Number.isInteger(sequenceNumber)) return;
    this.seenSequenceNumbers.add(sequenceNumber);
    if (this.seenSequenceNumbers.size > 1000) {
      const threshold = this.lastSequenceNumber - 200;
      this.seenSequenceNumbers = new Set([...this.seenSequenceNumbers].filter((value) => value >= threshold));
    }
    if (sequenceNumber > this.lastSequenceNumber) this.lastSequenceNumber = sequenceNumber;
  }

  private clientEventPayload(frame: SdkSseFrame): Record<string, unknown> | undefined {
    if (frame.event !== "client_event" || !frame.data) return undefined;
    let event: unknown;
    try {
      event = JSON.parse(frame.data);
    } catch {
      return undefined;
    }
    if (!isRecord(event)) return undefined;
    const payload = event.payload;
    if (!isRecord(payload) || typeof payload.type !== "string") return undefined;
    this.onEvent?.(event);
    return payload;
  }

  private async postWithRetry(message: Record<string, unknown>): Promise<void> {
    const headers = this.postHeaders();
    for (let attempt = 1; attempt <= this.postMaxRetries; attempt += 1) {
      const status = await this.sendPost(this.postUrl, headers, message).catch(() => undefined);
      if (status && ssePostSuccessStatusCodes.has(status)) return;
      if (status !== undefined && status >= 400 && status < 500 && status !== 429) return;
      if (attempt === this.postMaxRetries) return;
      const delay = Math.min(this.postBaseDelayMs * (2 ** (attempt - 1)), this.postMaxDelayMs);
      if (delay > 0) await this.sleep(delay);
    }
  }

  private async sendPost(url: string, headers: Record<string, string>, message: Record<string, unknown>): Promise<number> {
    if (this.postMessage) return this.postMessage(url, headers, message);
    const response = await fetch(url, {
      method: "POST",
      headers,
      body: JSON.stringify(message)
    });
    return response.status;
  }

  private sseHeaders(): Record<string, string> {
    const headers = this.freshHeaders();
    headers.Accept ??= "text/event-stream";
    headers["anthropic-version"] ??= "2023-06-01";
    headers["User-Agent"] ??= "agents-sdk";
    if (this.lastSequenceNumber > 0) headers["Last-Event-ID"] = String(this.lastSequenceNumber);
    return headers;
  }

  private postHeaders(): Record<string, string> {
    const headers = this.freshHeaders();
    headers["Content-Type"] ??= "application/json";
    headers["anthropic-version"] ??= "2023-06-01";
    headers["User-Agent"] ??= "agents-sdk";
    return headers;
  }

  private freshHeaders(): Record<string, string> {
    return { ...this.headers, ...(this.refreshHeaders?.() || {}) };
  }

  private streamUrl(): string {
    if (this.lastSequenceNumber <= 0) return this.url;
    return withSseFromSequenceParam(this.url, this.lastSequenceNumber);
  }

  private notifyClose(closeCode: number | undefined): void {
    this.onClose?.(closeCode);
  }
}

function chunkToText(chunk: SdkJsonlChunk): string {
  return typeof chunk === "string" ? chunk : new TextDecoder().decode(chunk);
}

function withTimeout<T>(promise: Promise<T>, timeoutMs: number): Promise<T> {
  let timeout: ReturnType<typeof setTimeout> | undefined;
  const timeoutPromise = new Promise<T>((_, reject) => {
    timeout = setTimeout(() => reject(new SdkSseLivenessTimeoutError()), timeoutMs);
  });
  return Promise.race([promise, timeoutPromise]).finally(() => {
    if (timeout) clearTimeout(timeout);
  });
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function numberOption(value: unknown, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function millisecondsOption(milliseconds: unknown, seconds: unknown, fallback: number): number {
  if (typeof milliseconds === "number" && Number.isFinite(milliseconds)) return milliseconds;
  if (typeof seconds === "number" && Number.isFinite(seconds)) return seconds * 1000;
  return fallback;
}

function optionalMillisecondsOption(milliseconds: unknown, seconds: unknown, fallback: number): number | undefined {
  if (milliseconds === null || seconds === null) return undefined;
  return millisecondsOption(milliseconds, seconds, fallback);
}
