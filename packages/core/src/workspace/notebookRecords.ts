export type NotebookDocument = Record<string, unknown>;
export type NotebookCell = Record<string, unknown>;
export type NotebookEditMode = "replace" | "insert" | "delete";
export type NotebookCellType = "code" | "markdown";

export function parseNotebook(content: string): NotebookDocument {
  const notebook = JSON.parse(content);
  if (!notebook || typeof notebook !== "object" || Array.isArray(notebook)) throw new Error("Notebook is not valid JSON.");
  return notebook as NotebookDocument;
}

export function notebookCells(notebook: NotebookDocument): NotebookCell[] {
  const cells = notebook.cells;
  if (!Array.isArray(cells) || !cells.every((cell) => cell && typeof cell === "object" && !Array.isArray(cell))) {
    throw new Error("Notebook cells must be a list of objects.");
  }
  return cells as NotebookCell[];
}

export function resolveNotebookCellIndex(cells: NotebookCell[], cellId: string, mode: NotebookEditMode): number {
  if (!cellId) {
    if (mode === "insert") return 0;
    throw new Error("Cell ID must be specified when not inserting a new cell.");
  }
  const directIndex = cells.findIndex((cell) => String(cell.id || "") === cellId);
  if (directIndex >= 0) return mode === "insert" ? directIndex + 1 : directIndex;
  const parsed = Number(cellId.replace(/^cell-/, ""));
  if (!Number.isInteger(parsed)) throw new Error(`Cell with ID "${cellId}" not found in notebook.`);
  if (parsed === cells.length && mode === "replace") return parsed;
  if (parsed < 0 || parsed >= cells.length) throw new Error(`Cell with index ${parsed} does not exist in notebook.`);
  return mode === "insert" ? parsed + 1 : parsed;
}

export function applyNotebookCellEdit(
  notebook: NotebookDocument,
  cellIndex: number,
  requestedCellId: string,
  newSource: string,
  cellType: NotebookCellType | undefined,
  mode: NotebookEditMode
): string {
  const cells = notebookCells(notebook);
  if (mode === "delete") return String(cells.splice(cellIndex, 1)[0]?.id || requestedCellId || `cell-${cellIndex}`);
  if (mode === "insert" || cellIndex === cells.length) {
    const newCellId = newCellIdFor(notebook);
    cells.splice(cellIndex, 0, newNotebookCell(cellType || "code", newSource, newCellId));
    return newCellId || `cell-${cellIndex}`;
  }
  const target = cells[cellIndex];
  target.source = newSource;
  if (cellType) target.cell_type = cellType;
  if (target.cell_type === "code") {
    target.execution_count = null;
    target.outputs = [];
  } else {
    delete target.execution_count;
    delete target.outputs;
  }
  return String(target.id || requestedCellId || `cell-${cellIndex}`);
}

export function notebookCellSource(cell: NotebookCell): string {
  return Array.isArray(cell.source) ? cell.source.map(String).join("") : String(cell.source || "");
}

export function normalizeNotebookEditMode(value: string): NotebookEditMode {
  if (["replace", "insert", "delete"].includes(value)) return value as NotebookEditMode;
  throw new Error("Edit mode must be replace, insert, or delete.");
}

export function normalizeNotebookCellType(value: string): NotebookCellType {
  if (["code", "markdown"].includes(value)) return value as NotebookCellType;
  throw new Error("Cell type must be code or markdown.");
}

export function notebookResultCellType(cells: NotebookCell[], index: number, mode: NotebookEditMode): string {
  if (mode === "delete") return "code";
  return String(cells[index]?.cell_type || "code");
}

export function notebookLanguage(notebook: NotebookDocument): string {
  const metadata = notebook.metadata && typeof notebook.metadata === "object" ? notebook.metadata as Record<string, unknown> : {};
  const languageInfo = metadata.language_info && typeof metadata.language_info === "object" ? metadata.language_info as Record<string, unknown> : {};
  return String(languageInfo.name || "python");
}

function newNotebookCell(cellType: NotebookCellType, source: string, cellId: string): NotebookCell {
  if (cellType === "markdown") return { cell_type: "markdown", id: cellId, source, metadata: {} };
  return { cell_type: "code", id: cellId, source, metadata: {}, execution_count: null, outputs: [] };
}

function newCellIdFor(notebook: NotebookDocument): string {
  const nbformat = Number(notebook.nbformat || 0);
  const minor = Number(notebook.nbformat_minor || 0);
  return nbformat > 4 || (nbformat === 4 && minor >= 5) ? crypto.randomUUID().replaceAll("-", "").slice(0, 12) : "";
}
