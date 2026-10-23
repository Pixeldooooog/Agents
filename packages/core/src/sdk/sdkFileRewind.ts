import { chmod, mkdir, rm, stat, writeFile } from "node:fs/promises";
import path from "node:path";
import type { JsonStateStore } from "../store/jsonStateStore.js";
import type { RunRecord, RuntimeEvent } from "../types/runtimeTypes.js";
import { resolveWorkspacePath } from "../tools/toolInputs.js";
import { eventMatchesMessageId, runMatchesSdkUserMessage } from "./sdkEventIdentity.js";
import { toolResultPayloadData } from "./sdkEventPayloads.js";
import { rewindEntriesFromFileHistorySnapshots } from "./sdkFileHistoryRewind.js";
import { listSdkSessionRuns } from "./sdkSessionRecords.js";

export type SdkFileRewindOptions = {
  store: JsonStateStore;
  repoRoot: string;
  sessionId: string;
  userMessageId: string;
  dryRun?: boolean;
};

export type RewindFileEntry = {
  path: string;
  before: string;
  beforeBytes?: Buffer;
  existed: boolean;
  encoding: string;
  insertions: number;
  deletions: number;
  mode?: number;
};

export async function rewindSdkFiles(options: SdkFileRewindOptions): Promise<Record<string, unknown>> {
  const sessionId = options.sessionId.trim();
  if (!sessionId) return { canRewind: false, error: "sessionId is required for rewind_files" };
  const runs = (await listSdkSessionRuns(options.store, sessionId)).sort((left, right) => left.created_at - right.created_at);
  if (!runs.length) return { canRewind: false, error: `session not found: ${sessionId}` };
  const snapshotScan = await rewindEntriesFromFileHistorySnapshots(runs, options.userMessageId, options.repoRoot, sessionId);
  if (snapshotScan.foundSnapshot) {
    if (snapshotScan.unsupportedPaths.length) {
      return {
        canRewind: false,
        error: `File history backup is incomplete for: ${snapshotScan.unsupportedPaths.join(", ")}`
      };
    }
    const payload = rewindResponsePayload(snapshotScan.entries);
    if (options.dryRun) return payload;
    try {
      for (const entry of snapshotScan.entries) await applyRewindEntry(options.repoRoot, entry);
    } catch (error) {
      return { canRewind: false, error: `Failed to rewind: ${errorMessage(error)}` };
    }
    return { canRewind: true };
  }
  const scan = rewindEntriesAfterMessage(runs, options.userMessageId);
  if (!scan.foundMessage) return { canRewind: false, error: `No user message found for id: ${options.userMessageId}` };
  if (scan.unsupportedPaths.length) {
    return {
      canRewind: false,
      error: `File history is incomplete for: ${scan.unsupportedPaths.join(", ")}`
    };
  }
  if (!scan.entries.length) return { canRewind: false, error: "No file checkpoint found for this message." };
  const payload = rewindResponsePayload(scan.entries);
  if (options.dryRun) return payload;
  try {
    for (const entry of scan.entries) await applyRewindEntry(options.repoRoot, entry);
  } catch (error) {
    return { canRewind: false, error: `Failed to rewind: ${errorMessage(error)}` };
  }
  return { canRewind: true };
}

