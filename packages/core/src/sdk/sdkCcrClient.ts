import { decodeJwtExpiry, extractBearerToken } from "./sdkCcrAuth.js";
import { ccrSessionIdFromUrl, normalizeCcrSessionUrl, pathWithQuery } from "./sdkCcrClientPaths.js";
import type { SdkCcrClientOptions } from "./sdkCcrClientOptions.js";
import {
  ccrClientEvent,
  ccrDeliveryUpdates,
  ccrInternalEvent,
  ccrWorkerRegisterPayload
} from "./sdkCcrClientPayloads.js";
import {
  SdkCcrStreamAccumulator,
  accumulateCcrStreamEvents,
  clearCcrStreamAccumulatorForMessage
} from "./sdkCcrStream.js";
import {
  SdkCcrAuthFailureError,
  SdkCcrEpochMismatchError,
  SdkCcrInitError,
  ccrGetBaseDelayMs,
  ccrGetMaxAttempts,
  ccrGetMaxDelayMs,
  ccrHeartbeatIntervalMs,
  ccrMaxConsecutiveAuthFailures,
  ccrStreamEventFlushIntervalMs,
  ccrUploadBaseDelayMs,
  ccrUploadMaxDelayMs,
  type SdkCcrDeliveryStatus,
  type SdkCcrRequestHandler,
  type SdkCcrRequestResult,
  type SdkCcrShutdownHandler,
  type SdkCcrShutdownReason
} from "./sdkCcrTypes.js";
import {
  ccrIntegerOption,
  ccrMillisecondsOption,
  ccrRetryAfterMilliseconds,
  optionalCcrMillisecondsOption
} from "./sdkCcrTiming.js";
import { SdkCcrWorkerStateUploader } from "./sdkCcrWorkerState.js";
import { SdkRetryableBatchError, SdkSerialBatchUploader } from "./sdkSerialBatchUploader.js";

export class SdkCcrClient {
  readonly sessionBaseUrl: string;
  readonly sessionId: string;
  readonly workerState: SdkCcrWorkerStateUploader;
  readonly eventUploader: SdkSerialBatchUploader;
  readonly internalEventUploader: SdkSerialBatchUploader;
  readonly deliveryUploader: SdkSerialBatchUploader;
  workerEpoch = 0;
  closed = false;
  currentState?: string;
  shutdownReason?: SdkCcrShutdownReason;
  private readonly requestHandler?: SdkCcrRequestHandler;
  private readonly getAuthHeaders: () => Record<string, string>;
  private readonly getAuthToken?: () => string | undefined;
  private readonly onShutdown?: SdkCcrShutdownHandler;
  private readonly maxConsecutiveAuthFailures: number;
  private readonly heartbeatIntervalMs?: number;
  private readonly streamEventFlushIntervalMs: number;
  private readonly getBaseDelayMs: number;
  private readonly getMaxDelayMs: number;
  private readonly sleep: (milliseconds: number) => Promise<void>;
  private readonly now: () => number;
  private consecutiveAuthFailures = 0;
  private heartbeatGeneration = 0;
  private deliveryEnqueueTasks: Promise<void>[] = [];
  private streamEventBuffer: Record<string, unknown>[] = [];
  private streamEventTimer?: ReturnType<typeof setTimeout>;
  private readonly streamTextAccumulator = new SdkCcrStreamAccumulator();

