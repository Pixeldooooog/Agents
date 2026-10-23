import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import type { JsonObject } from "../types/jsonTypes.js";
import type { ToolDefinition, ToolExecutionContext } from "./toolContracts.js";
import { numberArg, relativeWorkspacePath, resolveWorkspacePath, stringArg } from "./toolInputs.js";

export const searchToolDefinitions: ToolDefinition[] = [
  {
    name: "search.grep",
    description: "Search workspace text files with a regular expression.",
    risk: "low",
    handler: grepWorkspace
  },
  {
    name: "search.glob",
    description: "Find workspace files matching a glob pattern.",
    risk: "low",
    handler: globWorkspace
  }
];

async function grepWorkspace(context: ToolExecutionContext, args: JsonObject) {
  const pattern = stringArg(args.pattern);
  if (!pattern) throw new Error("pattern is required");
  const regex = new RegExp(pattern, stringArg(args.flags, stringArg(args.case_sensitive) === "false" ? "i" : ""));
  const root = resolveWorkspacePath(context.repoRoot, stringArg(args.path, "."));
  const headLimit = Math.max(1, numberArg(args.limit, 100));
  const files = await collectFiles(context.repoRoot, root);
  const matches: Array<{ path: string; line: number; match: string }> = [];
  for (const filePath of files) {
    if (matches.length >= headLimit) break;
    const content = await readTextIfPossible(filePath);
    if (content === undefined) continue;
    const lines = content.split(/\r?\n/);
    for (let index = 0; index < lines.length; index += 1) {
      if (regex.test(lines[index])) {
        matches.push({ path: relativeWorkspacePath(context.repoRoot, filePath), line: index + 1, match: lines[index] });
        if (matches.length >= headLimit) break;
      }
      regex.lastIndex = 0;
    }
  }
  return { pattern, matches, count: matches.length };
}

async function globWorkspace(context: ToolExecutionContext, args: JsonObject) {
  const pattern = stringArg(args.pattern, "**/*");
  const root = resolveWorkspacePath(context.repoRoot, stringArg(args.path, "."));
  const limit = Math.max(1, numberArg(args.limit, 200));
  const matcher = globToRegex(pattern);
  const files = await collectFiles(context.repoRoot, root);
  const matches = files
    .map((filePath) => relativeWorkspacePath(context.repoRoot, filePath))
    .filter((filePath) => matcher.test(filePath))
    .slice(0, limit);
  return { pattern, matches, count: matches.length };
}

async function collectFiles(repoRoot: string, root: string): Promise<string[]> {
  const entries = await readdir(root, { withFileTypes: true });
  const files: string[] = [];
  for (const entry of entries) {
    if (entry.name === ".git" || entry.name === "node_modules" || entry.name === ".agents") continue;
    const fullPath = path.join(root, entry.name);
    if (entry.isDirectory()) files.push(...await collectFiles(repoRoot, fullPath));
    else if (entry.isFile()) files.push(fullPath);
  }
  return files;
}

async function readTextIfPossible(filePath: string): Promise<string | undefined> {
  try {
    const content = await readFile(filePath, "utf8");
    return content.includes("\u0000") ? undefined : content;
  } catch {
    return undefined;
  }
}

function globToRegex(pattern: string): RegExp {
  const escaped = pattern
    .replace(/[.+^${}()|[\]\\]/g, "\\$&")
    .replace(/\*\*/g, "\u0000")
    .replace(/\*/g, "[^/]*")
    .replace(/\?/g, "[^/]")
    .replace(/\u0000/g, ".*");
  return new RegExp(`^${escaped}$`);
}
