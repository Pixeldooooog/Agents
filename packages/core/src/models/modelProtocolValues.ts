export type ModelProtocolRecord = Record<string, unknown>;

export function recordValue(value: unknown): ModelProtocolRecord {
  return value && typeof value === "object" && !Array.isArray(value) ? value as ModelProtocolRecord : {};
}

export function recordArray(value: unknown): ModelProtocolRecord[] {
  return Array.isArray(value) ? value.map(recordValue) : [];
}

export function stringValue(value: unknown): string {
  if (typeof value === "string") return value;
  return value == null ? "" : String(value);
}
