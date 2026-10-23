import { ndjsonSafeStringify } from "./sdkJsonl.js";
import type { SdkJsonlTransport } from "./sdkJsonlTransport.js";
import {
  delay,
  isPromiseLike,
  isWebSocketClosedError,
  openGlobalWebSocket,
  serverLastRequestId,
  websocketCloseCode,
  withTimeout,
  type SdkWebSocketConnection,
  type SdkWebSocketConnector,
  type SdkWebSocketConnectOptions
} from "./sdkWebSocketConnection.js";
import { resolveWebSocketProxy, type SdkWebSocketProxyEnv } from "./sdkWebSocketProxy.js";
import { resolveWebSocketTlsConfig, type SdkWebSocketTlsConfig } from "./sdkWebSocketTls.js";

export type SdkWebSocketCloseHandler = (closeCode: number | undefined) => void;

export type SdkWebSocketJsonlTransportOptions = {
  headers?: Record<string, string>;
  refreshHeaders?: () => Record<string, string>;
  refresh_headers?: () => Record<string, string>;
  connector?: SdkWebSocketConnector;
  proxyUrl?: string;
  proxy_url?: string;
  noProxy?: string;
  no_proxy?: string;
  trustEnvProxy?: boolean;
  trust_env_proxy?: boolean;
  tlsContext?: unknown;
  sslContext?: unknown;
  ssl_context?: unknown;
  tlsCaFile?: string;
  tls_ca_file?: string;
  tlsCertFile?: string;
  tls_cert_file?: string;
  tlsKeyFile?: string;
  tls_key_file?: string;
  tlsKeyPassword?: string;
  tls_key_password?: string;
  connectOptions?: Record<string, unknown>;
  connect_options?: Record<string, unknown>;
  env?: SdkWebSocketProxyEnv;
  autoReconnect?: boolean;
  auto_reconnect?: boolean;
  maxBufferSize?: number;
  max_buffer_size?: number;
  reconnectBaseDelayMs?: number;
  reconnect_base_delay_seconds?: number;
  reconnectMaxDelayMs?: number;
  reconnect_max_delay_seconds?: number;
  reconnectGiveUpMs?: number;
  reconnect_give_up_seconds?: number;
  pingIntervalMs?: number;
  ping_interval_seconds?: number | null;
  pingTimeoutMs?: number;
  ping_timeout_seconds?: number;
  keepaliveIntervalMs?: number;
  keepalive_interval_seconds?: number | null;
  sleepDetectionThresholdMs?: number;
  sleep_detection_threshold_seconds?: number;
  sleep?: (milliseconds: number) => Promise<void>;
  now?: () => number;
  monotonic?: () => number;
};

const websocketMaxBufferSize = 1000;
const websocketReconnectBaseDelayMs = 1000;
const websocketReconnectMaxDelayMs = 30000;
const websocketReconnectGiveUpMs = 600000;
const websocketPermanentCloseCodes = new Set([1002, 4001, 4003]);
const websocketPingIntervalMs = 10000;
const websocketPingTimeoutMs = 10000;
const websocketKeepaliveIntervalMs = 300000;
const websocketSleepDetectionThresholdMs = websocketReconnectMaxDelayMs * 2;
const websocketKeepAliveFrame = "{\"type\":\"keep_alive\"}\n";

export class SdkWebSocketJsonlTransport implements SdkJsonlTransport {
  private readonly connector?: SdkWebSocketConnector;
  private readonly proxyUrl?: string;
  private readonly noProxy?: string;
  private readonly trustEnvProxy: boolean;
  private readonly tlsContext?: unknown;
  private readonly tlsConfig?: SdkWebSocketTlsConfig;
  private readonly connectOptions: Record<string, unknown>;
  private readonly env?: SdkWebSocketProxyEnv;
  private readonly autoReconnect: boolean;
  private readonly maxBufferSize: number;
  private readonly reconnectBaseDelayMs: number;
  private readonly reconnectMaxDelayMs: number;
  private readonly reconnectGiveUpMs: number;
  private readonly pingIntervalMs?: number;
  private readonly pingTimeoutMs: number;
  private readonly keepaliveIntervalMs?: number;
  private readonly sleepDetectionThresholdMs: number;
  private readonly sleep: (milliseconds: number) => Promise<void>;
  private readonly now: () => number;
  headers: Record<string, string>;
  readonly refreshHeaders?: () => Record<string, string>;
  private connection?: SdkWebSocketConnection;
  private messageBuffer: Record<string, unknown>[] = [];
  private lastSentId?: string;
  private onClose?: SdkWebSocketCloseHandler;
  private onConnect?: () => void;
  private reconnectAttempts = 0;
  private reconnectStartedAt?: number;
  private healthGeneration = 0;
  state: "idle" | "connected" | "reconnecting" | "closing" | "closed" = "idle";
  closed = false;

