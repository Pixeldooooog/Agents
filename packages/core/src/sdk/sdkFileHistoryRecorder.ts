import { createHash } from "node:crypto";
import { chmod, copyFile, mkdir, readFile, readdir, stat, writeFile } from "node:fs/promises";
import path from "node:path";
import type { RunRecord, RuntimeEvent } from "../types/runtimeTypes.js";
import { resolveWorkspacePath } from "../tools/toolInputs.js";
import { resolveFileHistoryBackupPath } from "./sdkFileHistoryPaths.js";
import { fileHistorySnapshotsFromRuns } from "./sdkFileHistorySnapshots.js";
import type { SdkFileHistoryBackupRef, SdkFileHistorySnapshot } from "./sdkFileHistoryTypes.js";
import {
  readContentFromToolResult,
  rewindEntriesFromToolResult,
  toolResultData,
  type RewindFileEntry
} from "./sdkFileRewind.js";

export type SdkFileHistoryRecorderOptions = {
  repoRoot: string;
  sessionId: string;
  messageId: string;
  metadata?: Record<string, string>;
  runs?: RunRecord[];
};

export class SdkFileHistoryRecorder {
  private readonly backups: Record<string, Record<string, unknown>> = {};
  private readonly readCache = new Map<string, string>();

  constructor(
    private readonly repoRoot: string,
    private readonly configDir: string,
    private readonly sessionId: string,
    private readonly messageId: string,
    private readonly metadata: Record<string, string> = {}
  ) {}

  get backupRoot(): string {
    return path.join(this.configDir, "file-history", this.sessionId);
  }

  async seedFromPrevious(runs: RunRecord[]): Promise<void> {
    const snapshots = fileHistorySnapshotsFromRuns(runs);
    const trackedPaths = [...new Set(snapshots.flatMap((snapshot) => [...snapshot.backups.keys()]))].sort();
    for (const trackedPath of trackedPaths) {
      const latest = latestBackupForPath(trackedPath, snapshots);
      if (!latest) continue;
      try {
        this.backups[trackedPath] = await this.seedBackupPayload(trackedPath, latest.backup, latest.snapshot, runs);
      } catch {
        continue;
      }
    }
  }

  initialEvent(): RuntimeEvent {
    return this.snapshotEvent(false);
  }

  async observe(event: RuntimeEvent): Promise<RuntimeEvent[]> {
    if (event.type !== "tool_result") return [];
    const payload = toolResultData(event);
    const read = readContentFromToolResult(event, payload);
    if (read) {
      this.readCache.set(read.path, read.content);
      return [];
    }
    const parsed = rewindEntriesFromToolResult(event, payload, this.readCache);
    let changed = false;
    for (const entry of parsed.entries) {
      if (this.backups[entry.path]) continue;
      try {
        this.backups[entry.path] = await this.backupPayload(entry);
      } catch {
        continue;
      }
      changed = true;
    }
    return changed ? [this.snapshotEvent(true)] : [];
  }

  private async backupPayload(entry: RewindFileEntry): Promise<Record<string, unknown>> {
    const backup = backupPayloadBase(1);
    if (!entry.existed) return backup;
    const target = resolveWorkspacePath(this.repoRoot, entry.path);
    const version = await nextBackupVersion(this.backupRoot, target);
    const backupName = fileHistoryBackupName(target, version);
    await mkdir(this.backupRoot, { recursive: true });
    const backupPath = path.join(this.backupRoot, backupName);
    await writeFile(backupPath, entry.before, { encoding: entry.encoding as BufferEncoding });
    const targetMode = await stat(target).then((info) => info.mode).catch(() => undefined);
    if (targetMode !== undefined) await chmod(backupPath, targetMode).catch(() => undefined);
    backup.backupFileName = backupName;
    backup.version = version;
    return backup;
  }

  private async seedBackupPayload(
    trackedPath: string,
    latestBackup: SdkFileHistoryBackupRef,
    snapshot: SdkFileHistorySnapshot,
    runs: RunRecord[]
  ): Promise<Record<string, unknown>> {
    const target = resolveWorkspacePath(this.repoRoot, trackedPath);
    const nextVersion = Math.max(1, Number(latestBackup.version || 0) + 1);
    const targetInfo = await stat(target).catch(() => undefined);
    if (!targetInfo) return backupPayloadBase(nextVersion);
    if (!targetInfo.isFile()) throw new Error(`file history path is not a file: ${trackedPath}`);
    if (latestBackup.exists) {
      const backupPath = resolveFileHistoryBackupPath(latestBackup, snapshot, {
        runs,
        sessionId: this.sessionId,
        metadata: this.metadata,
        configDir: this.configDir,
        repoRoot: this.repoRoot
      });
      if (backupPath) {
        const [currentBytes, backupBytes] = await Promise.all([
          readFile(target),
          readFile(backupPath).catch(() => undefined)
        ]);
        if (backupBytes && Buffer.compare(currentBytes, backupBytes) === 0) return backupPayloadFromRef(latestBackup);
      }
    }
    return this.backupCurrentFilePayload(target, nextVersion);
  }