  constructor(sessionUrl: string, options: SdkCcrClientOptions = {}) {
    this.sessionBaseUrl = normalizeCcrSessionUrl(sessionUrl);
    this.sessionId = ccrSessionIdFromUrl(this.sessionBaseUrl);
    this.requestHandler = options.request;
    this.getAuthHeaders = options.getAuthHeaders || options.get_auth_headers || (() => ({}));
    this.getAuthToken = options.getAuthToken || options.get_auth_token;
    this.onShutdown = options.onShutdown || options.on_shutdown;
    this.maxConsecutiveAuthFailures = ccrIntegerOption(
      options.maxConsecutiveAuthFailures ?? options.max_consecutive_auth_failures,
      ccrMaxConsecutiveAuthFailures
    );
    this.heartbeatIntervalMs = optionalCcrMillisecondsOption(
      options.heartbeatIntervalMs,
      options.heartbeat_interval_seconds,
      ccrHeartbeatIntervalMs
    );
    this.streamEventFlushIntervalMs = ccrMillisecondsOption(
      options.streamEventFlushIntervalMs,
      options.stream_event_flush_interval_seconds,
      ccrStreamEventFlushIntervalMs
    );
    this.getBaseDelayMs = ccrMillisecondsOption(options.getBaseDelayMs, options.get_base_delay_seconds, ccrGetBaseDelayMs);
    this.getMaxDelayMs = ccrMillisecondsOption(options.getMaxDelayMs, options.get_max_delay_seconds, ccrGetMaxDelayMs);
    this.sleep = options.sleep || defaultSleep;
    this.now = options.now || (() => Date.now() / 1000);
    this.workerState = new SdkCcrWorkerStateUploader((body) => this.sendWorkerState(body), { sleep: this.sleep });
    this.eventUploader = new SdkSerialBatchUploader({
      maxBatchSize: 100,
      maxQueueSize: 100000,
      baseDelayMs: ccrUploadBaseDelayMs,
      maxDelayMs: ccrUploadMaxDelayMs,
      send: (events) => this.sendClientEvents(events),
      sleep: this.sleep
    });
    this.internalEventUploader = new SdkSerialBatchUploader({
      maxBatchSize: 100,
      maxQueueSize: 200,
      baseDelayMs: ccrUploadBaseDelayMs,
      maxDelayMs: ccrUploadMaxDelayMs,
      send: (events) => this.sendInternalEvents(events),
      sleep: this.sleep
    });
    this.deliveryUploader = new SdkSerialBatchUploader({
      maxBatchSize: 64,
      maxQueueSize: 64,
      baseDelayMs: ccrUploadBaseDelayMs,
      maxDelayMs: ccrUploadMaxDelayMs,
      send: (updates) => this.sendDeliveryUpdates(updates),
      sleep: this.sleep
    });
    const setTransportEventHandler = options.transport?.setOnEvent || options.transport?.set_on_event;
    setTransportEventHandler?.((event) => {
      const eventId = event.event_id;
      if (typeof eventId === "string") this.reportDelivery(eventId, "received");
    });
  }

  get internalEventsPending(): number {
    return this.internalEventUploader.pendingCount;
  }

  get session_base_url(): string {
    return this.sessionBaseUrl;
  }

  get session_id(): string {
    return this.sessionId;
  }

  get worker_state(): SdkCcrWorkerStateUploader {
    return this.workerState;
  }

  get event_uploader(): SdkSerialBatchUploader {
    return this.eventUploader;
  }

  get internal_event_uploader(): SdkSerialBatchUploader {
    return this.internalEventUploader;
  }

  get delivery_uploader(): SdkSerialBatchUploader {
    return this.deliveryUploader;
  }

  get worker_epoch(): number {
    return this.workerEpoch;
  }

  set worker_epoch(value: number) {
    this.workerEpoch = value;
  }

  get current_state(): string | undefined {
    return this.currentState;
  }

  set current_state(value: string | undefined) {
    this.currentState = value;
  }

  get shutdown_reason(): SdkCcrShutdownReason | undefined {
    return this.shutdownReason;
  }

  set shutdown_reason(value: SdkCcrShutdownReason | undefined) {
    this.shutdownReason = value;
  }

  get internal_events_pending(): number {
    return this.internalEventsPending;
  }

  async initialize(epoch: number): Promise<Record<string, unknown> | undefined> {
    if (!Object.keys(this.getAuthHeaders()).length) throw new SdkCcrInitError("no_auth_headers");
    this.workerEpoch = Math.trunc(epoch);
    const restoredWorkerState = Promise.resolve().then(() => this.getWorkerState());
    try {
      const result = await this.request("put", "/worker", ccrWorkerRegisterPayload(this.workerEpoch));
      if (!result.ok) throw new SdkCcrInitError("worker_register_failed");
      this.currentState = "idle";
      this.startHeartbeat();
      return await restoredWorkerState;
    } catch (error) {
      void restoredWorkerState.catch(() => undefined);
      throw error;
    }
  }

  reportState(state: string, details?: Record<string, unknown>): void {
    if (state === this.currentState && !details) return;
    this.currentState = state;
    this.workerState.enqueue({
      worker_status: state,
      requires_action_details: details || null
    });
  }

  reportMetadata(metadata: Record<string, unknown>): void {
    this.workerState.enqueue({ external_metadata: { ...metadata } });
  }

  reportDelivery(eventId: string, status: SdkCcrDeliveryStatus): void {
    this.deliveryEnqueueTasks.push(this.deliveryUploader.enqueue([{ eventId, status }]));
  }

  async writeEvent(message: Record<string, unknown>): Promise<void> {
    if (message.type === "stream_event") {
      this.streamEventBuffer.push({ ...message });
      if (!this.streamEventTimer) this.streamEventTimer = setTimeout(() => void this.flushStreamEventsLater(), this.streamEventFlushIntervalMs);
      return;
    }
    await this.flushStreamEventBuffer();
    if (message.type === "assistant" || message.type === "assistant_message") {
      clearCcrStreamAccumulatorForMessage(this.streamTextAccumulator, message);
    }
    await this.eventUploader.enqueue([ccrClientEvent(message)]);
  }

