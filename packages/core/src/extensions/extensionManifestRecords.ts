import path from "node:path";
import type { ExtensionKind, ExtensionManifest, ExtensionManifestFormat } from "./extensionManifestTypes.js";
import { isSkillMarkdownManifest, manifestRoot } from "./extensionManifestPaths.js";

export function normalizeExtensionManifest(kind: ExtensionKind, manifestPath: string, raw: Record<string, unknown>): ExtensionManifest {
  const rootPath = manifestRoot(kind, manifestPath);
  const metadata = objectRecord(raw.metadata);
  return {
    kind,
    format: manifestFormat(kind, manifestPath),
    name: String(raw.name || fallbackManifestName(kind, manifestPath, rootPath)),
    version: String(raw.version || "0.1.0"),
    description: String(raw.description || ""),
    when_to_use: String(raw.when_to_use || raw.whenToUse || raw.description || ""),
    tools: kind === "skill" ? [] : stringList(raw.tools),
    allowed_tools: stringList(raw.allowed_tools || raw.allowedTools),
    disallowed_tools: stringList(raw.disallowed_tools || raw.disallowedTools),
    prompt_fragments: stringList(raw.prompt_fragments),
    instructions: stringList(raw.instructions),
    paths: stringList(raw.paths),
    context: String(raw.context || ""),
    model: String(raw.model || metadata.model || ""),
    effort: String(raw.effort || metadata.effort || ""),
    agent: String(raw.agent || metadata.agent || ""),
    user_invocable: booleanValue(raw.user_invocable ?? raw.userInvocable, true),
    disable_model_invocation: booleanValue(raw.disable_model_invocation ?? raw.disableModelInvocation, false),
    metadata,
    rootPath,
    manifestPath
  };
}

export function invalidExtensionManifest(kind: ExtensionKind, manifestPath: string, error: unknown): ExtensionManifest {
  const rootPath = manifestRoot(kind, manifestPath);
  return {
    kind,
    format: kind === "plugin" ? "plugin-json" : "skill-md",
    name: fallbackManifestName(kind, manifestPath, rootPath),
    version: "",
    description: "",
    when_to_use: "",
    tools: [],
    allowed_tools: [],
    disallowed_tools: [],
    prompt_fragments: [],
    instructions: [],
    paths: [],
    context: "",
    model: "",
    effort: "",
    agent: "",
    user_invocable: true,
    disable_model_invocation: false,
    metadata: {},
    rootPath,
    manifestPath,
    invalid: true,
    error: error instanceof Error ? error.message : String(error)
  };
}

export function stringList(value: unknown): string[] {
  if (typeof value === "string" && value.trim()) return value.includes(",") ? splitList(value) : [value.trim()];
  return Array.isArray(value) ? value.map(String).filter(Boolean) : [];
}

export function objectRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

export function booleanValue(value: unknown, fallback: boolean): boolean {
  if (typeof value === "boolean") return value;
  if (typeof value === "string" && value.trim()) return value.trim().toLowerCase() === "true";
  return fallback;
}

export function isPortableManifestName(value: string): boolean {
  return /^[A-Za-z0-9_.-]+$/.test(value) && !value.includes("/") && !value.includes("\\") && value !== "." && value !== "..";
}

export function normalizedManifestName(value: string): string {
  return [...String(value || "").trim()].filter((char) => /[a-zA-Z0-9_.-]/.test(char)).join("").replace(/^[.-]+|[.-]+$/g, "");
}

function manifestFormat(kind: ExtensionKind, manifestPath: string): ExtensionManifestFormat {
  if (kind === "plugin") return "plugin-json";
  if (!isSkillMarkdownManifest(manifestPath)) throw new Error(`skill manifest must be SKILL.md: ${manifestPath}`);
  return "skill-md";
}

function fallbackManifestName(kind: ExtensionKind, manifestPath: string, rootPath: string): string {
  if (kind === "skill" && isSkillMarkdownManifest(manifestPath)) return normalizedManifestName(path.basename(rootPath)) || "skill";
  return normalizedManifestName(path.basename(rootPath)) || path.basename(manifestPath, path.extname(manifestPath));
}

function splitList(value: string): string[] {
  return value.split(",").map((item) => stripQuotes(item.trim())).filter(Boolean);
}

function stripQuotes(value: string): string {
  if ((value.startsWith("\"") && value.endsWith("\"")) || (value.startsWith("'") && value.endsWith("'"))) return value.slice(1, -1);
  return value;
}
