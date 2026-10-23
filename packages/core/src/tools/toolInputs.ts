export {
  assertDirectory,
  assertFile,
  relativeWorkspacePath,
  resolveWorkspacePath
} from "../workspace/workspacePaths.js";

export function stringArg(value: unknown, fallback = ""): string {
  return typeof value === "string" && value.length ? value : fallback;
}

export function numberArg(value: unknown, fallback: number): number {
  const numberValue = Number(value);
  return Number.isFinite(numberValue) ? numberValue : fallback;
}

export function booleanArg(value: unknown, fallback = false): boolean {
  if (typeof value === "boolean") return value;
  if (typeof value === "string") return ["1", "true", "yes", "on"].includes(value.toLowerCase());
  return fallback;
}
