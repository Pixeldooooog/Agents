import { patchSchema } from "./patchSchema.js";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import type { JsonObject } from "../types/jsonTypes.js";
import { defineTool, type RegisteredTool, type ToolContext } from "./toolContracts.js";
import { ensureExistingFileReadIsCurrent, recordFileReadState } from "./fileReadState.js";
import { booleanArg, relativeWorkspacePath, resolveWorkspacePath, stringArg } from "./toolInputs.js";

export const patchToolDefinitions: RegisteredTool[] = [
  defineTool({
    name: "patch.apply",
    parameters: patchSchema,
    description: "Apply exact text edits to a workspace file.",
    risk: "medium",
    requires: [],
    uses: ["fileReadState"],
    handler: applyPatch
  })
];

async function applyPatch(context: ToolContext<never, "fileReadState">, args: JsonObject) {
  const requestedPath = stringArg(args.path);
  if (!requestedPath) throw new Error("path is required");
  const filePath = resolveWorkspacePath(context.repoRoot, requestedPath);
  const edits = normalizeEdits(args);
  if (!edits.length) throw new Error("at least one edit is required");
  let original = "";
  let existed = true;
  try {
    original = await readFile(filePath, "utf8");
  } catch {
    existed = false;
    if (!booleanArg(args.create)) throw new Error(`file not found: ${requestedPath}`);
  }
  if (existed) ensureExistingFileReadIsCurrent(context, filePath, original);
  let updated = original;
  for (const edit of edits) {
    if (edit.oldText === edit.newText) throw new Error("old_text and new_text must differ");
    if (!edit.oldText && original) throw new Error("old_text is required for existing files");
    if (!edit.oldText) {
      updated += edit.newText;
      continue;
    }
    const occurrences = countOccurrences(updated, edit.oldText);
    if (!occurrences) throw new Error(`old_text not found in ${requestedPath}`);
    if (occurrences > 1 && !edit.replaceAll) throw new Error("old_text matched multiple locations; set replace_all or provide more context");
    updated = edit.replaceAll ? updated.split(edit.oldText).join(edit.newText) : updated.replace(edit.oldText, edit.newText);
  }
  await mkdir(path.dirname(filePath), { recursive: true });
  await writeFile(filePath, updated);
  await recordFileReadState(context, filePath, updated, { source: "write" });
  const stats = lineChangeStats(original, updated);
  return {
    type: existed ? "update" : "create",
    filePath: relativeWorkspacePath(context.repoRoot, filePath),
    path: relativeWorkspacePath(context.repoRoot, filePath),
    editCount: edits.length,
    content: updated,
    originalFile: existed ? original : null,
    updatedFile: updated,
    insertions: stats.insertions,
    deletions: stats.deletions,
    originalBytes: Buffer.byteLength(original),
    updatedBytes: Buffer.byteLength(updated),
    encoding: "utf-8",
    safety: {
      requiredPriorRead: existed,
      staleChecked: existed,
      recordedRead: true
    }
  };
}

function normalizeEdits(args: JsonObject): Array<{ oldText: string; newText: string; replaceAll: boolean }> {
  if (Array.isArray(args.edits)) {
    return args.edits.map((item) => {
      const edit = item && typeof item === "object" ? item as JsonObject : {};
      return {
        oldText: stringArg(edit.old_text),
        newText: String(edit.new_text ?? ""),
        replaceAll: booleanArg(edit.replace_all)
      };
    });
  }
  return [{
    oldText: stringArg(args.old_text),
    newText: String(args.new_text ?? ""),
    replaceAll: booleanArg(args.replace_all)
  }];
}

function countOccurrences(content: string, needle: string): number {
  if (!needle) return 0;
  return content.split(needle).length - 1;
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
