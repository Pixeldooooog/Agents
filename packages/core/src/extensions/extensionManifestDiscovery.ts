import { confinedExtensionPath, readExtensionManifest } from "./extensionFilesystem.js";
import { readdir } from "node:fs/promises";
import path from "node:path";
import type { ToolContext } from "../tools/toolContracts.js";
import type { ExtensionKind, ExtensionManifest } from "./extensionManifestTypes.js";
import { invalidExtensionManifest, normalizeExtensionManifest } from "./extensionManifestRecords.js";
import {
  isSkillMarkdownManifest,
  pluginManifestPath,
  pluginSearchRoots,
  skillManifestPath,
  skillSearchRoots,
  manifestRoot
} from "./extensionManifestPaths.js";
import { parseSkillMarkdownManifest } from "./extensionSkillMarkdown.js";

export async function discoverManifests(context: ToolContext, kind: ExtensionKind): Promise<ExtensionManifest[]> {
  const roots = kind === "skill" ? skillSearchRoots(context) : pluginSearchRoots(context);
  const manifests: ExtensionManifest[] = [];
  for (const root of roots) {
    try {
      await confinedExtensionPath(context.repoRoot, root);
      const entries = await readdir(root, { withFileTypes: true });
      for (const entry of entries) {
        if (entry.isDirectory()) {
          const manifestPath = kind === "skill"
            ? skillManifestPath(path.join(root, entry.name))
            : pluginManifestPath(path.join(root, entry.name));
          if (manifestPath) manifests.push(await readManifest(kind, manifestPath));
        }
      }
    } catch {
      continue;
    }
  }
  // Search-root order is authoritative; a broken higher-priority manifest cannot fall back silently.
  const selected = new Map<string, ExtensionManifest>();
  for (const manifest of manifests) if (!selected.has(manifest.name)) selected.set(manifest.name, manifest);
  return [...selected.values()].sort((left, right) => left.name.localeCompare(right.name));
}

export async function readManifest(kind: ExtensionKind, manifestPath: string): Promise<ExtensionManifest> {
  try {
    await confinedExtensionPath(manifestRoot(kind, manifestPath), manifestPath);
    const raw = await parseManifest(manifestPath);
    return normalizeExtensionManifest(kind, manifestPath, raw);
  } catch (error) {
    return invalidExtensionManifest(kind, manifestPath, error);
  }
}

export async function parseManifest(manifestPath: string): Promise<Record<string, unknown>> {
  const content = await readExtensionManifest(manifestPath);
  if (isSkillMarkdownManifest(manifestPath)) return parseSkillMarkdownManifest(content, manifestPath);
  return JSON.parse(content);
}
