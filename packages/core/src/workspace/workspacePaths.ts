import { stat } from "node:fs/promises";
import path from "node:path";

export function resolveWorkspacePath(repoRoot: string, requested = "."): string {
  const root = path.resolve(repoRoot);
  const resolved = path.resolve(root, requested || ".");
  if (resolved !== root && !resolved.startsWith(`${root}${path.sep}`)) {
    throw new Error(`path escapes workspace: ${requested}`);
  }
  return resolved;
}

export function relativeWorkspacePath(repoRoot: string, absolutePath: string): string {
  return path.relative(path.resolve(repoRoot), absolutePath) || ".";
}

export async function assertFile(repoRoot: string, requested: string): Promise<string> {
  const resolved = resolveWorkspacePath(repoRoot, requested);
  const info = await stat(resolved);
  if (!info.isFile()) throw new Error(`not a file: ${requested}`);
  return resolved;
}

export async function assertDirectory(repoRoot: string, requested: string): Promise<string> {
  const resolved = resolveWorkspacePath(repoRoot, requested || ".");
  const info = await stat(resolved);
  if (!info.isDirectory()) throw new Error(`not a directory: ${requested || "."}`);
  return resolved;
}
