import type { OperationFile, OperationSource } from "../types/runtimeTypes";
import { fileTarget, isEditTool } from "./operationToolMapping";

export function scrubArgs(args: Record<string, any>) {
  const clone = { ...args };
  for (const key of Object.keys(clone)) if (/key|token|secret|password/i.test(key)) clone[key] = "[redacted]";
  return clone;
}

export function previewResult(result: any) {
  if (result == null) return undefined;
  if (typeof result === "string") return result.slice(0, 1200);
  return result;
}

export function sourcesFromResult(result: any): OperationSource[] {
  const sources = Array.isArray(result?.sources) ? result.sources : [];
  return sources.slice(0, 6).map((source: any) => ({
    title: String(source.title || source.url || "Source"),
    url: String(source.url || ""),
    domain: source.domain ? String(source.domain) : domainFromUrl(source.url),
    content: source.content ? String(source.content).slice(0, 220) : "",
    score: typeof source.score === "number" ? source.score : undefined,
  }));
}

export function filesFromResult(toolName: string, args: Record<string, any>, result: any): OperationFile[] {
  const entries = Array.isArray(result?.entries) ? result.entries : fileEntries(result?.files);
  const files = entries.slice(0, 12).map((entry: any) => ({
    path: String(entry.path || entry.name || entry),
    kind: String(entry.kind || entry.type || ""),
    status: String(entry.status || ""),
  }));
  const targetPath = fileTarget(args);
  if (!files.length && targetPath) files.push({ path: String(targetPath), kind: isEditTool(toolName) ? "file" : "" });
  return files;
}

export function statsFromResult(result: any) {
  const meta = result?._meta;
  if (!meta || typeof meta !== "object") return undefined;
  return { duration_ms: meta.duration_ms, sandbox: meta.sandbox };
}

export function diffFromResult(result: any) {
  return result?.diff || result?._meta?.sandbox?.diff || undefined;
}

export function artifactsFromResult(result: any) {
  if (Array.isArray(result?.artifacts)) return result.artifacts;
  return result?.artifact ? [result.artifact] : [];
}

function fileEntries(value: any): any[] {
  if (Array.isArray(value)) return value;
  if (value && typeof value === "object") return Object.values(value);
  return [];
}

function domainFromUrl(url: string) {
  try {
    return new URL(String(url)).hostname.replace(/^www\./, "");
  } catch {
    return "";
  }
}
