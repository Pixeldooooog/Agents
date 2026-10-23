import type { RuntimeEvent } from "../types/runtimeTypes.js";
import type { SdkFilesPersistedMessage } from "./sdkMessages.js";
import { objectValue, stringField } from "./sdkEventFields.js";
import { toolResultPayloadData } from "./sdkEventPayloads.js";

export function filesPersistedMessageFromRuntimeEvent(
  runId: string,
  sessionId: string,
  event: RuntimeEvent
): SdkFilesPersistedMessage | undefined {
  if (event.type !== "tool_result") return undefined;
  const data = toolResultPayloadData(objectValue(event.payload));
  const artifacts = artifactPayloads(data);
  const failed = artifactFailures(data);
  if (!artifacts.length && !failed.length) return undefined;
  return {
    type: "system",
    subtype: "files_persisted",
    runId,
    sessionId,
    files: artifacts.map((artifact) => ({
      filename: artifactFilename(artifact),
      fileId: stringField(artifact, "artifact_id", "file_id", "id")
    })),
    failed,
    processedAt: artifacts.map(artifactProcessedAt).find(Boolean) || new Date().toISOString()
  };
}

function artifactPayloads(payload: Record<string, unknown>): Array<Record<string, unknown>> {
  const artifacts: Array<Record<string, unknown>> = [];
  const artifact = objectValue(payload.artifact);
  if (Object.keys(artifact).length) artifacts.push(artifact);
  for (const key of ["artifacts", "files"]) {
    const values = payload[key];
    if (Array.isArray(values)) artifacts.push(...values.map(objectValue).filter((item) => Object.keys(item).length));
  }
  return artifacts.filter((artifact) => stringField(artifact, "artifact_id", "file_id", "id"));
}

function artifactFailures(payload: Record<string, unknown>): Array<{ filename: string; error: string }> {
  const values = payload.failed || payload.failed_files;
  if (!Array.isArray(values)) return [];
  return values.map(objectValue).map((item) => ({
    filename: stringField(item, "filename", "path", "uri"),
    error: stringField(item, "error", "message")
  }));
}

function artifactFilename(artifact: Record<string, unknown>): string {
  const filename = stringField(artifact, "filename", "workspace_path", "path");
  if (filename) return filename;
  const uri = stringField(artifact, "uri");
  if (uri) return uri.split("/").at(-1) || uri;
  return stringField(artifact, "artifact_id", "file_id", "id") || "artifact";
}

function artifactProcessedAt(artifact: Record<string, unknown>): string {
  const value = artifact.processed_at ?? artifact.created_at;
  if (typeof value === "string") return value;
  if (typeof value === "number" && value > 0) return new Date(value < 1_000_000_000_000 ? value * 1000 : value).toISOString();
  return "";
}
