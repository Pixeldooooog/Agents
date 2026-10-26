import { existsSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import type { RunRecord } from "../types/runtimeTypes.js";
import type { SdkFileHistoryBackupRef, SdkFileHistorySnapshot } from "./sdkFileHistoryTypes.js";

export type SdkFileHistoryBackupPathOptions = {
  runs: RunRecord[];
  sessionId: string;
  metadata?: Record<string, string>;
  configDir?: string;
  repoRoot?: string;
};

export function resolveFileHistoryBackupPath(
  backup: SdkFileHistoryBackupRef,
  snapshot: SdkFileHistorySnapshot,
  runsOrOptions: RunRecord[] | SdkFileHistoryBackupPathOptions,
  sessionId = ""
): string | undefined {
  if (backup.backupPath) return path.resolve(expandHome(backup.backupPath));
  const backupName = backup.backupFileName.trim();
  if (!backupName || path.isAbsolute(backupName) || backupName.includes("/") || backupName.includes("\\") || backupName.startsWith("..")) {
    return undefined;
  }
  const options = Array.isArray(runsOrOptions) ? { runs: runsOrOptions, sessionId } : runsOrOptions;
  const roots = fileHistoryBackupRoots(snapshot, options);
  for (const root of roots) {
    const candidate = path.join(root, backupName);
    if (existsSync(candidate)) return candidate;
  }
  return roots.length ? path.join(roots[0], backupName) : undefined;
}

function fileHistoryBackupRoots(snapshot: SdkFileHistorySnapshot, options: SdkFileHistoryBackupPathOptions): string[] {
  const metadata = options.metadata || {};
  const roots: string[] = [];
  if (snapshot.backupRoot) roots.push(path.resolve(expandHome(snapshot.backupRoot)));
  if (metadata.file_history_root || metadata.fileHistoryRoot) {
    roots.push(path.resolve(expandHome(String(metadata.file_history_root || metadata.fileHistoryRoot))));
  }
  const configDirs = uniqueStrings([
    metadata.claude_config_dir || "",
    metadata.claudeConfigDir || "",
    options.configDir || "",
    process.env.CLAUDE_CONFIG_DIR || "",
    options.repoRoot ? path.join(options.repoRoot, ".kevin", "sdk") : "",
    path.join(os.homedir(), ".claude")
  ]);
  const sessionIds = fileHistorySessionIds(snapshot, options);
  for (const configDir of configDirs) {
    for (const resolvedSessionId of sessionIds) {
      roots.push(path.join(path.resolve(expandHome(configDir)), "file-history", resolvedSessionId));
    }
  }
  return uniqueStrings(roots);
}

function fileHistorySessionIds(snapshot: SdkFileHistorySnapshot, options: SdkFileHistoryBackupPathOptions): string[] {
  const metadata = options.metadata || {};
  return uniqueStrings([
    snapshot.historySessionId,
    metadata.file_history_session_id || "",
    metadata.fileHistorySessionId || "",
    options.sessionId,
    ...options.runs.map((run) => run.metadata.sdk_file_history_session_id || run.metadata.file_history_session_id || run.metadata.fileHistorySessionId || run.metadata.sdk_session_id || run.run_id)
  ]);
}

function expandHome(value: string): string {
  if (value === "~") return os.homedir();
  return value.startsWith("~/") ? path.join(os.homedir(), value.slice(2)) : value;
}

function uniqueStrings(values: string[]): string[] {
  const seen = new Set<string>();
  const unique: string[] = [];
  for (const value of values) {
    const item = String(value || "").trim();
    if (!item || seen.has(item)) continue;
    seen.add(item);
    unique.push(item);
  }
  return unique;
}
