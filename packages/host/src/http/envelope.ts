import type { ServerResponse } from "node:http";

export type ApiResponse = {
  success: boolean;
  code: string;
  message: string;
  data: unknown;
};

export function ok(data: unknown = {}, code = "200"): ApiResponse {
  return { success: true, code, message: "success", data };
}

export function fail(code: string, detail: unknown, status = Number(code) || 500): { status: number; body: ApiResponse } {
  return { status, body: { success: false, code, message: "failed", data: { detail } } };
}

export function sendJson(response: ServerResponse, status: number, body: unknown, headers: Record<string, string> = {}): void {
  const payload = JSON.stringify(body);
  response.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Content-Length": Buffer.byteLength(payload),
    ...headers
  });
  response.end(payload);
}

export function sendSse(response: ServerResponse, event: string, payload: unknown): void {
  response.write(`event: ${event}\n`);
  response.write(`data: ${JSON.stringify(payload)}\n\n`);
}