  constructor(readonly url: string, options: SdkWebSocketJsonlTransportOptions = {}) {
    this.headers = { ...(options.headers || {}) };
    this.refreshHeaders = options.refreshHeaders || options.refresh_headers;
    this.connector = options.connector;
    this.proxyUrl = stringOption(options.proxyUrl ?? options.proxy_url);
    this.noProxy = stringOption(options.noProxy ?? options.no_proxy);
    this.trustEnvProxy = booleanOption(options.trustEnvProxy ?? options.trust_env_proxy, true);
    this.tlsContext = options.tlsContext ?? options.sslContext ?? options.ssl_context;
    this.tlsConfig = this.tlsContext === undefined
      ? resolveWebSocketTlsConfig({
        caCertFile: options.tlsCaFile ?? options.tls_ca_file,
        clientCertFile: options.tlsCertFile ?? options.tls_cert_file,
        clientKeyFile: options.tlsKeyFile ?? options.tls_key_file,
        clientKeyPassword: options.tlsKeyPassword ?? options.tls_key_password,
        env: options.env
      })
      : undefined;
    this.connectOptions = { ...(options.connectOptions || options.connect_options || {}) };
    this.env = options.env;
    this.autoReconnect = booleanOption(options.autoReconnect ?? options.auto_reconnect, true);
    this.maxBufferSize = integerOption(options.maxBufferSize ?? options.max_buffer_size, websocketMaxBufferSize);
    this.reconnectBaseDelayMs = millisecondsOption(options.reconnectBaseDelayMs, options.reconnect_base_delay_seconds, websocketReconnectBaseDelayMs);
    this.reconnectMaxDelayMs = millisecondsOption(options.reconnectMaxDelayMs, options.reconnect_max_delay_seconds, websocketReconnectMaxDelayMs);
    this.reconnectGiveUpMs = millisecondsOption(options.reconnectGiveUpMs, options.reconnect_give_up_seconds, websocketReconnectGiveUpMs);
    this.pingIntervalMs = optionalMillisecondsOption(options.pingIntervalMs, options.ping_interval_seconds, websocketPingIntervalMs);
    this.pingTimeoutMs = millisecondsOption(options.pingTimeoutMs, options.ping_timeout_seconds, websocketPingTimeoutMs);
    this.keepaliveIntervalMs = optionalMillisecondsOption(options.keepaliveIntervalMs, options.keepalive_interval_seconds, websocketKeepaliveIntervalMs);
    this.sleepDetectionThresholdMs = millisecondsOption(
      options.sleepDetectionThresholdMs,
      options.sleep_detection_threshold_seconds,
      websocketSleepDetectionThresholdMs
    );
    this.sleep = options.sleep || ((milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds)));
    this.now = options.now || (options.monotonic ? () => options.monotonic!() * 1000 : Date.now);
  }

  get refresh_headers(): (() => Record<string, string>) | undefined {
    return this.refreshHeaders;
  }

  setOnClose(handler: SdkWebSocketCloseHandler | undefined): void {
    this.onClose = handler;
  }

  set_on_close(handler: SdkWebSocketCloseHandler | undefined): void {
    this.setOnClose(handler);
  }

  setOnConnect(handler: (() => void) | undefined): void {
    this.onConnect = handler;
  }

  set_on_connect(handler: (() => void) | undefined): void {
    this.setOnConnect(handler);
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

  getStateLabel(): string {
    return this.state;
  }

  get_state_label(): string {
    return this.getStateLabel();
  }

  async connect(): Promise<void> {
    if (this.connection || this.closed) return;
    if (!["idle", "reconnecting"].includes(this.state)) return;
    this.state = "reconnecting";
    const headers = this.connectHeaders();
    this.connection = await this.openConnection(headers);
    this.state = "connected";
    this.reconnectAttempts = 0;
    this.reconnectStartedAt = undefined;
    this.onConnect?.();
    await this.replayBufferedMessages(serverLastRequestId(this.connection));
    this.startHealthTasks();
  }

  async read(): Promise<string | Uint8Array | undefined> {
    while (!this.closed) {
      await this.connect();
      if (!this.connection) return undefined;
      try {
        return await this.connection.recv();
      } catch (error) {
        const closeCode = websocketCloseCode(error);
        if (closeCode === undefined && !isWebSocketClosedError(error)) throw error;
        if (!await this.handleConnectionError(closeCode)) return undefined;
      }
    }
    return undefined;
  }

  async write(data: string): Promise<void> {
    for (const line of data.split(/\r?\n/)) {
      if (!line.trim()) continue;
      const message = JSON.parse(line) as unknown;
      const buffered = this.bufferMessage(message);
      if (this.state !== "connected") {
        await this.connect();
        if (buffered) continue;
      }
      if (this.state === "connected") {
        const sent = await this.sendLine(`${ndjsonSafeStringify(message)}\n`);
        if (!sent) await this.handleConnectionError(undefined);
      }
    }
  }

  async close(): Promise<void> {
    this.closed = true;
    this.state = "closing";
    this.stopHealthTasks();
    await this.disconnect();
    this.state = "closed";
  }

  private async openConnection(headers: Record<string, string>): Promise<SdkWebSocketConnection> {
    const options = this.connectionOptions(headers);
    if (this.connector) return this.connector(this.url, headers, options);
    return openGlobalWebSocket(this.url, headers, options);
  }

  private connectionOptions(headers: Record<string, string>): SdkWebSocketConnectOptions {
    return {
      headers: { ...headers },
      proxy: resolveWebSocketProxy({
        url: this.url,
        proxyUrl: this.proxyUrl,
        noProxy: this.noProxy,
        trustEnvProxy: this.trustEnvProxy,
        env: this.env
      }),
      tlsContext: this.tlsContext,
      ssl_context: this.tlsContext,
      tls: this.tlsConfig,
      rawOptions: { ...this.connectOptions },
      raw_options: { ...this.connectOptions }
    };
  }

  private connectHeaders(): Record<string, string> {
    const headers = { ...this.headers };
    if (this.lastSentId) headers["X-Last-Request-Id"] = this.lastSentId;
    return headers;
  }

  private bufferMessage(message: unknown): boolean {
    if (!isRecord(message) || typeof message.uuid !== "string") return false;
    this.messageBuffer.push(message);
    if (this.messageBuffer.length > this.maxBufferSize) {
      this.messageBuffer.splice(0, this.messageBuffer.length - this.maxBufferSize);
    }
    this.lastSentId = message.uuid;
    return true;
  }

  private async sendLine(line: string): Promise<boolean> {
    if (!this.connection || this.state !== "connected") return false;
    try {
      await this.connection.send(line);
      return true;
    } catch {
      return false;
    }
  }

  private async handleConnectionError(closeCode: number | undefined): Promise<boolean> {
    await this.disconnect();
    if (["closing", "closed"].includes(this.state) || this.closed) return false;
    const headersRefreshed = this.refreshHeadersForUnauthorized(closeCode);
    if (closeCode !== undefined && websocketPermanentCloseCodes.has(closeCode) && !headersRefreshed) {
      this.closed = true;
      this.state = "closed";
      this.notifyClose(closeCode);
      return false;
    }
    if (!this.autoReconnect) {
      this.closed = true;
      this.state = "closed";
      this.notifyClose(closeCode);
      return false;
    }
    const currentTime = this.now();
    this.reconnectStartedAt ??= currentTime;
    if (currentTime - this.reconnectStartedAt >= this.reconnectGiveUpMs) {
      this.closed = true;
      this.state = "closed";
      this.notifyClose(closeCode);
      return false;
    }
    if (!headersRefreshed) this.refreshHeadersIfAvailable();
    this.reconnectAttempts += 1;
    this.state = "reconnecting";
    const delay = Math.min(
      this.reconnectBaseDelayMs * (2 ** (this.reconnectAttempts - 1)),
      this.reconnectMaxDelayMs
    );
    if (delay > 0) await this.sleep(delay);
    return !this.closed;
  }

  private refreshHeadersForUnauthorized(closeCode: number | undefined): boolean {
    if (closeCode !== 4003 || !this.refreshHeaders) return false;
    const freshHeaders = this.refreshHeaders();
    if (freshHeaders.Authorization === this.headers.Authorization) return false;
    this.headers = { ...this.headers, ...freshHeaders };
    return true;
  }

  private refreshHeadersIfAvailable(): void {
    if (this.refreshHeaders) this.headers = { ...this.headers, ...this.refreshHeaders() };
  }

  private async disconnect(): Promise<void> {
    this.stopHealthTasks();
    const connection = this.connection;
    this.connection = undefined;
    if (connection) await connection.close();
  }

  private startHealthTasks(): void {
    this.stopHealthTasks();
    const generation = ++this.healthGeneration;
    if (this.pingIntervalMs !== undefined && this.pingIntervalMs > 0) void this.pingLoop(generation);
    if (this.keepaliveIntervalMs !== undefined && this.keepaliveIntervalMs > 0) void this.keepaliveLoop(generation);
  }

  private stopHealthTasks(): void {
    this.healthGeneration += 1;
  }

  private async pingLoop(generation: number): Promise<void> {
    let lastTick = this.now();
    while (!this.closed && generation === this.healthGeneration) {
      await delay(this.pingIntervalMs || 0);
      if (this.state !== "connected" || !this.connection || generation !== this.healthGeneration) continue;
      const currentTime = this.now();
      const gap = currentTime - lastTick;
      lastTick = currentTime;
      if (gap > this.sleepDetectionThresholdMs) {
        if (await this.handleConnectionError(undefined)) await this.connect();
        return;
      }
      try {
        await this.pingConnection();
      } catch {
        if (await this.handleConnectionError(undefined)) await this.connect();
        return;
      }
    }
  }

  private async keepaliveLoop(generation: number): Promise<void> {
    while (!this.closed && generation === this.healthGeneration) {
      await delay(this.keepaliveIntervalMs || 0);
      if (this.state !== "connected" || generation !== this.healthGeneration) continue;
      if (!await this.sendLine(websocketKeepAliveFrame)) {
        if (await this.handleConnectionError(undefined)) await this.connect();
        return;
      }
    }
  }

  private async pingConnection(): Promise<void> {
    if (!this.connection?.ping) return;
    const result = await this.connection.ping();
    if (isPromiseLike(result)) await withTimeout(result, this.pingTimeoutMs, "WebSocket ping timeout");
  }

  private async replayBufferedMessages(lastRequestId: string | undefined): Promise<void> {
    if (!this.messageBuffer.length) return;
    if (lastRequestId) {
      const index = this.messageBuffer.findIndex((message) => message.uuid === lastRequestId);
      if (index !== -1) this.messageBuffer = this.messageBuffer.slice(index + 1);
      if (!this.messageBuffer.length) this.lastSentId = undefined;
    }
    for (const message of [...this.messageBuffer]) {
      if (!await this.sendLine(`${ndjsonSafeStringify(message)}\n`)) break;
    }
  }

  private notifyClose(closeCode: number | undefined): void {
    this.onClose?.(closeCode);
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function stringOption(value: unknown): string | undefined {
  return typeof value === "string" && value ? value : undefined;
}

function booleanOption(value: unknown, fallback: boolean): boolean {
  return typeof value === "boolean" ? value : fallback;
}

function integerOption(value: unknown, fallback: number): number {
  return typeof value === "number" && Number.isInteger(value) && value >= 0 ? value : fallback;
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
