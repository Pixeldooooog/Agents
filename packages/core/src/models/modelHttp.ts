import { ModelHttpError, ModelProtocolError } from "./modelErrors.js";
import { readSseEvents, type SseEvent } from "./modelSse.js";
import { parseProtocolJson } from "./modelProtocolValidation.js";
import { recordValue } from "./modelProtocolValues.js";
import type { ModelClientConfig } from "./modelClientTypes.js";

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

/** Transport only: adapters decide which event completes a model turn. */
export async function* postSse(config: ModelClientConfig, suffix: string, body: unknown): AsyncGenerator<SseEvent> {
  const signal = requestSignal(config);
  const response = await fetch(`${config.baseUrl}${suffix}`, {
    method: "POST", headers: headersFor(config, true),
    body: JSON.stringify(body), signal
  });
  if (!response.ok) throw httpError(response.status, await response.text());
  if (!response.body) throw new ModelProtocolError("model stream has no body");
  if (response.headers.get("content-type")?.split(";")[0].trim().toLowerCase() !== "text/event-stream") {
    await response.body.cancel();
    throw new ModelProtocolError("model stream must use text/event-stream");
  }
  let size = 0;
  let count = 0;
  for await (const event of readSseEvents(response.body)) {
    signal.throwIfAborted();
    size += event.data.length;
    if (size > 16 * 1024 * 1024 || ++count > 65536) throw new ModelProtocolError("model stream exceeds size limit");
    yield event;
    signal.throwIfAborted();
  }
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
