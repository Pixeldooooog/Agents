import { existsSync, readdirSync } from "node:fs";
import { stat } from "node:fs/promises";
import path from "node:path";
import { resolveWorkspacePath } from "../tools/toolInputs.js";
import type { ToolExecutionContext } from "../tools/toolContracts.js";
import type { ExtensionKind } from "./extensionManifestTypes.js";

export function skillSearchRoots(context: ToolExecutionContext): string[] {
  return [
    resolveWorkspacePath(context.repoRoot, ".kevin/skills"),
    resolveWorkspacePath(context.repoRoot, ".claude/skills"),
    resolveWorkspacePath(context.repoRoot, "skills")
  ];
}

export function pluginSearchRoots(context: ToolExecutionContext): string[] {
  return [
    resolveWorkspacePath(context.repoRoot, ".kevin/plugins"),
    resolveWorkspacePath(context.repoRoot, "plugins")
  ];
}

export function installRoot(context: ToolExecutionContext, kind: ExtensionKind): string {
  return resolveWorkspacePath(context.repoRoot, kind === "skill" ? ".kevin/skills" : ".kevin/plugins");
}

export function resolveSourcePath(context: ToolExecutionContext, source: string): string {
  const text = String(source || "").trim();
  if (!text) throw new Error("source is required");
  return path.isAbsolute(text) ? path.resolve(text) : resolveWorkspacePath(context.repoRoot, text);
}

export function manifestRoot(kind: ExtensionKind, manifestPath: string): string {
  if (kind === "plugin" && path.basename(path.dirname(manifestPath)) === ".codex-plugin") {
    return path.dirname(path.dirname(manifestPath));
  }
  if (kind === "skill") return path.dirname(manifestPath);
  return path.dirname(manifestPath);
}

export function skillManifestPath(root: string): string {
  try {
    const entries = new Set(readdirSync(root));
    const candidate = ["SKILL.md", "skill.md"].find((name) => entries.has(name));
    return candidate ? path.join(root, candidate) : "";
  } catch {
    return "";
  }
}

export function pluginManifestPath(root: string): string {
  const candidates = [path.join(root, ".codex-plugin", "plugin.json"), path.join(root, "plugin.json")];
  return candidates.find((candidate) => existsSync(candidate)) || "";
}

export function isSkillMarkdownManifest(manifestPath: string): boolean {
  return path.basename(manifestPath).toLowerCase() === "skill.md";
}

export async function sourceManifestPath(
  kind: ExtensionKind,
  sourcePath: string,
  isDirectory: boolean
): Promise<string> {
  if (!isDirectory) {
    if (kind === "skill" && !isSkillMarkdownManifest(sourcePath)) throw new Error(`skill manifest must be SKILL.md: ${sourcePath}`);
    return sourcePath;
  }
  if (kind === "skill") {
    const manifestPath = skillManifestPath(sourcePath);
    if (!manifestPath) throw new Error(`skill manifest not found in: ${sourcePath}`);
    return manifestPath;
  }
  const manifestPath = pluginManifestPath(sourcePath);
  if (!manifestPath) throw new Error(`plugin manifest not found in: ${sourcePath}`);
  return manifestPath;
}

export async function fileExists(filePath: string): Promise<boolean> {
  try {
    await stat(filePath);
    return true;
  } catch {
    return false;
  }
}
