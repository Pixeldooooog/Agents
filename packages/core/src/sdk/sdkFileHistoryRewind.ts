import { readFile, stat } from "node:fs/promises";
import type { RunRecord } from "../types/runtimeTypes.js";
import { resolveWorkspacePath } from "../tools/toolInputs.js";
import { resolveFileHistoryBackupPath } from "./sdkFileHistoryPaths.js";
import { fileHistorySnapshotsFromRuns } from "./sdkFileHistorySnapshots.js";
import type { SdkFileHistoryBackupRef, SdkFileHistorySnapshot } from "./sdkFileHistoryTypes.js";

type FileHistoryRewindEntry = {
  path: string;
  before: string;
  beforeBytes?: Buffer;
  existed: boolean;
  encoding: string;
  insertions: number;
  deletions: number;
  mode?: number;
};

export async function rewindEntriesFromFileHistorySnapshots(
  runs: RunRecord[],
  userMessageId: string,
  repoRoot: string,
  sessionId: string
): Promise<{ entries: FileHistoryRewindEntry[]; unsupportedPaths: string[]; foundSnapshot: boolean }> {
  const snapshots = fileHistorySnapshotsFromRuns(runs);
  const targetSnapshot = lastSnapshotForMessage(snapshots, userMessageId);
  if (!targetSnapshot) return { entries: [], unsupportedPaths: [], foundSnapshot: false };
  const entries: FileHistoryRewindEntry[] = [];
  const unsupportedPaths = new Set<string>();
  const trackedPaths = [...new Set(snapshots.flatMap((snapshot) => [...snapshot.backups.keys()]))].sort();
  for (const trackedPath of trackedPaths) {
    const backup = targetSnapshot.backups.get(trackedPath) || firstBackupForPath(trackedPath, snapshots);
    if (!backup) continue;
    try {
      const entry = await rewindEntryFromFileHistoryBackup(trackedPath, backup, targetSnapshot, repoRoot, runs, sessionId);
      if (entry) entries.push(entry);
    } catch {
      unsupportedPaths.add(trackedPath);
    }
  }
  return { entries, unsupportedPaths: [...unsupportedPaths].sort(), foundSnapshot: true };
}

async function rewindEntryFromFileHistoryBackup(
  trackedPath: string,
  backup: SdkFileHistoryBackupRef,
  snapshot: SdkFileHistorySnapshot,
  repoRoot: string,
  runs: RunRecord[],
  sessionId: string
): Promise<FileHistoryRewindEntry | undefined> {
  const current = await readWorkspaceFile(repoRoot, trackedPath);
  if (!backup.exists) {
    if (!current) return undefined;
    const stats = lineChangeStatsFromBytes(current.bytes, Buffer.alloc(0));
    return {
      path: trackedPath,
      before: "",
      existed: false,
      encoding: "utf-8",
      insertions: stats.insertions,
      deletions: stats.deletions
    };
  }
  const backupPath = resolveFileHistoryBackupPath(backup, snapshot, {
    runs,
    sessionId,
    repoRoot,
    metadata: metadataForRuns(runs)
  });
  if (!backupPath) throw new Error(`file history backup not found: ${trackedPath}`);
  const [backupBytes, backupInfo] = await Promise.all([readFile(backupPath), stat(backupPath)]);
  if (current && Buffer.compare(current.bytes, backupBytes) === 0) return undefined;
  const backupText = decodeRewindBytes(backupBytes);
  const stats = lineChangeStatsFromBytes(current?.bytes, backupBytes);
  return {
    path: trackedPath,
    before: backupText,
    beforeBytes: backupBytes,
    existed: true,
    encoding: "utf-8",
    insertions: stats.insertions,
    deletions: stats.deletions,
    mode: backupInfo.mode
  };
}

function lastSnapshotForMessage(
  snapshots: SdkFileHistorySnapshot[],
  userMessageId: string
): SdkFileHistorySnapshot | undefined {
  return [...snapshots].reverse().find((snapshot) => snapshot.messageId === userMessageId);
}

function firstBackupForPath(
  trackedPath: string,
  snapshots: SdkFileHistorySnapshot[]
): SdkFileHistoryBackupRef | undefined {
  let fallback: SdkFileHistoryBackupRef | undefined;
  for (const snapshot of snapshots) {
    const backup = snapshot.backups.get(trackedPath);
    if (!backup) continue;
    fallback ??= backup;
    if (backup.version === 1) return backup;
  }
  return fallback;
}

function metadataForRuns(runs: RunRecord[]): Record<string, string> {
  return Object.assign({}, ...runs.map((run) => run.metadata));
}

async function readWorkspaceFile(repoRoot: string, trackedPath: string): Promise<{ bytes: Buffer } | undefined> {
  const target = resolveWorkspacePath(repoRoot, trackedPath);
  const info = await stat(target).catch(() => undefined);
  if (!info) return undefined;
  if (!info.isFile()) throw new Error(`rewind path is not a file: ${trackedPath}`);
  return { bytes: await readFile(target) };
}

function lineChangeStatsFromBytes(currentBytes: Buffer | undefined, backupBytes: Buffer): { insertions: number; deletions: number } {
  if (isLikelyBinary(currentBytes) || isLikelyBinary(backupBytes)) return { insertions: 0, deletions: 0 };
  return lineChangeStats(decodeRewindBytes(currentBytes || Buffer.alloc(0)), decodeRewindBytes(backupBytes));
}

function isLikelyBinary(bytes: Buffer | undefined): boolean {
  return bytes ? bytes.includes(0) : false;
}

function decodeRewindBytes(bytes: Buffer): string {
  return bytes.toString("utf8");
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
