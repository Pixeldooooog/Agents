import type { SdkWebSocketTlsConfig } from "./sdkWebSocketTls.js";

export type SdkWebSocketConnectOptions = {
  headers: Record<string, string>;
  proxy?: string;
  tlsContext?: unknown;
  ssl_context?: unknown;
  tls?: SdkWebSocketTlsConfig;
  rawOptions: Record<string, unknown>;
  raw_options: Record<string, unknown>;
};

export type SdkWebSocketConnection = {
  recv(): Promise<string | Uint8Array | undefined>;
  send(data: string): Promise<void> | void;
  close(): Promise<void> | void;
  ping?(): Promise<unknown> | unknown;
  responseHeaders?: HeaderLike;
  headers?: HeaderLike;
  response?: { headers?: HeaderLike };
};

export type SdkWebSocketConnector = (
  url: string,
  headers: Record<string, string>,
  options: SdkWebSocketConnectOptions
) => Promise<SdkWebSocketConnection>;

type HeaderLike = {
  get(name: string): string | undefined | null;
};

export async function openGlobalWebSocket(
  url: string,
  headers: Record<string, string>,
  options?: SdkWebSocketConnectOptions
): Promise<SdkWebSocketConnection> {
  const WebSocketConstructor = WebSocket as unknown as new (targetUrl: string, options?: unknown) => WebSocket;
  const websocket = new WebSocketConstructor(url, globalWebSocketOptions(headers, options));
  const inbound = new WebSocketInboundQueue();
  websocket.addEventListener("message", (event) => inbound.push(event.data as string | Uint8Array));
  websocket.addEventListener("close", () => inbound.close());
  websocket.addEventListener("error", () => inbound.close());
  if (websocket.readyState === WebSocket.CONNECTING) await waitForOpen(websocket);
  return {
    recv: () => inbound.shift(),
    send: (data) => websocket.send(data),
    close: () => websocket.close()
  };
}

function globalWebSocketOptions(
  headers: Record<string, string>,
  options: SdkWebSocketConnectOptions | undefined
): Record<string, unknown> {
  const websocketOptions: Record<string, unknown> = { ...(options?.rawOptions || options?.raw_options || {}), headers };
  if (options?.proxy !== undefined && websocketOptions.proxy === undefined) websocketOptions.proxy = options.proxy;
  if (websocketOptions.tls === undefined) {
    if (options?.tlsContext !== undefined) websocketOptions.tls = options.tlsContext;
    else if (options?.ssl_context !== undefined) websocketOptions.tls = options.ssl_context;
    else if (options?.tls !== undefined) websocketOptions.tls = options.tls;
  }
  return websocketOptions;
}

export function serverLastRequestId(connection: SdkWebSocketConnection): string | undefined {
  const headers = connection.responseHeaders || connection.headers || connection.response?.headers;
  if (!headers) return undefined;
  for (const key of ["x-last-request-id", "X-Last-Request-Id"]) {
    const value = headers.get(key);
    if (typeof value === "string") return value;
  }
  return undefined;
}

export function websocketCloseCode(error: unknown): number | undefined {
  if (!isRecord(error)) return undefined;
  if (typeof error.code === "number") return error.code;
  const received = error.rcvd;
  if (isRecord(received) && typeof received.code === "number") return received.code;
  return undefined;
}

export function isWebSocketClosedError(error: unknown): boolean {
  return error instanceof Error && (
    error.constructor.name.startsWith("ConnectionClosed") || websocketCloseCode(error) !== undefined
  );
}

export function delay(milliseconds: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

export function withTimeout<T>(promise: Promise<T>, timeoutMs: number, message: string): Promise<T> {
  let timeout: ReturnType<typeof setTimeout> | undefined;
  const timeoutPromise = new Promise<T>((_, reject) => {
    timeout = setTimeout(() => reject(new Error(message)), timeoutMs);
  });
  return Promise.race([promise, timeoutPromise]).finally(() => {
    if (timeout) clearTimeout(timeout);
  });
}

export function isPromiseLike(value: unknown): value is Promise<unknown> {
  return isRecord(value) && typeof value.then === "function";
}

function waitForOpen(websocket: WebSocket): Promise<void> {
  return new Promise((resolve, reject) => {
    websocket.addEventListener("open", () => resolve(), { once: true });
    websocket.addEventListener("error", () => reject(new Error("WebSocket connection failed")), { once: true });
  });
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

class WebSocketInboundQueue {
  private messages: Array<string | Uint8Array> = [];
  private waiters: Array<(message: string | Uint8Array | undefined) => void> = [];
  private closed = false;

  push(message: string | Uint8Array): void {
    const waiter = this.waiters.shift();
    if (waiter) {
      waiter(message);
      return;
    }
    this.messages.push(message);
  }

  close(): void {
    this.closed = true;
    while (this.waiters.length) this.waiters.shift()?.(undefined);
  }

  async shift(): Promise<string | Uint8Array | undefined> {
    if (this.messages.length) return this.messages.shift();
    if (this.closed) return undefined;
    return new Promise((resolve) => this.waiters.push(resolve));
  }
}