function rewindEntriesAfterMessage(runs: RunRecord[], userMessageId: string): {
  entries: RewindFileEntry[];
  unsupportedPaths: string[];
  foundMessage: boolean;
} {
  let foundMessage = false;
  const entriesByPath = new Map<string, RewindFileEntry>();
  const unsupportedPaths = new Set<string>();
  const readCache = new Map<string, string>();
  for (const run of runs) {
    if (!foundMessage && runMatchesSdkUserMessage(run, userMessageId)) foundMessage = true;
    for (const event of run.events) {
      if (!foundMessage) {
        if (eventMatchesMessageId(event, userMessageId)) foundMessage = true;
        continue;
      }
      if (event.type !== "tool_result" || event.payload?.is_error === true) continue;
      const payload = toolResultData(event);
      const read = readContentFromToolResult(event, payload);
      if (read) {
        readCache.set(read.path, read.content);
        continue;
      }
      const parsed = rewindEntriesFromToolResult(event, payload, readCache);
      for (const path of parsed.unsupportedPaths) {
        if (!entriesByPath.has(path)) unsupportedPaths.add(path);
      }
      for (const entry of parsed.entries) {
        if (unsupportedPaths.has(entry.path)) continue;
        const existing = entriesByPath.get(entry.path);
        if (!existing) {
          entriesByPath.set(entry.path, entry);
          continue;
        }
        existing.insertions += entry.insertions;
        existing.deletions += entry.deletions;
      }
    }
  }
  return {
    entries: [...entriesByPath.values()].sort((left, right) => left.path.localeCompare(right.path)),
    unsupportedPaths: [...unsupportedPaths].sort(),
    foundMessage
  };
}

export function readContentFromToolResult(event: RuntimeEvent, payload: Record<string, unknown>): { path: string; content: string } | undefined {
  if (!["filesystem.read", "Read"].includes(event.name || "")) return undefined;
  if (payload.truncated || payload.isPartialView) return undefined;
  const file = objectValue(payload.file);
  const filePath = rewindPathValue(file.filePath || file.file_path || payload.path || payload.file_path);
  const content = typeof file.content === "string" ? file.content : payload.content;
  if (!filePath || typeof content !== "string") return undefined;
  return { path: filePath, content };
}

export function rewindEntriesFromToolResult(
  event: RuntimeEvent,
  payload: Record<string, unknown>,
  readCache: Map<string, string>
): { entries: RewindFileEntry[]; unsupportedPaths: string[] } {
  if (payload.dry_run === true || payload.changed === false) return { entries: [], unsupportedPaths: [] };
  const toolName = event.name || "";
  if (["patch.apply", "Edit"].includes(toolName)) return entryFromPatchPayload(payload);
  if (["notebook.edit", "NotebookEdit"].includes(toolName)) {
    const entry = entryFromNotebookPayload(payload);
    return { entries: entry ? [entry] : [], unsupportedPaths: [] };
  }
  if (["filesystem.write", "filesystem.delete", "Write"].includes(toolName)) {
    const parsed = entryFromWritePayload(payload, readCache);
    return { entries: parsed.entry ? [parsed.entry] : [], unsupportedPaths: parsed.unsupportedPaths };
  }
  return { entries: [], unsupportedPaths: [] };
}

function entryFromPatchPayload(payload: Record<string, unknown>): { entries: RewindFileEntry[]; unsupportedPaths: string[] } {
  const entries: RewindFileEntry[] = [];
  const supportedPaths = new Set<string>();
  const unsupportedPaths = new Set<string>();
  const pathValue = rewindPathValue(payload.filePath || payload.path);
  const original = payload.originalFile;
  if (pathValue && (typeof original === "string" || original === null)) {
    const before = typeof original === "string" ? original : "";
    entries.push(rewindEntry(pathValue, before, original !== null, payload, patchAfterContent(payload, before)));
    supportedPaths.add(pathValue);
  }

  const files = Array.isArray(payload.files) ? payload.files : [];
  for (const item of files) {
    const file = objectValue(item);
    const itemPath = rewindPathValue(file.path || file.filePath);
    if (!itemPath || supportedPaths.has(itemPath)) continue;
    const action = String(file.action || "");
    if (action === "create") {
      entries.push(rewindEntry(itemPath, "", false, { ...payload, structuredPatch: structuredPatchForPath(payload, itemPath) }));
      supportedPaths.add(itemPath);
    } else if (action === "edit") {
      unsupportedPaths.add(itemPath);
    }
  }

  if (!files.length && Array.isArray(payload.structuredPatches) && !supportedPaths.size) {
    for (const item of payload.structuredPatches) {
      const structuredPatch = objectValue(item);
      const itemPath = rewindPathValue(structuredPatch.filePath || structuredPatch.path);
      if (itemPath) unsupportedPaths.add(itemPath);
    }
  }

  if (pathValue && !supportedPaths.has(pathValue) && !unsupportedPaths.has(pathValue)) unsupportedPaths.add(pathValue);
  return { entries, unsupportedPaths: [...unsupportedPaths].sort() };
}

