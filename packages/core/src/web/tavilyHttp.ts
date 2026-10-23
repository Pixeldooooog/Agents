import type { WebSearchSettings } from "../config/settings.js";

export type TavilyPayload = Record<string, unknown>;

export async function postTavily(settings: WebSearchSettings, suffix: string, payload: TavilyPayload): Promise<TavilyPayload> {
  const response = await fetch(`${settings.tavilyBaseUrl.replace(/\/+$/, "")}${suffix}`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${settings.tavilyApiKey}`,
      "Content-Type": "application/json"
    },
    body: JSON.stringify(payload),
    signal: AbortSignal.timeout(Math.max(1, settings.timeout) * 1000)
  });
  const text = await response.text();
  const data = safeJson(text);
  if (!response.ok) throw new Error(`Tavily request failed: ${text.slice(0, 1000)}`);
  if (!isRecord(data)) throw new Error("Tavily returned a non-object response");
  return data;
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return {};
  }
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}
