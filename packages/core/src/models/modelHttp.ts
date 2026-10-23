import type { ModelClientConfig, TextDeltaHandler } from "./modelClientTypes.js";

export async function postJson(config: ModelClientConfig, suffix: string, body: unknown, auth = true): Promise<any> {
  const response = await fetch(`${config.baseUrl}${suffix}`, {
    method: "POST",
    headers: headersFor(config, auth),
    body: JSON.stringify(body),
    signal: requestSignal(config)
  });
  const text = await response.text();
  const payload = parseModelJson(text);
  if (!response.ok) throw new Error(modelError(response.status, payload, text));
  return payload;
}

export async function streamSse(
  config: ModelClientConfig,
  suffix: string,
  body: unknown,
  pickDelta: (payload: any) => string,
  onDelta: TextDeltaHandler
): Promise<string> {
  const response = await fetch(`${config.baseUrl}${suffix}`, {
    method: "POST",
    headers: headersFor(config, true),
    body: JSON.stringify(body),
    signal: requestSignal(config)
  });
  if (!response.ok || !response.body) {
    throw new Error(modelError(response.status, parseModelJson(await response.text()), ""));
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let content = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parsed = drainSse(buffer, pickDelta, onDelta);
    buffer = parsed.rest;
    content += parsed.content;
  }
  return content;
}

export function parseModelJson(text: string): any {
  try {
    return JSON.parse(text);
  } catch {
    return {};
  }
}

function drainSse(
  buffer: string,
  pickDelta: (payload: any) => string,
  onDelta: TextDeltaHandler
): { rest: string; content: string } {
  const chunks = buffer.split("\n\n");
  const rest = chunks.pop() || "";
  let content = "";
  for (const chunk of chunks) {
    for (const line of chunk.split("\n")) {
      if (!line.startsWith("data: ")) continue;
      const data = line.slice(6).trim();
      if (!data || data === "[DONE]") continue;
      const delta = pickDelta(parseModelJson(data));
      if (delta) {
        content += delta;
        onDelta(delta);
      }
    }
  }
  return { rest, content };
}

function headersFor(config: ModelClientConfig, auth: boolean): Record<string, string> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (!auth) return headers;
  if (config.protocol === "claude-messages") {
    headers["x-api-key"] = config.apiKey;
    headers["anthropic-version"] = "2023-06-01";
  } else {
    headers.Authorization = `Bearer ${config.apiKey}`;
  }
  return headers;
}

function requestSignal(config: ModelClientConfig): AbortSignal {
  const timeoutSignal = AbortSignal.timeout(config.timeoutMs);
  if (!config.signal) return timeoutSignal;
  if (config.signal.aborted) return config.signal;
  const anySignal = (AbortSignal as typeof AbortSignal & { any?: (signals: AbortSignal[]) => AbortSignal }).any;
  return anySignal ? anySignal([config.signal, timeoutSignal]) : linkedAbortSignal([config.signal, timeoutSignal]);
}

function linkedAbortSignal(signals: AbortSignal[]): AbortSignal {
  const controller = new AbortController();
  for (const signal of signals) {
    if (signal.aborted) {
      controller.abort(signal.reason);
      return controller.signal;
    }
    signal.addEventListener("abort", () => controller.abort(signal.reason), { once: true });
  }
  return controller.signal;
}

function modelError(status: number, payload: any, fallback: string): string {
  return String(payload?.error?.message || payload?.message || fallback || `model request failed: ${status}`);
}