function entryFromNotebookPayload(payload: Record<string, unknown>): RewindFileEntry | undefined {
  const pathValue = rewindPathValue(payload.notebook_path || payload.path || payload.filePath);
  const original = payload.original_file ?? payload.originalFile;
  const updated = firstString(payload, "updated_file", "updatedFile");
  return pathValue && typeof original === "string" ? rewindEntry(pathValue, original, true, payload, updated) : undefined;
}

function entryFromWritePayload(
  payload: Record<string, unknown>,
  readCache: Map<string, string>
): { entry?: RewindFileEntry; unsupportedPaths: string[] } {
  const file = objectValue(payload.file);
  const pathValue = rewindPathValue(payload.path || payload.filePath || payload.file_path || file.filePath || file.file_path);
  if (!pathValue) return { unsupportedPaths: [] };
  const original = firstPresent(payload, "originalFile", "original_file", "oldContent", "old_content");
  const safety = objectValue(payload.safety);
  const encoding = String(payload.encoding || payload.charset || safety.encoding || "utf-8");
  const after = firstString(payload, "content", "updatedFile", "updated_file", "newContent", "new_content");
  if (original.found) {
    return {
      entry: rewindEntry(pathValue, typeof original.value === "string" ? original.value : "", typeof original.value === "string", {
        ...payload,
        encoding
      }, after),
      unsupportedPaths: []
    };
  }
  if (String(payload.type || "").toLowerCase() === "create") {
    return { entry: rewindEntry(pathValue, "", false, { ...payload, encoding }, after), unsupportedPaths: [] };
  }
  if (!booleanValue(safety.requiredPriorRead ?? safety.required_prior_read)) {
    return { entry: rewindEntry(pathValue, "", false, { ...payload, encoding }, after), unsupportedPaths: [] };
  }
  const cached = readCache.get(pathValue);
  if (cached === undefined) return { unsupportedPaths: [pathValue] };
  return { entry: rewindEntry(pathValue, cached, true, { ...payload, encoding }, after), unsupportedPaths: [] };
}

function rewindEntry(
  pathValue: string,
  before: string,
  existed: boolean,
  payload: Record<string, unknown>,
  afterOverride?: string
): RewindFileEntry {
  const updated = afterOverride ?? firstString(payload, "updatedFile", "updated_file", "content", "newContent", "new_content");
  const stats = changeStats(payload.structuredPatch, before, updated);
  return {
    path: pathValue,
    before,
    existed,
    encoding: typeof payload.encoding === "string" ? payload.encoding : "utf-8",
    insertions: numberValue(payload.insertions, stats.insertions),
    deletions: numberValue(payload.deletions, stats.deletions)
  };
}

function rewindResponsePayload(entries: RewindFileEntry[]): Record<string, unknown> {
  const ordered = [...entries].sort((left, right) => left.path.localeCompare(right.path));
  return {
    canRewind: true,
    filesChanged: ordered.map((entry) => entry.path),
    insertions: ordered.reduce((total, entry) => total + Math.max(0, entry.insertions), 0),
    deletions: ordered.reduce((total, entry) => total + Math.max(0, entry.deletions), 0)
  };
}

async function applyRewindEntry(repoRoot: string, entry: RewindFileEntry): Promise<void> {
  const target = resolveWorkspacePath(repoRoot, entry.path);
  if (!entry.existed) {
    const info = await stat(target).catch(() => undefined);
    if (info?.isDirectory()) throw new Error(`cannot rewind file path because it is a directory: ${entry.path}`);
    await rm(target, { force: true });
    return;
  }
  await mkdir(path.dirname(target), { recursive: true });
  if (entry.beforeBytes) await writeFile(target, entry.beforeBytes);
  else await writeFile(target, entry.before, { encoding: entry.encoding as BufferEncoding });
  if (entry.mode !== undefined) await chmod(target, entry.mode).catch(() => undefined);
}

