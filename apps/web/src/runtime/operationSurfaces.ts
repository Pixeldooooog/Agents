import type { OperationSceneKind } from "../types";

export type OperationSurfaceKind = "finder" | "editor" | "browser" | "terminal" | "reader" | "summary";

export function surfaceForScene(scene: OperationSceneKind): OperationSurfaceKind {
  if (scene === "edit") return "editor";
  if (scene === "web" || scene === "browser") return "browser";
  if (scene === "terminal" || scene === "git") return "terminal";
  if (scene === "document") return "reader";
  if (scene === "summary") return "summary";
  return "finder";
}

export function surfaceLabel(surface: OperationSurfaceKind) {
  const labels: Record<OperationSurfaceKind, string> = {
    finder: "Finder",
    editor: "Editor",
    browser: "Browser",
    terminal: "Terminal",
    reader: "Reader",
    summary: "Summary",
  };
  return labels[surface];
}
