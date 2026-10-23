export function normalizeList(value: unknown): unknown[] {
  if (Array.isArray(value)) return value;
  const record = objectRecord(value);
  if (Array.isArray(record.resources)) return record.resources;
  if (Array.isArray(record.prompts)) return record.prompts;
  return [];
}

export function objectRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

export function requiredText(value: string, name: string): string {
  const text = value.trim();
  if (!text) throw new Error(`${name} is required`);
  return text;
}

export function clampResultLimit(value: number, fallback: number, maximum: number): number {
  const numberValue = Number(value || fallback);
  return Math.max(1, Math.min(Number.isFinite(numberValue) ? numberValue : fallback, maximum));
}
