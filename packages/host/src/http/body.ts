import type { IncomingMessage } from "node:http";

export async function readJson<T = any>(request: IncomingMessage): Promise<T> {
  const chunks: Buffer[] = [];
  for await (const chunk of request) chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
  const text = Buffer.concat(chunks).toString("utf8").trim();
  return text ? JSON.parse(text) as T : {} as T;
}

export function queryValue(url: URL, name: string, fallback = ""): string {
  return url.searchParams.get(name) || fallback;
}

export function queryNumber(url: URL, name: string, fallback: number): number {
  const value = Number(url.searchParams.get(name) || fallback);
  return Number.isFinite(value) ? value : fallback;
}
