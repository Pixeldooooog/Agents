import { mkdir, readdir, readFile, rm, stat, writeFile } from "node:fs/promises";
import path from "node:path";
import type { JsonObject } from "../types/jsonTypes.js";
import { defineTool, type RegisteredTool, type ToolContext } from "./toolContracts.js";
import { relativeWorkspacePath, resolveWorkspacePath } from "./toolInputs.js";
import { safeName } from "../workspace/workspaceNames.js";

export { safeName } from "../workspace/workspaceNames.js";

export const promptToolDefinitions: RegisteredTool[] = [
  defineTool({
    name: "prompt.templates",
    description: "List saved prompt templates.",
    risk: "low",
    parameters: { type: "object", properties: { query: { type: "string" }, max_results: { type: "integer", minimum: 1, maximum: 100 } } },
    requires: [],
    handler: promptTemplates
  }),
  defineTool({
    name: "prompt.read",
    description: "Read a saved prompt template.",
    risk: "low",
    parameters: { type: "object", properties: { name: { type: "string" }, max_bytes: { type: "integer", minimum: 1, maximum: 200000 } }, required: ["name"] },
    requires: [],
    handler: promptRead
  }),
  defineTool({
    name: "prompt.render",
    description: "Render a saved prompt template with named arguments.",
    risk: "low",
    parameters: { type: "object", properties: { name: { type: "string" }, arguments: { type: "object" }, raw_arguments: { type: "string" } }, required: ["name"] },
    requires: [],
    handler: promptRender
  }),
  defineTool({
    name: "prompt.save",
    description: "Save a prompt template.",
    risk: "medium",
    parameters: { type: "object", properties: { name: { type: "string" }, content: { type: "string" }, overwrite: { type: "boolean" } }, required: ["name", "content"] },
    requires: [],
    handler: promptSave
  }),
  defineTool({
    name: "prompt.delete",
    description: "Delete a saved prompt template.",
    risk: "medium",
    parameters: { type: "object", properties: { name: { type: "string" } }, required: ["name"] },
    requires: [],
    handler: promptDelete
  })
];

async function promptTemplates(context: ToolContext, args: JsonObject): Promise<Record<string, unknown>> {
  let templates = await listTemplates(context);
  const query = String(args.query || "").trim().toLowerCase();
  if (query) templates = templates.filter((template) => `${template.name} ${template.preview}`.toLowerCase().includes(query));
  const limit = boundedLimit(args.max_results, 50);
  return { templates: templates.slice(0, limit), count: Math.min(templates.length, limit), total: templates.length };
}

async function promptRead(context: ToolContext, args: JsonObject): Promise<Record<string, unknown>> {
  const name = safeName(args.name, "prompt template");
  const maxBytes = boundedLimit(args.max_bytes, 20000, 200000);
  const filePath = templatePath(context, name);
  const content = await readLimitedFile(filePath, maxBytes);
  return {
    name,
    path: relativeWorkspacePath(context.repoRoot, filePath),
    ...content
  };
}

async function promptRender(context: ToolContext, args: JsonObject): Promise<Record<string, unknown>> {
  const read = await promptRead(context, { name: args.name, max_bytes: 200000 });
  return {
    name: read.name,
    path: read.path,
    arguments: stringRecord(args.arguments),
    raw_arguments: String(args.raw_arguments || ""),
    prompt: renderTemplate(String(read.content || ""), args.arguments, String(args.raw_arguments || ""))
  };
}

async function promptSave(context: ToolContext, args: JsonObject): Promise<Record<string, unknown>> {
  const name = safeName(args.name, "prompt template");
  const filePath = templatePath(context, name);
  if (!args.overwrite && await fileExists(filePath)) throw new Error(`prompt template already exists: ${name}`);
  const content = String(args.content || "");
  await mkdir(path.dirname(filePath), { recursive: true });
  await writeFile(filePath, content);
  return { name, path: relativeWorkspacePath(context.repoRoot, filePath), bytes: Buffer.byteLength(content) };
}

async function promptDelete(context: ToolContext, args: JsonObject): Promise<Record<string, unknown>> {
  const name = safeName(args.name, "prompt template");
  const filePath = templatePath(context, name);
  await rm(filePath, { force: true });
  return { name, path: relativeWorkspacePath(context.repoRoot, filePath), deleted: true, result: { deleted: true } };
}

async function listTemplates(context: ToolContext): Promise<Record<string, string>[]> {
  const directoryPath = resolveWorkspacePath(context.repoRoot, ".kevin/prompts");
  try {
    const entries = await readdir(directoryPath, { withFileTypes: true });
    const templates = await Promise.all(entries.filter((entry) => entry.isFile() && entry.name.endsWith(".md")).map(async (entry) => {
      const filePath = path.join(directoryPath, entry.name);
      const preview = (await readLimitedFile(filePath, 240)).content.split(/\s+/).join(" ").slice(0, 160);
      return { name: entry.name.slice(0, -3), path: relativeWorkspacePath(context.repoRoot, filePath), preview };
    }));
    return templates.sort((a, b) => a.name.localeCompare(b.name));
  } catch {
    return [];
  }
}

function templatePath(context: ToolContext, name: string): string {
  return resolveWorkspacePath(context.repoRoot, `.kevin/prompts/${name}.md`);
}

export function renderTemplate(content: string, args: unknown, rawArguments: string): string {
  let rendered = String(content || "");
  const replacements = { arguments: rawArguments, ...stringRecord(args) };
  for (const [key, value] of Object.entries(replacements)) {
    rendered = rendered.replaceAll(`{{${key}}}`, value).replaceAll(`{${key}}`, value);
  }
  return rendered;
}

export async function readLimitedFile(filePath: string, maxBytes: number): Promise<{ content: string; bytes: number; truncated: boolean }> {
  const content = await readFile(filePath, "utf8");
  const bytes = Buffer.byteLength(content);
  return { content: content.slice(0, maxBytes), bytes, truncated: bytes > maxBytes };
}

async function fileExists(filePath: string): Promise<boolean> {
  try {
    return (await stat(filePath)).isFile();
  } catch {
    return false;
  }
}

function stringRecord(value: unknown): Record<string, string> {
  if (!value || typeof value !== "object") return {};
  return Object.fromEntries(Object.entries(value).map(([key, entryValue]) => [String(key), String(entryValue)]));
}

function boundedLimit(value: unknown, fallback: number, maximum = 100): number {
  const limit = Number(value || fallback);
  if (!Number.isFinite(limit)) return fallback;
  return Math.max(1, Math.min(maximum, limit));
}
