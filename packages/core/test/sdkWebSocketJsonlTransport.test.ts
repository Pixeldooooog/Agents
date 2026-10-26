import { describe, expect, test } from "bun:test";
import {
  SDKWebSocketJsonlTransport,
  SdkWebSocketJsonlTransport,
  shouldBypassProxy,
  type SdkWebSocketConnectOptions,
  type SdkWebSocketConnection
} from "@kevin/core/sdk";

describe("SDK WebSocket JSONL transport", () => {
  test("resolves proxy and connection options for connector transports", async () => {
    const captured: Array<{ url: string; headers: Record<string, string>; options: SdkWebSocketConnectOptions }> = [];
    const tlsContext = { ca: "test" };
    let connectCount = 0;
    const refreshHeaders = () => ({ Authorization: "Bearer refreshed" });
    const transport = new SDKWebSocketJsonlTransport("wss://api.example.com/v2/session_ingress/ws/abc", {
      headers: { Authorization: "Bearer token" },
      refresh_headers: refreshHeaders,
      connector: async (url, headers, options) => {
        captured.push({ url, headers, options });
        return new FakeWebSocket();
      },
      proxy_url: "http://proxy.local:8080",
      no_proxy: "localhost",
      trust_env_proxy: false,
      ssl_context: tlsContext,
      connect_options: { compression: false },
      env: { https_proxy: "http://proxy.local:8080", no_proxy: "localhost" },
      ping_interval_seconds: null,
      keepalive_interval_seconds: null
    });
    transport.set_on_connect(() => {
      connectCount += 1;
    });

    expect(transport.headers).toEqual({ Authorization: "Bearer token" });
    expect(transport.refreshHeaders).toBe(refreshHeaders);
    expect(transport.refresh_headers).toBe(refreshHeaders);
    expect(transport.get_state_label()).toBe("idle");
    await transport.connect();
    expect(transport.is_connected_status()).toBe(true);
    await transport.close();

    expect(captured[0].url).toBe("wss://api.example.com/v2/session_ingress/ws/abc");
    expect(captured[0].headers.Authorization).toBe("Bearer token");
    expect(captured[0].options.proxy).toBe("http://proxy.local:8080");
    expect(captured[0].options.tlsContext).toBe(tlsContext);
    expect(captured[0].options.ssl_context).toBe(tlsContext);
    expect(captured[0].options.tls).toBeUndefined();
    expect(captured[0].options.rawOptions).toEqual({ compression: false });
    expect(captured[0].options.raw_options).toEqual({ compression: false });
    expect(connectCount).toBe(1);
    expect(transport.is_closed_status()).toBe(true);
  });

  test("resolves TLS file options and environment aliases for connector transports", async () => {
    const captured: SdkWebSocketConnectOptions[] = [];
    const transport = new SdkWebSocketJsonlTransport("wss://api.example.com/v2/session_ingress/ws/abc", {
      connector: async (_url, _headers, options) => {
        captured.push(options);
        return new FakeWebSocket();
      },
      tls_ca_file: "/explicit/ca.pem",
      env: {
        KEVIN_SDK_CA_CERTS: "/env/ca.pem",
        CLAUDE_CODE_CLIENT_CERT: "/env/client.pem",
        KEVIN_SDK_CLIENT_KEY: "/env/client.key",
        CLAUDE_CODE_CLIENT_KEY_PASSPHRASE: "secret"
      },
      ping_interval_seconds: null,
      keepalive_interval_seconds: null
    });

    await transport.connect();
    await transport.close();

    expect(captured[0].tls).toEqual({
      caCertFile: "/explicit/ca.pem",
      clientCertFile: "/env/client.pem",
      clientKeyFile: "/env/client.key",
      clientKeyPassword: "secret"
    });
    expect(captured[0].tlsContext).toBeUndefined();
  });

  test("honors no_proxy host rules", async () => {
    const proxies: Array<string | undefined> = [];
    const transport = new SdkWebSocketJsonlTransport("wss://api.example.com/v2/session_ingress/ws/abc", {
      connector: async (_url, _headers, options) => {
        proxies.push(options.proxy);
        return new FakeWebSocket();
      },
      env: {
        HTTPS_PROXY: "http://proxy.local:8080",
        NO_PROXY: ".example.com"
      }
    });

    await transport.connect();
    await transport.close();

    expect(proxies).toEqual([undefined]);
    expect(shouldBypassProxy("wss://api.example.com:443/ws", ".example.com")).toBe(true);
  });

  test("reconnects and replays unconfirmed uuid messages", async () => {
    const sockets = [
      new FakeWebSocket({ recvItems: [new FakeWebSocketClosed(1006)] }),
      new FakeWebSocket({
        recvItems: ["{\"type\":\"keep_alive\"}\n"],
        responseHeaders: fakeHeaders({ "x-last-request-id": "uuid-1" })
      })
    ];
    const calls: Array<{ headers: Record<string, string> }> = [];
    const transport = new SdkWebSocketJsonlTransport("wss://api.example.com/v2/session_ingress/ws/abc", {
      headers: { Authorization: "Bearer token" },
      connector: async (_url, headers) => {
        calls.push({ headers });
        return sockets[calls.length - 1];
      },
      reconnectBaseDelayMs: 0,
      sleep: async () => undefined
    });

    await transport.write("{\"type\":\"result\",\"uuid\":\"uuid-1\",\"result\":\"one\"}\n");
    await transport.write("{\"type\":\"result\",\"uuid\":\"uuid-2\",\"result\":\"two\"}\n");
    const inbound = await transport.read();
    await transport.close();

    expect(inbound).toBe("{\"type\":\"keep_alive\"}\n");
    expect(calls[0].headers.Authorization).toBe("Bearer token");
    expect(calls[1].headers["X-Last-Request-Id"]).toBe("uuid-2");
    expect(sockets[0].sent.map((line) => JSON.parse(line).uuid)).toEqual(["uuid-1", "uuid-2"]);
    expect(sockets[1].sent.map((line) => JSON.parse(line).uuid)).toEqual(["uuid-2"]);
  });

  test("stops on permanent close codes", async () => {
    const closed: Array<number | undefined> = [];
    const transport = new SdkWebSocketJsonlTransport("wss://api.example.com/v2/session_ingress/ws/abc", {
      connector: async () => new FakeWebSocket({ recvItems: [new FakeWebSocketClosed(4001)] })
    });
    transport.set_on_close((closeCode) => closed.push(closeCode));

    const line = await transport.read();

    expect(line).toBeUndefined();
    expect(closed).toEqual([4001]);
    expect(transport.isClosedStatus()).toBe(true);
  });

  test("refreshes headers for unauthorized close codes", async () => {
    const sockets = [
      new FakeWebSocket({ recvItems: [new FakeWebSocketClosed(4003)] }),
      new FakeWebSocket({ recvItems: ["{\"type\":\"keep_alive\"}\n"] })
    ];
    const calls: Array<{ headers: Record<string, string> }> = [];
    const transport = new SdkWebSocketJsonlTransport("wss://api.example.com/v2/session_ingress/ws/abc", {
      headers: { Authorization: "Bearer old" },
      refreshHeaders: () => ({ Authorization: "Bearer new" }),
      connector: async (_url, headers) => {
        calls.push({ headers });
        return sockets[calls.length - 1];
      },
      reconnectBaseDelayMs: 0,
      sleep: async () => undefined
    });

    const line = await transport.read();
    await transport.close();

    expect(line).toBe("{\"type\":\"keep_alive\"}\n");
    expect(calls.map((call) => call.headers.Authorization)).toEqual(["Bearer old", "Bearer new"]);
  });

  test("sends periodic keepalive frames", async () => {
    const socket = new FakeWebSocket();
    const transport = new SdkWebSocketJsonlTransport("wss://api.example.com/v2/session_ingress/ws/abc", {
      connector: async () => socket,
      pingIntervalMs: 0,
      keepaliveIntervalMs: 5
    });

    await transport.connect();
    await waitFor(() => socket.sent.length > 0);
    await transport.close();

    expect(socket.sent).toEqual(["{\"type\":\"keep_alive\"}\n"]);
  });

  test("uses Python-style monotonic seconds for sleep gap detection", async () => {
    const sockets = [new FakeWebSocket(), new FakeWebSocket()];
    const calls: Array<{ headers: Record<string, string> }> = [];
    const ticks = [0, 61];
    const transport = new SDKWebSocketJsonlTransport("wss://api.example.com/v2/session_ingress/ws/abc", {
      connector: async (_url, headers) => {
        calls.push({ headers });
        return sockets[calls.length - 1];
      },
      reconnect_base_delay_seconds: 0,
      ping_interval_seconds: 0.01,
      keepalive_interval_seconds: null,
      sleep_detection_threshold_seconds: 60,
      monotonic: () => ticks.shift() ?? 61,
      sleep: async () => undefined
    });

    await transport.connect();
    await waitFor(() => calls.length >= 2);
    await transport.close();

    expect(calls).toHaveLength(2);
    expect(sockets[0].pings).toBe(0);
    expect(sockets[0].closed).toBe(true);
  });
});

