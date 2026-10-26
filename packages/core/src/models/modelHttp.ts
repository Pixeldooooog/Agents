import { ModelHttpError } from "./modelErrors.js";
import { parseProtocolJson } from "./modelProtocolValidation.js";
import { recordValue } from "./modelProtocolValues.js";
import type { ModelClientConfig, TextDeltaHandler } from "./modelClientTypes.js";

export async function postJson(config: ModelClientConfig, suffix: string, body: unknown, auth = true): Promise<unknown> {
  const response = await fetch(`${config.baseUrl}${suffix}`, {
    method: "POST",
    headers: headersFor(config, auth),
    body: JSON.stringify(body),
    signal: requestSignal(config)
  });
  const text = await response.text();
  if (!response.ok) throw httpError(response.status, text);
  return parseProtocolJson(text);
}

export async function streamSse(
  config: ModelClientConfig,
  suffix: string,
  body: unknown,
  pickDelta: (payload: unknown) => string,
  onDelta: TextDeltaHandler
): Promise<string> {
  const response = await fetch(`${config.baseUrl}${suffix}`, {
    method: "POST",
    headers: headersFor(config, true),
    body: JSON.stringify(body),
    signal: requestSignal(config)
  });
  if (!response.ok || !response.body) {
    throw httpError(response.status, await response.text());
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let content = "";
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parsed = drainSse(buffer, pickDelta, onDelta);
      buffer = parsed.rest;
      content += parsed.content;
    }
  } finally {
    // Release the underlying connection even when parsing or the consumer fails.
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
  return content;
}

function drainSse(
  buffer: string,
  pickDelta: (payload: unknown) => string,
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
      const delta = pickDelta(parseProtocolJson(data));
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
  return AbortSignal.any([config.signal, timeoutSignal]);
}

function httpError(status: number, text: string): ModelHttpError {
  let payload: unknown;
  try { payload = JSON.parse(text) as unknown; } catch { /* HTTP status remains authoritative for non-JSON error pages. */ }
  const record = recordValue(payload);
  const message = recordValue(record.error).message ?? record.message;
  return new ModelHttpError(status, typeof message === "string" ? message : `model request failed: ${status}`);
}
