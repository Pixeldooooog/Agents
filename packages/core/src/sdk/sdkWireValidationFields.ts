export function requireFrameObject(value: unknown): Record<string, unknown> {
  const result = objectValue(value);
  if (!result) throw new Error("frame must be an object");
  return result;
}

export function requireString(value: Record<string, unknown>, key: string): string {
  const result = stringValue(value[key]);
  if (result === undefined) throw new Error(`${key} must be a string`);
  return result;
}

export function requireNumber(value: Record<string, unknown>, key: string): number {
  const result = value[key];
  if (typeof result !== "number" || !Number.isFinite(result)) throw new Error(`${key} must be a finite number`);
  return result;
}

export function requireBoolean(value: Record<string, unknown>, key: string): boolean {
  const result = value[key];
  if (typeof result !== "boolean") throw new Error(`${key} must be a boolean`);
  return result;
}

export function requireObject(value: Record<string, unknown>, key: string): Record<string, unknown> {
  const result = objectValue(value[key]);
  if (!result) throw new Error(`${key} must be an object`);
  return result;
}

export function requireObjectArray(value: Record<string, unknown>, key: string): Array<Record<string, unknown>> {
  const result = value[key];
  if (!Array.isArray(result)) throw new Error(`${key} must be an object array`);
  for (const [index, item] of result.entries()) {
    if (!objectValue(item)) throw new Error(`${key}.${index} must be an object`);
  }
  return result as Array<Record<string, unknown>>;
}

export function requireStringArray(value: Record<string, unknown>, key: string): string[] {
  const result = value[key];
  if (!Array.isArray(result) || result.some((item) => typeof item !== "string")) {
    throw new Error(`${key} must be a string array`);
  }
  return result as string[];
}

export function requireStringRecord(value: Record<string, unknown>, key: string): Record<string, string> {
  const result = requireObject(value, key);
  for (const [recordKey, recordValue] of Object.entries(result)) {
    if (typeof recordValue !== "string") throw new Error(`${key}.${recordKey} must be a string`);
  }
  return result as Record<string, string>;
}

export function optionalString(value: Record<string, unknown>, key: string): void {
  if (value[key] !== undefined) requireString(value, key);
}

export function optionalNumber(value: Record<string, unknown>, key: string): void {
  if (value[key] !== undefined) requireNumber(value, key);
}

export function optionalNumberOrNull(value: Record<string, unknown>, key: string): void {
  if (value[key] === undefined || value[key] === null) return;
  requireNumber(value, key);
}

export function optionalStringOrNull(value: Record<string, unknown>, key: string): void {
  if (value[key] === undefined || value[key] === null) return;
  requireString(value, key);
}

export function optionalBoolean(value: Record<string, unknown>, key: string): void {
  if (value[key] !== undefined) requireBoolean(value, key);
}

export function optionalBooleanOrNull(value: Record<string, unknown>, key: string): void {
  if (value[key] === undefined || value[key] === null) return;
  requireBoolean(value, key);
}

export function optionalObject(value: Record<string, unknown>, key: string): void {
  if (value[key] !== undefined) requireObject(value, key);
}

export function optionalObjectOrNull(value: Record<string, unknown>, key: string): void {
  if (value[key] === undefined || value[key] === null) return;
  requireObject(value, key);
}

export function optionalObjectArray(value: Record<string, unknown>, key: string): void {
  if (value[key] !== undefined) requireObjectArray(value, key);
}

export function optionalObjectArrayOrNull(value: Record<string, unknown>, key: string): void {
  if (value[key] === undefined || value[key] === null) return;
  requireObjectArray(value, key);
}

export function optionalStringArray(value: Record<string, unknown>, key: string): void {
  const result = value[key];
  if (result === undefined) return;
  if (!Array.isArray(result) || result.some((item) => typeof item !== "string")) {
    throw new Error(`${key} must be a string array`);
  }
}

export function optionalStringArrayOrNull(value: Record<string, unknown>, key: string): void {
  if (value[key] === undefined || value[key] === null) return;
  optionalStringArray(value, key);
}

export function rejectUnknownKeys(value: Record<string, unknown>, path: string, allowedKeys: string[]): void {
  const allowed = new Set(allowedKeys);
  for (const key of Object.keys(value)) {
    if (!allowed.has(key)) throw new Error(`${path}.${key} is not supported`);
  }
}

export function objectValue(value: unknown): Record<string, unknown> | undefined {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : undefined;
}

export function stringValue(value: unknown): string | undefined {
  return typeof value === "string" ? value : undefined;
}
