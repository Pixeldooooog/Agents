import type { RunRecord, RuntimeEvent } from "../types/runtimeTypes.js";
import type { SdkFileHistoryBackupRef, SdkFileHistorySnapshot } from "./sdkFileHistoryTypes.js";

export function fileHistorySnapshotsFromRuns(runs: RunRecord[]): SdkFileHistorySnapshot[] {
  const snapshots: SdkFileHistorySnapshot[] = [];
  const indexByMessageId = new Map<string, number>();
  for (const run of [...runs].sort((left, right) => left.created_at - right.created_at)) {
    for (const event of run.events) {
      const payload = fileHistorySnapshotPayload(event);
      if (!payload) continue;
      const snapshot = fileHistorySnapshotFromPayload(payload, run);
      if (!snapshot) continue;
      const isUpdate = Boolean(payload.isSnapshotUpdate || payload.is_snapshot_update);
      const existingIndex = isUpdate ? indexByMessageId.get(snapshot.messageId) : undefined;
      if (existingIndex === undefined) {
        indexByMessageId.set(snapshot.messageId, snapshots.length);
        snapshots.push(snapshot);
      } else {
        snapshots[existingIndex] = snapshot;
      }
    }
  }
  return snapshots;
}

export function fileHistorySnapshotPayload(event: RuntimeEvent): Record<string, unknown> | undefined {
  for (const candidate of [event.payload, event.raw]) {
    const payload = objectValue(candidate);
    if (payload.type === "file-history-snapshot" && isObject(payload.snapshot)) return payload;
    const raw = objectValue(payload.raw);
    if (raw.type === "file-history-snapshot" && isObject(raw.snapshot)) return raw;
  }
  if (event.type === "file-history-snapshot" && isObject(event.payload?.snapshot)) {
    return { ...objectValue(event.payload), type: "file-history-snapshot" };
  }
  return undefined;
}

export function fileHistorySnapshotFromPayload(
  payload: Record<string, unknown>,
  run: RunRecord
): SdkFileHistorySnapshot | undefined {
  const snapshotPayload = objectValue(payload.snapshot);
  const messageId = stringValue(
    snapshotPayload.messageId,
    snapshotPayload.message_id,
    payload.messageId,
    payload.message_id
  );
  if (!messageId) return undefined;
  const backupPayload = objectValue(snapshotPayload.trackedFileBackups);
  const snakeBackupPayload = objectValue(snapshotPayload.tracked_file_backups);
  const rawBackups = Object.keys(backupPayload).length ? backupPayload : snakeBackupPayload;
  if (!Object.keys(rawBackups).length) return undefined;
  const backups = new Map<string, SdkFileHistoryBackupRef>();
  for (const [trackedPath, backup] of Object.entries(rawBackups)) {
    const ref = fileHistoryBackupRef(backup);
    if (ref) backups.set(rewindPathValue(trackedPath), ref);
  }
  return {
    messageId,
    backups,
    backupRoot: stringValue(payload.backupRoot, payload.backup_root, snapshotPayload.backupRoot, snapshotPayload.backup_root),
    historySessionId: stringValue(
      payload.sessionId,
      payload.session_id,
      snapshotPayload.sessionId,
      snapshotPayload.session_id,
      run.metadata.sdk_file_history_session_id
    )
  };
}

function fileHistoryBackupRef(value: unknown): SdkFileHistoryBackupRef | undefined {
  const payload = objectValue(value);
  if (!Object.keys(payload).length) return undefined;
  const hasBackupName = Object.prototype.hasOwnProperty.call(payload, "backupFileName")
    || Object.prototype.hasOwnProperty.call(payload, "backup_file_name");
  const backupName = Object.prototype.hasOwnProperty.call(payload, "backupFileName")
    ? payload.backupFileName
    : payload.backup_file_name;
  const backupPath = stringValue(payload.backupPath, payload.backup_path);
  const backupTime = Object.prototype.hasOwnProperty.call(payload, "backupTime")
    ? payload.backupTime
    : payload.backup_time;
  if (backupName === null && hasBackupName) {
    return { exists: false, backupFileName: "", backupPath: "", version: integerValue(payload.version), backupTime };
  }
  if (typeof backupName === "string" && backupName) {
    return {
      exists: true,
      backupFileName: backupName,
      backupPath,
      version: integerValue(payload.version),
      backupTime
    };
  }
  if (backupPath) {
    return { exists: true, backupFileName: "", backupPath, version: integerValue(payload.version), backupTime };
  }
  return undefined;
}

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function isObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function stringValue(...values: unknown[]): string {
  for (const value of values) {
    const text = String(value || "").trim();
    if (text) return text;
  }
  return "";
}

function integerValue(value: unknown): number {
  const parsed = Number(value || 0);
  return Number.isInteger(parsed) ? parsed : 0;
}

function rewindPathValue(value: unknown): string {
  const text = String(value || "").trim();
  return text.startsWith("./") ? text.slice(2) : text;
}