  async writeInternalEvent(
    eventType: string,
    payload: Record<string, unknown>,
    options: { isCompaction?: boolean; agentId?: string } = {}
  ): Promise<void> {
    await this.internalEventUploader.enqueue([ccrInternalEvent(eventType, payload, options)]);
  }

  async flush(): Promise<void> {
    await this.flushStreamEventBuffer();
    await this.eventUploader.flush();
  }

  flushInternalEvents(): Promise<void> {
    return this.internalEventUploader.flush();
  }

  async flushDelivery(): Promise<void> {
    const tasks = this.deliveryEnqueueTasks;
    this.deliveryEnqueueTasks = [];
    await Promise.all(tasks);
    await this.deliveryUploader.flush();
  }

  flushWorkerState(): Promise<void> {
    return this.workerState.flush();
  }

  async getWorkerState(): Promise<Record<string, unknown> | undefined> {
    const result = await this.getWithRetry("/worker");
    const worker = recordValue(result?.worker);
    const metadata = recordValue(worker?.external_metadata);
    return metadata ? { ...metadata } : undefined;
  }

  readInternalEvents(): Promise<Record<string, unknown>[] | undefined> {
    return this.paginatedGet("/worker/internal-events");
  }

  readSubagentInternalEvents(): Promise<Record<string, unknown>[] | undefined> {
    return this.paginatedGet("/worker/internal-events", { subagents: "true" });
  }

  async close(): Promise<void> {
    this.closed = true;
    this.stopHeartbeat();
    if (this.streamEventTimer) {
      clearTimeout(this.streamEventTimer);
      this.streamEventTimer = undefined;
    }
    this.streamEventBuffer = [];
    this.workerState.close();
    this.eventUploader.close();
    this.internalEventUploader.close();
    this.deliveryUploader.close();
    this.deliveryEnqueueTasks = [];
  }

  private async sendWorkerState(body: Record<string, unknown>): Promise<boolean> {
    const result = await this.request("put", "/worker", { worker_epoch: this.workerEpoch, ...body });
    return result.ok;
  }

  private async sendClientEvents(events: Record<string, unknown>[]): Promise<void> {
    const result = await this.request("post", "/worker/events", {
      worker_epoch: this.workerEpoch,
      events
    });
    if (!result.ok) throw new SdkRetryableBatchError("client event POST failed", ccrRetryAfterMilliseconds(result));
  }

  private async sendInternalEvents(events: Record<string, unknown>[]): Promise<void> {
    const result = await this.request("post", "/worker/internal-events", {
      worker_epoch: this.workerEpoch,
      events
    });
    if (!result.ok) throw new SdkRetryableBatchError("internal event POST failed", ccrRetryAfterMilliseconds(result));
  }

  private async sendDeliveryUpdates(updates: Record<string, unknown>[]): Promise<void> {
    const result = await this.request("post", "/worker/events/delivery", {
      worker_epoch: this.workerEpoch,
      updates: ccrDeliveryUpdates(updates)
    });
    if (!result.ok) throw new SdkRetryableBatchError("delivery POST failed", ccrRetryAfterMilliseconds(result));
  }

  private startHeartbeat(): void {
    if (this.heartbeatIntervalMs === undefined || this.heartbeatIntervalMs <= 0) return;
    const generation = ++this.heartbeatGeneration;
    void this.heartbeatLoop(generation);
  }

  private stopHeartbeat(): void {
    this.heartbeatGeneration += 1;
  }

  private async heartbeatLoop(generation: number): Promise<void> {
    while (!this.closed && generation === this.heartbeatGeneration) {
      await this.sleep(this.heartbeatIntervalMs || 0);
      if (!this.closed && generation === this.heartbeatGeneration) {
        await this.request("post", "/worker/heartbeat", {
          session_id: this.sessionId,
          worker_epoch: this.workerEpoch
        });
      }
    }
  }

  private async flushStreamEventsLater(): Promise<void> {
    this.streamEventTimer = undefined;
    await this.flushStreamEventBuffer({ cancelTimer: false });
  }

  private async flushStreamEventBuffer(options: { cancelTimer?: boolean } = {}): Promise<void> {
    if (options.cancelTimer !== false && this.streamEventTimer) {
      clearTimeout(this.streamEventTimer);
      this.streamEventTimer = undefined;
    }
    if (!this.streamEventBuffer.length) return;
    const buffered = this.streamEventBuffer;
    this.streamEventBuffer = [];
    const payloads = accumulateCcrStreamEvents(buffered, this.streamTextAccumulator);
    await this.eventUploader.enqueue(payloads.map((payload) => ({ ...ccrClientEvent(payload), ephemeral: true })));
  }

