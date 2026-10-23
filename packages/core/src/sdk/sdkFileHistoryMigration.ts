import { copyFile, link, mkdir, stat } from "node:fs/promises";
import path from "node:path";
import type { RunRecord, RuntimeEvent } from "../types/runtimeTypes.js";
import { resolveFileHistoryBackupPath } from "./sdkFileHistoryPaths.js";
import { fileHistorySnapshotFromPayload, fileHistorySnapshotPayload } from "./sdkFileHistorySnapshots.js";
import type { SdkFileHistorySnapshot } from "./sdkFileHistoryTypes.js";

export async function migrateFileHistoryEventsForSession(
  events: RuntimeEvent[],
  options: {
    runs: RunRecord[];
    sourceSessionId: string;
    targetSessionId: string;
  }
): Promise<RuntimeEvent[]> {
  if (options.sourceSessionId === options.targetSessionId) return events.map(cloneRuntimeEvent);
  const snapshotRecord = options.runs.at(-1) || fallbackRunRecord(options.sourceSessionId);
  const migrated: RuntimeEvent[] = [];
  for (const event of events) {
    const payload = fileHistorySnapshotPayload(event);
    const snapshot = payload ? fileHistorySnapshotFromPayload(payload, snapshotRecord) : undefined;
    if (!payload || !snapshot) {
      migrated.push(cloneRuntimeEvent(event));
      continue;
    }
    const targetRoot = await copyFileHistorySnapshotBackups(snapshot, {
      runs: options.runs,
      sourceSessionId: options.sourceSessionId,
      targetSessionId: options.targetSessionId
    });
    migrated.push(targetRoot
      ? withMigratedFileHistoryPayload(event, payload, options.targetSessionId, targetRoot)
      : cloneRuntimeEvent(event));
  }
  return migrated;
}

async function copyFileHistorySnapshotBackups(
  snapshot: SdkFileHistorySnapshot,
  options: {
    runs: RunRecord[];
    sourceSessionId: string;
    targetSessionId: string;
  }
): Promise<string | undefined> {
  const metadata = metadataForRuns(options.runs);
  const targetRoot = fileHistoryMigrationTargetRoot(snapshot, options.targetSessionId, metadata);
  try {
    await mkdir(targetRoot, { recursive: true });
    for (const backup of snapshot.backups.values()) {
      if (!backup.exists) continue;
      const source = resolveFileHistoryBackupPath(backup, snapshot, {
        runs: options.runs,
        sessionId: options.sourceSessionId,
        metadata
      });
      if (!source || !(await isFile(source))) return undefined;
      const targetName = backup.backupFileName || path.basename(source);
      await linkOrCopyFileHistoryBackup(source, path.join(targetRoot, targetName));
    }
  } catch {
    return undefined;
  }
  return targetRoot;
}

function fileHistoryMigrationTargetRoot(
  snapshot: SdkFileHistorySnapshot,
  targetSessionId: string,
  metadata: Record<string, string>
): string {
  if (snapshot.backupRoot) return path.join(path.dirname(path.resolve(snapshot.backupRoot)), targetSessionId);
  const configDir = String(metadata.claude_config_dir || metadata.claudeConfigDir || process.env.CLAUDE_CONFIG_DIR || "").trim()
    || path.join(String(metadata.sdk_cwd || metadata.cwd || process.cwd()), ".agents", "sdk");
  return path.join(path.resolve(configDir), "file-history", targetSessionId);
}

async function linkOrCopyFileHistoryBackup(source: string, target: string): Promise<void> {
  await mkdir(path.dirname(target), { recursive: true });
  if (await isFile(target)) return;
  try {
    await link(source, target);
  } catch {
    if (!(await isFile(target))) await copyFile(source, target);
  }
}

function withMigratedFileHistoryPayload(
  event: RuntimeEvent,
  payload: Record<string, unknown>,
  targetSessionId: string,
  targetRoot: string
): RuntimeEvent {
  const migratedPayload = migratedFileHistoryPayload(payload, targetSessionId, targetRoot);
  return {
    ...cloneRuntimeEvent(event),
    payload: migratedPayload,
    raw: isObject(event.raw) ? migratedFileHistoryPayload(event.raw, targetSessionId, targetRoot) : event.raw
  };
}

function migratedFileHistoryPayload(
  payload: Record<string, unknown>,
  targetSessionId: string,
  targetRoot: string
): Record<string, unknown> {
  const migrated: Record<string, unknown> = { ...payload, sessionId: targetSessionId, backupRoot: targetRoot };
  if (isObject(migrated.snapshot)) {
    migrated.snapshot = { ...migrated.snapshot, sessionId: targetSessionId, backupRoot: targetRoot };
  }
  return migrated;
}

async function isFile(filename: string): Promise<boolean> {
  return stat(filename).then((info) => info.isFile()).catch(() => false);
}

function cloneRuntimeEvent(event: RuntimeEvent): RuntimeEvent {
  return JSON.parse(JSON.stringify(event)) as RuntimeEvent;
}

function metadataForRuns(runs: RunRecord[]): Record<string, string> {
  return Object.assign({}, ...runs.map((run) => run.metadata));
}

function isObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function fallbackRunRecord(sessionId: string): RunRecord {
  return {
    run_id: sessionId,
    agent_id: "",
    tenant_id: "",
    user_id: "",
    workspace_id: "",
    status: "finished",
    events: [],
    created_at: 0,
    updated_at: 0,
    metadata: {},
    spec: {
      protocol: "",
      model: "",
      base_url: "",
      system_prompt: "",
      enabled_tools: [],
      permission_profile: "ask",
      approval_required_tools: [],
      denied_tools: [],
      tenant_id: "",
      user_id: "",
      agent_id: "",
      workspace_id: "",
      runtime: {},
      metadata: {}
    }
  };
}
