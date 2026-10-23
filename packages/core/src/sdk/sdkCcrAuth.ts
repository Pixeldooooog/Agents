export function extractBearerToken(headers: Record<string, string>): string | undefined {
  for (const [key, value] of Object.entries(headers)) {
    if (key.toLowerCase() !== "authorization") continue;
    const prefix = "bearer ";
    if (!value.toLowerCase().startsWith(prefix)) continue;
    const token = value.slice(prefix.length).trim();
    return token || undefined;
  }
  return undefined;
}

export function decodeJwtExpiry(token: string | undefined): number | undefined {
  if (!token) return undefined;
  const parts = token.split(".");
  if (parts.length < 2) return undefined;
  try {
    const payload = decodeBase64Url(parts[1]);
    const data = JSON.parse(payload) as unknown;
    if (!isRecord(data) || typeof data.exp !== "number") return undefined;
    return data.exp;
  } catch {
    return undefined;
  }
}

function decodeBase64Url(value: string): string {
  const padded = `${value}${"=".repeat((4 - (value.length % 4)) % 4)}`;
  const base64 = padded.replace(/-/g, "+").replace(/_/g, "/");
  return Buffer.from(base64, "base64").toString("utf8");
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export const extract_bearer_token = extractBearerToken;
export const decode_jwt_expiry = decodeJwtExpiry;
