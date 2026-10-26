import { ModelHttpError, ModelProtocolError } from "./modelErrors.js";
import { readSseEvents, type SseEvent } from "./modelSse.js";
import { parseProtocolJson } from "./modelProtocolValidation.js";
import { recordValue } from "./modelProtocolValues.js";
import type { ModelClientConfig, TextDeltaHandler, TextStreamStep } from "./modelClientTypes.js";

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
  consume: (event: SseEvent) => TextStreamStep,
  onDelta: TextDeltaHandler
): Promise<string> {
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
  const parts: string[] = [];
  let size = 0;
  for await (const event of readSseEvents(response.body)) {
    signal.throwIfAborted();
    const step = consume(event);
    if (step.delta) {
      size += step.delta.length;
      if (size > 8 * 1024 * 1024) throw new ModelProtocolError("model text exceeds stream size limit");
      parts.push(step.delta);
      onDelta(step.delta);
      signal.throwIfAborted();
    }
    if (step.done) return parts.join("");
  }
  signal.throwIfAborted();
  throw new ModelProtocolError("model stream ended before protocol completion");
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
