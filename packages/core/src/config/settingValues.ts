import type { ConfigTree } from "./configFileReaders.js";

export type ModelSettings = {
  apiKey: string;
  baseUrl: string;
  model: string;
};

export function modelSettings(
  tree: ConfigTree,
  sectionName: string,
  env: Record<string, string | undefined>,
  prefix: string
): ModelSettings {
  const values = section(tree, sectionName);
  return {
    apiKey: stringSetting(env[`${prefix}_API_KEY`], valueOrFallback(values.api_key, "")),
    baseUrl: stringSetting(env[`${prefix}_BASE_URL`], valueOrFallback(values.base_url, "")),
    model: stringSetting(env[`${prefix}_MODEL`], valueOrFallback(values.model, ""))
  };
}

export function section(tree: ConfigTree, name: string): Record<string, unknown> {
  return tree[name] || {};
}

export function valueOrFallback<T>(input: unknown, fallback: T): T {
  return input === undefined || input === null || input === "" ? fallback : input as T;
}

export function stringSetting(input: unknown, fallback: unknown): string {
  return String(input ?? fallback ?? "").trim();
}

export function numberSetting(input: unknown, fallback: unknown): number {
  const number = Number(input ?? fallback);
  return Number.isFinite(number) ? number : 0;
}

export function boolSetting(input: unknown, fallback: unknown): boolean {
  if (typeof input === "boolean") return input;
  const normalized = String(input ?? fallback ?? "").trim().toLowerCase();
  return ["1", "true", "yes", "on", "debug", "dev", "development"].includes(normalized);
}

export function listSetting(input: unknown, fallback: unknown): string[] {
  const settingValue = input ?? fallback;
  if (Array.isArray(settingValue)) {
    return settingValue.map(String).map((item) => item.trim()).filter(Boolean);
  }
  return String(settingValue ?? "").split(",").map((item) => item.trim()).filter(Boolean);
}

export function headerSetting(input: unknown, fallback: unknown): Record<string, string> {
  const settingValue = input ?? fallback;
  if (typeof settingValue === "string") {
    try {
      const parsed = JSON.parse(settingValue);
      return headerSetting(parsed, {});
    } catch {
      return {};
    }
  }
  if (!settingValue || typeof settingValue !== "object" || Array.isArray(settingValue)) return {};
  return Object.fromEntries(Object.entries(settingValue).map(([key, item]) => [key, String(item)]));
}