class FakeWebSocketClosed extends Error {
  constructor(readonly code: number) {
    super(`closed ${code}`);
  }
}

class FakeWebSocket implements SdkWebSocketConnection {
  sent: string[] = [];
  closed = false;
  pings = 0;
  responseHeaders?: { get(name: string): string | undefined };
  private recvItems: unknown[];
  private pingError?: Error;

  constructor(options: {
    recvItems?: unknown[];
    responseHeaders?: { get(name: string): string | undefined };
    pingError?: Error;
  } = {}) {
    this.recvItems = [...(options.recvItems || [])];
    this.responseHeaders = options.responseHeaders;
    this.pingError = options.pingError;
  }

  async recv(): Promise<string | Uint8Array | undefined> {
    const item = this.recvItems.shift();
    if (item instanceof Error) throw item;
    return item as string | Uint8Array | undefined;
  }

  async send(data: string): Promise<void> {
    this.sent.push(data);
  }

  async close(): Promise<void> {
    this.closed = true;
  }

  async ping(): Promise<void> {
    this.pings += 1;
    if (this.pingError) throw this.pingError;
  }
}

function fakeHeaders(values: Record<string, string>): { get(name: string): string | undefined } {
  return {
    get(name: string) {
      return values[name];
    }
  };
}

async function waitFor(predicate: () => boolean): Promise<void> {
  for (let attempt = 0; attempt < 50; attempt += 1) {
    if (predicate()) return;
    await new Promise((resolve) => setTimeout(resolve, 5));
  }
  throw new Error("condition not reached");
}
