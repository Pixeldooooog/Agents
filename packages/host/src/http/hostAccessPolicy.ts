import { timingSafeEqual } from "node:crypto";
import type { IncomingMessage } from "node:http";
import { isIP } from "node:net";
import type { Settings } from "@kevin/core";

export type HostAccessPolicy = {
  loopbackOnly: boolean;
  publicOrigin: string;
  allowedOrigins: ReadonlySet<string>;
  token: string;
};

export function createHostAccessPolicy(host: Settings["host"]): HostAccessPolicy {
  const loopbackOnly = isLoopback(host.bindHost);
  const token = host.accessToken.trim();
  if (!loopbackOnly && !token) {
    throw new Error("Non-loopback HOST requires an explicit ACCESS_TOKEN");
  }
  return {
    loopbackOnly,
    publicOrigin: parseOrigin(host.domain),
    allowedOrigins: new Set(host.corsOrigins.map(parseOrigin)),
    token
  };
}

/** Origin checks protect browser access; bearer auth protects remote/native access. */
export function requestOriginAllowed(policy: HostAccessPolicy, request: IncomingMessage): boolean {
  const authority = request.headers.host;
  if (!authority) return false;
  let target: URL;
  try {
    target = new URL(`http://${authority}`);
    if (target.username || target.password || target.pathname !== "/" || target.search || target.hash) return false;
  } catch {
    return false;
  }
  // A foreign Host header must not turn a loopback server into a DNS-rebinding endpoint.
  if (policy.loopbackOnly && !isLoopback(target.hostname)) return false;
  const origin = request.headers.origin;
  if (origin === undefined) return request.headers["sec-fetch-site"] !== "cross-site";
  let normalized: string;
  try {
    normalized = parseOrigin(origin);
  } catch {
    return false;
  }
  return normalized === target.origin
    || (normalized === policy.publicOrigin && new URL(normalized).host === target.host)
    || policy.allowedOrigins.has(normalized);
}

export function requestAuthorized(policy: HostAccessPolicy, request: IncomingMessage): boolean {
  if (!policy.token) return policy.loopbackOnly;
  const actual = Buffer.from(request.headers.authorization || "");
  const expected = Buffer.from(`Bearer ${policy.token}`);
  return actual.length === expected.length && timingSafeEqual(actual, expected);
}

export function corsHeaders(request: IncomingMessage): Record<string, string> {
  return {
    Vary: "Origin",
    ...(request.headers.origin ? { "Access-Control-Allow-Origin": request.headers.origin } : {}),
    "Access-Control-Allow-Headers": "Content-Type, Authorization, Idempotency-Key, Last-Event-ID",
    "Access-Control-Allow-Methods": "GET, POST, PATCH, DELETE, OPTIONS"
  };
}

function isLoopback(host: string): boolean {
  const normalized = host.toLowerCase().replace(/^\[|\]$/g, "");
  return normalized === "localhost" || normalized === "::1"
    || (isIP(normalized) === 4 && normalized.startsWith("127."));
}

function parseOrigin(value: string): string {
  const url = new URL(value);
  if (!["http:", "https:"].includes(url.protocol) || url.username || url.password
    || url.pathname !== "/" || url.search || url.hash || url.hostname.includes("*")) {
    throw new Error("Host domain and CORS origins must be explicit HTTP(S) origins without paths or wildcards");
  }
  return url.origin;
}
