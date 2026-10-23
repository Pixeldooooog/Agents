import type { SdkCcrRequestResult } from "./sdkCcrTypes.js";

export function ccrRetryAfterMilliseconds(result: SdkCcrRequestResult): number | undefined {
  if (finiteNumber(result.retryAfterMs)) return result.retryAfterMs;
  return finiteNumber(result.retry_after_seconds) ? result.retry_after_seconds * 1000 : undefined;
}

export function ccrIntegerOption(value: unknown, fallback: number): number {
  const parsed = Number(value);
  return Number.isInteger(parsed) ? parsed : fallback;
}

export function ccrMillisecondsOption(milliseconds: unknown, seconds: unknown, fallback: number): number {
  if (finiteNumber(milliseconds)) return milliseconds;
  return finiteNumber(seconds) ? seconds * 1000 : fallback;
}

export function optionalCcrMillisecondsOption(
  milliseconds: unknown,
  seconds: unknown,
  fallback: number
): number | undefined {
  if (milliseconds === null || seconds === null) return undefined;
  return ccrMillisecondsOption(milliseconds, seconds, fallback);
}

function finiteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}
