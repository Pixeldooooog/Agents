import type { OperationEvent, OperationFile, RunTraceResponse } from "../types/runtimeTypes";
import { operationFromFrame } from "./operationFrames";

export function projectRunTrace(trace: RunTraceResponse, fallbackRunId = ""): OperationEvent[] {
  const runId = trace.run_id || fallbackRunId;
  const snapshots = Array.isArray(trace.sandbox_snapshots) ? trace.sandbox_snapshots : [];
  const artifacts = Array.isArray(trace.artifacts) ? trace.artifacts : [];
  const frameEvents = Array.isArray(trace.operation_frames) ? trace.operation_frames.map((frame) => operationFromFrame(frame, runId)) : [];
  const events: OperationEvent[] = [...frameEvents];
  const latestSnapshot = snapshots[snapshots.length - 1];
  if (latestSnapshot) {
    events.push({
      id: `trace:snapshot:${latestSnapshot.snapshot_id || snapshots.length}`,
      runId,
      toolCallId: "",
      toolName: "workspace.snapshot",
      scene: "workspace",
      phase: "done",
      title: "Workspace snapshot captured",
      target: latestSnapshot.phase || "workspace",
      detail: `${latestSnapshot.file_count || 0} files · ${formatBytes(latestSnapshot.total_bytes || 0)}`,
      resultPreview: latestSnapshot.manifest,
      diffPreview: latestSnapshot.diff,
      artifacts,
      files: filesFromManifest(latestSnapshot.manifest),
      stats: { file_count: latestSnapshot.file_count || 0, total_bytes: latestSnapshot.total_bytes || 0 },
      endedAt: Date.now(),
    });
  }
  if (artifacts.length) {
    events.push({
      id: `trace:artifacts:${runId}:${artifacts.length}`,
      runId,
      toolCallId: "",
      toolName: "artifacts.collect",
      scene: "summary",
      phase: "done",
      title: "Artifacts collected",
      target: `${artifacts.length} artifact${artifacts.length > 1 ? "s" : ""}`,
      detail: "Run outputs are available in trace.",
      artifacts,
      endedAt: Date.now(),
    });
  }
  return events;
}

function filesFromManifest(manifest: any): OperationFile[] {
  const entries = fileEntries(manifest?.files || manifest);
  return entries.slice(0, 12).map((entry: any) => ({ path: String(entry.path || entry), kind: String(entry.kind || "") }));
}

function fileEntries(value: any): any[] {
  if (Array.isArray(value)) return value;
  if (value && typeof value === "object") return Object.values(value);
  return [];
}

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${Math.round(value / 1024)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}
