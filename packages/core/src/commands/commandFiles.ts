import { stat } from "node:fs/promises";
import path from "node:path";
import type { JsonObject } from "../types/jsonTypes.js";
import { relativeWorkspacePath, resolveWorkspacePath } from "../workspace/workspacePaths.js";
import { safeName } from "../workspace/workspaceNames.js";
import type { CommandFrontmatter } from "./commandRecords.js";

export function commandNameFromValue(value: unknown): string {
  return `/${safeName(String(value || "").replace(/^\//, ""), "command")}`;
}

export function commandMarkdownPath(repoRoot: string, commandName: string): string {
  return resolveWorkspacePath(repoRoot, `.kevin/commands/${commandName.slice(1)}.md`);
}

export function relativeCommandPath(repoRoot: string, absolutePath: string): string {
  return relativeWorkspacePath(repoRoot, absolutePath);
}

export function parseCommandFrontmatter(raw: string): CommandFrontmatter {
  const text = String(raw || "");
  if (!text.startsWith("---\n")) return { metadata: {}, content: text };
  const end = text.indexOf("\n---", 4);
  if (end < 0) return { metadata: {}, content: text };
  const metadata: Record<string, string> = {};
  for (const line of text.slice(4, end).split(/\r?\n/)) {
    const index = line.indexOf(":");
    if (index > 0) metadata[line.slice(0, index).trim()] = line.slice(index + 1).trim().replace(/^["']|["']$/g, "");
  }
  return { metadata, content: text.slice(end + 4).replace(/^\r?\n/, "") };
}

export function commandFileContent(commandName: string, args: JsonObject): string {
  const metadata: Record<string, string> = {
    name: commandName.slice(1),
    description: String(args.description || ""),
    argument_hint: String(args.argument_hint || ""),
    aliases: commandAliasLine(args.aliases),
    category: String(args.category || "custom")
  };
  const lines = ["---", ...Object.entries(metadata).flatMap(([key, value]) => value ? [`${key}: ${value}`] : []), "---", String(args.content || "").trim(), ""];
  return lines.join("\n");
}

export async function commandFileExists(filePath: string): Promise<boolean> {
  try {
    return (await stat(filePath)).isFile();
  } catch {
    return false;
  }
}

export function commandDirectoryPath(filePath: string): string {
  return path.dirname(filePath);
}

function commandAliasLine(value: unknown): string {
  return Array.isArray(value) ? value.map((alias) => commandNameFromValue(alias).slice(1)).join(", ") : "";
}