  private async backupCurrentFilePayload(target: string, version: number): Promise<Record<string, unknown>> {
    const backup = backupPayloadBase(version);
    const backupName = fileHistoryBackupName(target, version);
    const backupPath = path.join(this.backupRoot, backupName);
    await mkdir(this.backupRoot, { recursive: true });
    await copyFile(target, backupPath);
    const targetMode = await stat(target).then((info) => info.mode).catch(() => undefined);
    if (targetMode !== undefined) await chmod(backupPath, targetMode).catch(() => undefined);
    backup.backupFileName = backupName;
    return backup;
  }

  private snapshotEvent(isSnapshotUpdate: boolean): RuntimeEvent {
    return {
      type: "file-history-snapshot",
      name: "file-history",
      payload: {
        type: "file-history-snapshot",
        messageId: this.messageId,
        sessionId: this.sessionId,
        backupRoot: this.backupRoot,
        snapshot: {
          messageId: this.messageId,
          trackedFileBackups: { ...this.backups },
          timestamp: new Date().toISOString()
        },
        isSnapshotUpdate
      }
    };
  }
}

export async function createSdkFileHistoryRecorder(
  options: SdkFileHistoryRecorderOptions
): Promise<SdkFileHistoryRecorder | undefined> {
  if (!options.messageId || !sdkFileHistoryEnabled(options.metadata)) return undefined;
  const recorder = new SdkFileHistoryRecorder(
    options.repoRoot,
    sdkFileHistoryConfigDir(options.repoRoot, options.metadata),
    options.sessionId,
    options.messageId,
    options.metadata || {}
  );
  await recorder.seedFromPrevious(options.runs || []);
  return recorder;
}

export function sdkFileHistoryEnabled(metadata: Record<string, string> | undefined): boolean {
  const values = metadata || {};
  for (const key of ["file_history_enabled", "fileHistoryEnabled", "fileCheckpointingEnabled"]) {
    if (Object.prototype.hasOwnProperty.call(values, key)) return truthyMetadataValue(values[key]);
  }
  return true;
}

function sdkFileHistoryConfigDir(repoRoot: string, metadata: Record<string, string> | undefined): string {
  const values = metadata || {};
  return path.resolve(String(values.claude_config_dir || values.claudeConfigDir || path.join(repoRoot, ".agents", "sdk")));
}

function latestBackupForPath(
  trackedPath: string,
  snapshots: SdkFileHistorySnapshot[]
): { snapshot: SdkFileHistorySnapshot; backup: SdkFileHistoryBackupRef } | undefined {
  for (const snapshot of [...snapshots].reverse()) {
    const backup = snapshot.backups.get(trackedPath);
    if (backup) return { snapshot, backup };
  }
  return undefined;
}

async function nextBackupVersion(backupRoot: string, target: string): Promise<number> {
  const digest = fileHistoryPathDigest(target);
  const entries = await readdir(backupRoot).catch(() => []);
  let highest = 0;
  for (const entry of entries) {
    if (!entry.startsWith(`${digest}@v`)) continue;
    const parsed = Number(entry.split("@v").at(-1));
    if (Number.isInteger(parsed)) highest = Math.max(highest, parsed);
  }
  return highest + 1;
}

function fileHistoryBackupName(target: string, version: number): string {
  return `${fileHistoryPathDigest(target)}@v${Math.max(1, Math.trunc(version || 1))}`;
}

function fileHistoryPathDigest(target: string): string {
  return createHash("sha256").update(String(target)).digest("hex").slice(0, 16);
}

function backupPayloadBase(version: number): Record<string, unknown> {
  return {
    backupFileName: null,
    version: Math.max(1, Math.trunc(version || 1)),
    backupTime: new Date().toISOString()
  };
}

function backupPayloadFromRef(ref: SdkFileHistoryBackupRef): Record<string, unknown> {
  const payload = backupPayloadBase(ref.version || 1);
  if (!ref.exists) payload.backupFileName = null;
  else if (ref.backupFileName) payload.backupFileName = ref.backupFileName;
  else if (ref.backupPath) payload.backupPath = ref.backupPath;
  if (ref.backupTime !== undefined) payload.backupTime = ref.backupTime;
  return payload;
}

function truthyMetadataValue(value: unknown): boolean {
  if (typeof value === "boolean") return value;
  if (typeof value === "number") return value !== 0;
  return !["", "0", "false", "no", "off"].includes(String(value || "").trim().toLowerCase());
}
