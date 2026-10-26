import { confinedExtensionPath, validateExtensionPackage } from "./extensionFilesystem.js";
import { isPortableManifestName } from "./extensionManifestRecords.js";
import { cp, mkdir, readdir, rm, stat } from "node:fs/promises";
import path from "node:path";
import { relativeWorkspacePath } from "../tools/toolInputs.js";
import type { ToolContext } from "../tools/toolContracts.js";
import { renderTemplate } from "../tools/promptTools.js";
import { discoverManifests, parseManifest } from "./extensionManifestDiscovery.js";
import {
  fileExists,
  installRoot,
  isSkillMarkdownManifest,
  resolveSourcePath,
  sourceManifestPath
} from "./extensionManifestPaths.js";
import type { ExtensionKind, ExtensionManifest } from "./extensionManifestTypes.js";

export type { ExtensionKind, ExtensionManifest } from "./extensionManifestTypes.js";

export async function discoverSkills(context: ToolContext): Promise<ExtensionManifest[]> {
  return discoverManifests(context, "skill");
}

export async function discoverPlugins(context: ToolContext): Promise<ExtensionManifest[]> {
  return discoverManifests(context, "plugin");
}

export async function installSkill(context: ToolContext, source: string): Promise<ExtensionManifest> {
  return installExtension(context, "skill", source);
}

export async function installPlugin(context: ToolContext, source: string): Promise<ExtensionManifest> {
  return installExtension(context, "plugin", source);
}

export async function uninstallSkill(context: ToolContext, name: string): Promise<string> {
  return uninstallExtension(context, "skill", name);
}

export async function uninstallPlugin(context: ToolContext, name: string): Promise<string> {
  return uninstallExtension(context, "plugin", name);
}

export async function loadSkill(context: ToolContext, name: string): Promise<ExtensionManifest> {
  return loadExtension(context, "skill", name);
}

export async function loadPlugin(context: ToolContext, name: string): Promise<ExtensionManifest> {
  return loadExtension(context, "plugin", name);
}

export async function renderExtensionPrompt(manifest: ExtensionManifest, args: unknown, rawArguments: string): Promise<string> {
  const fragments = manifest.instructions;
  const prompt = fragments.map((fragment) => fragment.trim()).filter(Boolean).join("\n\n") || manifest.description;
  return renderTemplate(prompt.replaceAll("$ARGUMENTS", "{{arguments}}"), args, rawArguments);
}

export function publicExtensionPayload(context: ToolContext, manifest: ExtensionManifest, includePrompt = false) {
  const payload: Record<string, unknown> = {
    name: manifest.name,
    format: manifest.format,
    version: manifest.version,
    description: manifest.description,
    when_to_use: manifest.when_to_use,
    tools: manifest.tools,
    allowed_tools: manifest.allowed_tools,
    disallowed_tools: manifest.disallowed_tools,
    prompt_fragments: manifest.prompt_fragments,
    paths: manifest.paths,
    context: manifest.context,
    model: manifest.model,
    effort: manifest.effort,
    agent: manifest.agent,
    user_invocable: manifest.user_invocable,
    disable_model_invocation: manifest.disable_model_invocation,
    metadata: manifest.metadata,
    path: relativeWorkspacePath(context.repoRoot, manifest.rootPath),
    manifest_path: relativeWorkspacePath(context.repoRoot, manifest.manifestPath),
    invalid: Boolean(manifest.invalid)
  };
  if (manifest.error) payload.error = manifest.error;
  if (includePrompt) payload.prompts = manifest.prompt_fragments;
  return payload;
}

async function installExtension(context: ToolContext, kind: ExtensionKind, source: string): Promise<ExtensionManifest> {
  const sourcePath = resolveSourcePath(context, source);
  const sourceInfo = await stat(sourcePath);
  const manifestPath = await sourceManifestPath(kind, sourcePath, sourceInfo.isDirectory());
  await confinedExtensionPath(sourceInfo.isDirectory() ? sourcePath : path.dirname(sourcePath), manifestPath);
  await validateExtensionPackage(sourcePath);
  const raw = await parseManifest(manifestPath);
  const nameFallback = kind === "skill" && isSkillMarkdownManifest(manifestPath)
    ? path.basename(path.dirname(manifestPath))
    : path.basename(sourcePath, ".json");
  const name = requireExtensionName(String(raw.name || nameFallback));
  const isPackagedSkillFile = kind === "skill" && !sourceInfo.isDirectory() && isSkillMarkdownManifest(manifestPath);
  const targetRoot = await confinedExtensionPath(context.repoRoot, installRoot(context, kind));
  const flatTarget = kind === "plugin" ? path.join(targetRoot, `${name}.json`) : "";
  const packageTarget = path.join(targetRoot, name);
  if ((flatTarget && await fileExists(flatTarget)) || await fileExists(packageTarget)) {
    throw new Error(`${kind} already installed: ${name}`);
  }
  const relativeTarget = path.relative(path.resolve(sourcePath), packageTarget);
  if (sourceInfo.isDirectory() && relativeTarget !== ".." && !relativeTarget.startsWith(`..${path.sep}`) && !path.isAbsolute(relativeTarget)) throw new Error("cannot install a package inside its source");
  await mkdir(targetRoot, { recursive: true });
  if (sourceInfo.isDirectory() || isPackagedSkillFile) {
    await mkdir(packageTarget);
    try {
      if (sourceInfo.isDirectory()) {
        // mkdir reserves this install; copy children without replacing the reserved directory.
        for (const entry of await readdir(sourcePath)) {
          await cp(path.join(sourcePath, entry), path.join(packageTarget, entry), { recursive: true, force: false, errorOnExist: true });
        }
      } else await cp(sourcePath, path.join(packageTarget, "SKILL.md"), { force: false, errorOnExist: true });
    } catch (error) {
      await rm(packageTarget, { recursive: true, force: true });
      throw error;
    }
  } else if (flatTarget) await cp(sourcePath, flatTarget, { force: false, errorOnExist: true });
  else throw new Error(`${kind} manifest must be SKILL.md: ${sourcePath}`);
  return loadExtension(context, kind, name);
}

async function uninstallExtension(context: ToolContext, kind: ExtensionKind, name: string): Promise<string> {
  const extensionName = requireExtensionName(name);
  const root = await confinedExtensionPath(context.repoRoot, installRoot(context, kind));
  const flat = kind === "plugin" ? path.join(root, `${extensionName}.json`) : "";
  const packaged = path.join(root, extensionName);
  if (flat && await fileExists(flat)) await rm(flat, { force: true });
  else if (await fileExists(packaged)) await rm(packaged, { recursive: true, force: true });
  else throw new Error(`${kind} not installed: ${extensionName}`);
  return extensionName;
}

async function loadExtension(context: ToolContext, kind: ExtensionKind, name: string): Promise<ExtensionManifest> {
  const wanted = requireExtensionName(String(name || "").replace(/^\//, ""));
  const manifest = (await discoverManifests(context, kind)).find((item) => {
    return item.name === wanted;
  });
  if (!manifest || manifest.invalid) throw new Error(`unknown ${kind}: ${wanted}`);
  return manifest;
}

function requireExtensionName(name: string): string {
  if (!isPortableManifestName(name)) throw new Error("invalid extension name");
  return name;
}
