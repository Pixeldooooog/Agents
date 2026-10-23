export function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

export function optionalObjectValue(value: unknown): Record<string, unknown> | undefined {
  const record = objectValue(value);
  return Object.keys(record).length ? record : undefined;
}

export function stringField(source: Record<string, unknown>, ...keys: string[]): string {
  for (const key of keys) {
    const value = source[key];
    if (value !== undefined && value !== null && value !== "") return String(value);
  }
  return "";
}

export function numberField(value: unknown): number {
  const parsed = Number(value || 0);
  return Number.isFinite(parsed) ? parsed : 0;
}

export function stringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => String(item || "")).filter(Boolean);
}

export function parseJsonObject(value: unknown): Record<string, unknown> {
  if (value && typeof value === "object" && !Array.isArray(value)) return value as Record<string, unknown>;
  if (typeof value !== "string" || !value.trim()) return {};
  try {
    return objectValue(JSON.parse(value));
  } catch {
    return {};
  }
}

export function newSdkMessageUuid(): string {
  return `sdk_${crypto.randomUUID().replaceAll("-", "")}`;
}