export function toolResultData(event: RuntimeEvent): Record<string, unknown> {
  const parsed = toolResultPayloadData(objectValue(event.payload));
  const nested = objectValue(parsed.data);
  if (!Object.keys(nested).length) return parsed;
  return parsed._meta === undefined ? nested : { ...nested, _meta: parsed._meta };
}

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function rewindPathValue(value: unknown): string {
  const text = String(value || "").trim();
  return text.startsWith("./") ? text.slice(2) : text;
}

function firstString(payload: Record<string, unknown>, ...keys: string[]): string | undefined {
  for (const key of keys) {
    if (typeof payload[key] === "string") return payload[key] as string;
  }
  return undefined;
}

function firstPresent(payload: Record<string, unknown>, ...keys: string[]): { found: boolean; value: unknown } {
  for (const key of keys) {
    if (Object.prototype.hasOwnProperty.call(payload, key)) return { found: true, value: payload[key] };
  }
  return { found: false, value: undefined };
}

function booleanValue(value: unknown): boolean {
  if (typeof value === "boolean") return value;
  if (typeof value === "number") return value !== 0;
  return !["", "0", "false", "no", "off"].includes(String(value || "").trim().toLowerCase());
}

function numberValue(value: unknown, fallback: number): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function patchAfterContent(payload: Record<string, unknown>, before: string): string | undefined {
  const oldString = payload.oldString;
  const newString = payload.newString;
  if (typeof oldString === "string" && typeof newString === "string" && before.includes(oldString)) {
    return before.replace(oldString, newString);
  }
  return undefined;
}

function structuredPatchForPath(payload: Record<string, unknown>, pathValue: string): unknown {
  if (!Array.isArray(payload.structuredPatches)) return undefined;
  for (const item of payload.structuredPatches) {
    const structuredPatch = objectValue(item);
    const itemPath = rewindPathValue(structuredPatch.filePath || structuredPatch.path);
    if (itemPath === pathValue && Array.isArray(structuredPatch.hunks)) return structuredPatch.hunks;
  }
  return undefined;
}

function changeStats(patch: unknown, before: string, after: string | undefined): { insertions: number; deletions: number } {
  const structuredStats = structuredPatchStats(patch);
  if (structuredStats.insertions || structuredStats.deletions || after === undefined) return structuredStats;
  return lineChangeStats(before, after);
}

function structuredPatchStats(patch: unknown): { insertions: number; deletions: number } {
  if (!Array.isArray(patch)) return { insertions: 0, deletions: 0 };
  let insertions = 0;
  let deletions = 0;
  for (const hunk of patch) {
    const lines = objectValue(hunk).lines;
    if (!Array.isArray(lines)) continue;
    for (const line of lines) {
      const text = String(line);
      if (text.startsWith("+")) insertions += 1;
      else if (text.startsWith("-")) deletions += 1;
    }
  }
  return { insertions, deletions };
}

function lineChangeStats(before: string, after: string): { insertions: number; deletions: number } {
  const beforeLines = before ? before.split(/\r?\n/) : [];
  const afterLines = after ? after.split(/\r?\n/) : [];
  let prefix = 0;
  while (prefix < beforeLines.length && prefix < afterLines.length && beforeLines[prefix] === afterLines[prefix]) {
    prefix += 1;
  }
  let suffix = 0;
  while (
    suffix < beforeLines.length - prefix &&
    suffix < afterLines.length - prefix &&
    beforeLines[beforeLines.length - 1 - suffix] === afterLines[afterLines.length - 1 - suffix]
  ) {
    suffix += 1;
  }
  return {
    deletions: beforeLines.length - prefix - suffix,
    insertions: afterLines.length - prefix - suffix
  };
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