  private async request(
    method: string,
    path: string,
    body?: Record<string, unknown>
  ): Promise<SdkCcrRequestResult> {
    const headers = { ...this.getAuthHeaders() };
    if (!Object.keys(headers).length) return { ok: false };
    if (this.requestHandler) {
      const result = await this.requestHandler(method, path, headers, body);
      await this.handleStatus(result.status, headers);
      if (result.ok) this.consecutiveAuthFailures = 0;
      return result;
    }
    const response = await fetch(`${this.sessionBaseUrl}${path}`, {
      method: method.toUpperCase(),
      headers: {
        ...headers,
        ...(body ? { "Content-Type": "application/json" } : {})
      },
      ...(body ? { body: JSON.stringify(body) } : {})
    });
    await this.handleStatus(response.status, headers);
    const retryAfter = response.headers.get("retry-after");
    const retryAfterMs = retryAfter ? Number(retryAfter) * 1000 : undefined;
    return {
      ok: response.status >= 200 && response.status < 300,
      status: response.status,
      data: await parseCcrResponseData(response),
      retryAfterMs
    };
  }

  private async handleStatus(status: number | undefined, headers: Record<string, string>): Promise<void> {
    if (status === undefined) return;
    if (status >= 200 && status < 300) {
      this.consecutiveAuthFailures = 0;
      return;
    }
    if (status === 409) {
      await this.triggerShutdown("epoch_mismatch");
      throw new SdkCcrEpochMismatchError();
    }
    if (![401, 403].includes(status)) return;
    const token = this.getAuthToken?.() || extractBearerToken(headers);
    const expiry = decodeJwtExpiry(token);
    if (expiry !== undefined && expiry < this.now()) {
      await this.triggerShutdown("auth_expired");
      throw new SdkCcrAuthFailureError("auth_expired", "CCR auth token expired without refresh");
    }
    this.consecutiveAuthFailures += 1;
    if (this.consecutiveAuthFailures >= this.maxConsecutiveAuthFailures) {
      await this.triggerShutdown("auth_failures_exhausted");
      throw new SdkCcrAuthFailureError("auth_failures_exhausted", "CCR auth failures exhausted");
    }
  }

  private async triggerShutdown(reason: SdkCcrShutdownReason): Promise<void> {
    this.shutdownReason ??= reason;
    this.closeUploadQueues();
    await this.onShutdown?.(reason);
  }

  private closeUploadQueues(): void {
    this.closed = true;
    this.workerState.close();
    this.eventUploader.close();
    this.internalEventUploader.close();
    this.deliveryUploader.close();
    this.deliveryEnqueueTasks = [];
  }

  private async paginatedGet(
    path: string,
    params: Record<string, string> = {}
  ): Promise<Record<string, unknown>[] | undefined> {
    const allEvents: Record<string, unknown>[] = [];
    let cursor: string | undefined;
    while (true) {
      const page = await this.getWithRetry(pathWithQuery(path, params, cursor));
      if (!page) return undefined;
      const data = Array.isArray(page.data) ? page.data : [];
      allEvents.push(...data.filter(recordValue));
      cursor = typeof page.next_cursor === "string" && page.next_cursor ? page.next_cursor : undefined;
      if (!cursor) return allEvents;
    }
  }

  private async getWithRetry(path: string): Promise<Record<string, unknown> | undefined> {
    if (!Object.keys(this.getAuthHeaders()).length) return undefined;
    for (let attempt = 1; attempt <= ccrGetMaxAttempts; attempt += 1) {
      try {
        const result = await this.request("get", path);
        if (result.ok) return recordValue(result.data);
      } catch (error) {
        if (error instanceof SdkCcrEpochMismatchError || error instanceof SdkCcrAuthFailureError) throw error;
      }
      if (attempt < ccrGetMaxAttempts) {
        await this.sleep(Math.min(this.getBaseDelayMs * (2 ** (attempt - 1)), this.getMaxDelayMs));
      }
    }
    return undefined;
  }
}

function recordValue(value: unknown): Record<string, unknown> | undefined {
  return typeof value === "object" && value !== null && !Array.isArray(value) ? value as Record<string, unknown> : undefined;
}

export const SDKCCRClient = SdkCcrClient;
export type SDKCCRClient = SdkCcrClient;

function defaultSleep(milliseconds: number): Promise<void> {
  return new Promise((resolve) => {
    const timeout = setTimeout(resolve, milliseconds);
    timeout.unref?.();
  });
}

async function parseCcrResponseData(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text.trim()) return undefined;
  const contentType = response.headers.get("content-type") || "";
  if (contentType.toLowerCase().includes("json") || looksLikeJson(text)) {
    return JSON.parse(text);
  }
  return undefined;
}

function looksLikeJson(text: string): boolean {
  const trimmed = text.trimStart();
  return trimmed.startsWith("{") || trimmed.startsWith("[");
}
