import { readFile, writeFile } from "node:fs/promises";
import type { JsonObject } from "../types/jsonTypes.js";
import { defineTool, type RegisteredTool, type ToolContext } from "../tools/toolContracts.js";
import { relativeWorkspacePath, resolveWorkspacePath, stringArg } from "../tools/toolInputs.js";
import {
  applyNotebookCellEdit,
  notebookCellSource,
  notebookCells,
  notebookLanguage,
  notebookResultCellType,
  normalizeNotebookCellType,
  normalizeNotebookEditMode,
  parseNotebook,
  resolveNotebookCellIndex
} from "./notebookRecords.js";

const notebookEditSchema = {
  type: "object",
  properties: {
    notebook_path: { type: "string" },
    new_source: { type: "string" },
    cell_id: { type: "string" },
    cell_type: { type: "string", enum: ["code", "markdown"] },
    edit_mode: { type: "string", enum: ["replace", "insert", "delete"] }
  },
  required: ["notebook_path", "new_source"]
};

export const notebookToolDefinitions: RegisteredTool[] = [
  defineTool({
    name: "notebook.edit",
    description: "Edit a specific cell in a Jupyter notebook.",
    risk: "medium",
    parameters: notebookEditSchema,
    requires: [],
    handler: notebookEdit
  })
];

async function notebookEdit(context: ToolContext, args: JsonObject) {
  const requestedPath = stringArg(args.notebook_path);
  if (!requestedPath.endsWith(".ipynb")) throw new Error("File must be a Jupyter notebook (.ipynb file).");
  const notebookPath = resolveWorkspacePath(context.repoRoot, requestedPath);
  const originalFile = await readFile(notebookPath, "utf8");
  const notebook = parseNotebook(originalFile);
  const cells = notebookCells(notebook);
  const mode = normalizeNotebookEditMode(stringArg(args.edit_mode, "replace"));
  const cellIndex = resolveNotebookCellIndex(cells, stringArg(args.cell_id), mode);
  const oldCellSource = mode === "insert" ? "" : notebookCellSource(cells[cellIndex]);
  const cellType = args.cell_type === undefined ? undefined : normalizeNotebookCellType(stringArg(args.cell_type));
  const newSource = stringArg(args.new_source);
  const cellId = applyNotebookCellEdit(notebook, cellIndex, stringArg(args.cell_id), newSource, cellType, mode);
  const updatedFile = `${JSON.stringify(notebook, null, 1)}\n`;
  await writeFile(notebookPath, updatedFile);
  const resultCellType = cellType || notebookResultCellType(cells, cellIndex, mode);
  return {
    new_source: newSource,
    cell_id: cellId,
    cell_type: resultCellType,
    language: notebookLanguage(notebook),
    edit_mode: mode,
    error: "",
    notebook_path: relativeWorkspacePath(context.repoRoot, notebookPath),
    cell_index: cellIndex,
    old_source: oldCellSource,
    updated_source: mode === "delete" ? "" : newSource,
    original_file: originalFile,
    updated_file: updatedFile,
    bytes: Buffer.byteLength(updatedFile),
    encoding: "utf8"
  };
}
