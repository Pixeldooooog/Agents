import { stat } from "node:fs/promises";
import type { FileReadStateRecord, ToolExecutionContext } from "./toolContracts.js";
import { relativeWorkspacePath } from "./toolInputs.js";

export const PRE_READ_REQUIRED_ERROR = "File has not been read yet. Read it first before writing to it.";
export const STALE_FILE_ERROR = "File has been modified since read, either by the user or by a linter. Read it again before attempting to write it.";

export type FileReadStateOptions = {
  encoding?: string;
  source?: "read" | "write";
  offset?: number;
  limit?: number | null;
  isPartialView?: boolean;
  timestamp?: number;
};

export async function recordFileReadState(
  context: ToolExecutionContext,
  absolutePath: string,
  content: string,
  options: FileReadStateOptions = {}
): Promise<FileReadStateRecord | undefined> {
  if (!context.fileReadState) return undefined;
  const relativePath = relativeWorkspacePath(context.repoRoot, absolutePath);
  const record: FileReadStateRecord = {
    path: relativePath,
    content,
    timestamp: options.timestamp ?? await fileMtime(absolutePath),
    encoding: options.encoding || "utf-8",
    fullRead: !options.isPartialView,
    source: options.source || "read",
    offset: options.offset ?? 1,
    limit: options.limit ?? null,
    isPartialView: Boolean(options.isPartialView)
  };
  context.fileReadState[relativePath] = record;
  return record;
}

export function ensureExistingFileReadIsCurrent(
  context: ToolExecutionContext,
  absolutePath: string,
  currentContent: string
): string {
  const relativePath = relativeWorkspacePath(context.repoRoot, absolutePath);
  const record = context.fileReadState?.[relativePath];
  if (!record || !record.fullRead) throw new Error(PRE_READ_REQUIRED_ERROR);
  if (record.content !== currentContent) throw new Error(STALE_FILE_ERROR);
  return relativePath;
}

async function fileMtime(absolutePath: string): Promise<number> {
  return (await stat(absolutePath)).mtimeMs;
}
