import { filesystemReadSchema, filesystemListSchema, filesystemWriteSchema, filesystemDeleteSchema, filesystemMoveSchema } from "./filesystemSchemas.js";
import { mkdir, readdir, readFile, rm, stat, writeFile, rename } from "node:fs/promises";
import path from "node:path";
import type { JsonObject } from "../types/jsonTypes.js";
import type { ToolDefinition, ToolExecutionContext } from "./toolContracts.js";
import { ensureExistingFileReadIsCurrent, recordFileReadState } from "./fileReadState.js";
import { assertDirectory, assertFile, booleanArg, numberArg, relativeWorkspacePath, resolveWorkspacePath, stringArg } from "./toolInputs.js";

export const filesystemToolDefinitions: ToolDefinition[] = [
  {
    name: "filesystem.read",
    parameters: filesystemReadSchema,
    description: "Read a UTF-8 workspace file.",
    risk: "low",
    handler: readWorkspaceFile
  },
  {
    name: "filesystem.list",
    parameters: filesystemListSchema,
    description: "List workspace directory entries.",
    risk: "low",
    handler: listWorkspaceDirectory
  },
  {
    name: "filesystem.write",
    parameters: filesystemWriteSchema,
    description: "Create or replace a UTF-8 workspace file.",
    risk: "medium",
    handler: writeWorkspaceFile
  },
  {
    name: "filesystem.delete",
    parameters: filesystemDeleteSchema,
    description: "Delete a workspace file or directory.",
    risk: "medium",
    handler: deleteWorkspacePath
  },
  {
    name: "filesystem.move",
    parameters: filesystemMoveSchema,
    description: "Move or rename a workspace file or directory.",
    risk: "medium",
    handler: moveWorkspacePath
  }
];

async function readWorkspaceFile(context: ToolExecutionContext, args: JsonObject) {
  const requestedPath = stringArg(args.path);
  const filePath = await assertFile(context.repoRoot, requestedPath);
  const content = await readFile(filePath, "utf8");
  const lines = content.split(/\r?\n/);
  const offset = Math.max(0, numberArg(args.offset, 0));
  const limit = Math.max(0, numberArg(args.limit, 0));
  const selected = limit ? lines.slice(offset, offset + limit).join("\n") : content;
  if (!limit) {
    await recordFileReadState(context, filePath, content, { source: "read", offset: offset + 1, limit: null });
  }
  return {
    type: "text",
    file: {
      filePath: relativeWorkspacePath(context.repoRoot, filePath),
      content: selected,
      numLines: selected ? selected.split(/\r?\n/).length : 0,
      startLine: offset + 1,
      totalLines: lines.length
    },
    content: selected,
    isPartialView: Boolean(limit)
  };
}

async function listWorkspaceDirectory(context: ToolExecutionContext, args: JsonObject) {
  const directoryPath = await assertDirectory(context.repoRoot, stringArg(args.path, "."));
  const entries = await readdir(directoryPath, { withFileTypes: true });
  return {
    path: relativeWorkspacePath(context.repoRoot, directoryPath),
    entries: entries.slice(0, Math.max(1, numberArg(args.limit, 200))).map((entry) => ({
      name: entry.name,
      type: entry.isDirectory() ? "directory" : entry.isSymbolicLink() ? "symlink" : "file"
    }))
  };
}

async function writeWorkspaceFile(context: ToolExecutionContext, args: JsonObject) {
  const requestedPath = stringArg(args.path);
  const filePath = resolveWorkspacePath(context.repoRoot, requestedPath);
  const content = String(args.content ?? "");
  const originalFile = await readExistingTextFile(filePath);
  if (originalFile !== null) ensureExistingFileReadIsCurrent(context, filePath, originalFile);
  await mkdir(path.dirname(filePath), { recursive: true });
  await writeFile(filePath, content);
  await recordFileReadState(context, filePath, content, { source: "write" });
  return {
    type: originalFile === null ? "create" : "update",
    filePath: relativeWorkspacePath(context.repoRoot, filePath),
    path: relativeWorkspacePath(context.repoRoot, filePath),
    content,
    updatedFile: content,
    originalFile,
    bytes: Buffer.byteLength(content),
    encoding: "utf-8",
    safety: {
      requiredPriorRead: originalFile !== null,
      staleChecked: originalFile !== null,
      recordedRead: true
    }
  };
}

async function deleteWorkspacePath(context: ToolExecutionContext, args: JsonObject) {
  const requestedPath = stringArg(args.path);
  const targetPath = resolveWorkspacePath(context.repoRoot, requestedPath);
  const originalFile = await readExistingTextFileForDelete(targetPath);
  if (originalFile !== null) ensureExistingFileReadIsCurrent(context, targetPath, originalFile);
  await rm(targetPath, { recursive: booleanArg(args.recursive), force: booleanArg(args.force) });
  return {
    type: "delete",
    path: relativeWorkspacePath(context.repoRoot, targetPath),
    filePath: relativeWorkspacePath(context.repoRoot, targetPath),
    originalFile,
    encoding: "utf-8",
    safety: {
      requiredPriorRead: originalFile !== null,
      staleChecked: originalFile !== null
    }
  };
}

async function moveWorkspacePath(context: ToolExecutionContext, args: JsonObject) {
  const sourcePath = resolveWorkspacePath(context.repoRoot, stringArg(args.source));
  const targetPath = resolveWorkspacePath(context.repoRoot, stringArg(args.destination));
  await mkdir(path.dirname(targetPath), { recursive: true });
  await rename(sourcePath, targetPath);
  return {
    type: "move",
    source: relativeWorkspacePath(context.repoRoot, sourcePath),
    destination: relativeWorkspacePath(context.repoRoot, targetPath)
  };
}

async function readExistingTextFileForDelete(filePath: string): Promise<string | null> {
  try {
    const info = await stat(filePath);
    if (info.isDirectory()) return null;
    if (!info.isFile()) throw new Error(`not a file: ${filePath}`);
    return await readFile(filePath, "utf8");
  } catch (error) {
    if (isMissingPath(error)) return null;
    throw error;
  }
}

async function readExistingTextFile(filePath: string): Promise<string | null> {
  try {
    const info = await stat(filePath);
    if (!info.isFile()) throw new Error(`not a file: ${filePath}`);
    return await readFile(filePath, "utf8");
  } catch (error) {
    if (isMissingPath(error)) return null;
    throw error;
  }
}

function isMissingPath(error: unknown): boolean {
  return Boolean(error) && typeof error === "object" && (error as { code?: unknown }).code === "ENOENT";
}
