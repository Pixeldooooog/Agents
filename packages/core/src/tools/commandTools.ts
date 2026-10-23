import { mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { Buffer } from "node:buffer";
import type { JsonObject } from "../types/jsonTypes.js";
import type { ToolDefinition, ToolExecutionContext } from "./toolContracts.js";
import {
  commandDirectoryPath,
  commandFileContent,
  commandFileExists,
  commandMarkdownPath,
  commandNameFromValue,
  parseCommandFrontmatter,
  relativeCommandPath
} from "../commands/commandFiles.js";
import { commandMatchesQuery, discoverCommands, findCommand, publicCommand } from "../commands/commandDiscovery.js";
import { readLimitedFile, renderTemplate } from "./promptTools.js";
import {
  commandDeleteSchema,
  commandDiscoverSchema,
  commandReadSchema,
  commandRenderSchema,
  commandSaveSchema
} from "./commandToolSchemas.js";

export const commandToolDefinitions: ToolDefinition[] = [
  {
    name: "command.discover",
    description: "Discover prompt-backed slash commands in the workspace.",
    risk: "low",
    parameters: commandDiscoverSchema,
    handler: commandDiscover
  },
  {
    name: "command.render",
    description: "Render a prompt-backed slash command.",
    risk: "low",
    parameters: commandRenderSchema,
    handler: commandRender
  },
  {
    name: "command.read",
    description: "Read a prompt-backed slash command file.",
    risk: "low",
    parameters: commandReadSchema,
    handler: commandRead
  },
  {
    name: "command.save",
    description: "Save a prompt-backed slash command.",
    risk: "medium",
    parameters: commandSaveSchema,
    handler: commandSave
  },
  {
    name: "command.delete",
    description: "Delete a prompt-backed slash command.",
    risk: "medium",
    parameters: commandDeleteSchema,
    handler: commandDelete
  }
];

async function commandDiscover(context: ToolExecutionContext, args: JsonObject): Promise<Record<string, unknown>> {
  let commands = await discoverCommands(context.repoRoot);
  const query = String(args.query || "").trim().toLowerCase();
  if (query) commands = commands.filter((command) => commandMatchesQuery(command, query));
  const limit = boundedLimit(args.max_results, 50);
  return { commands: commands.slice(0, limit), count: Math.min(commands.length, limit), total: commands.length };
}

async function commandRender(context: ToolExecutionContext, args: JsonObject): Promise<Record<string, unknown>> {
  const command = await findCommand(context.repoRoot, args.name);
  const body = await readFile(command.absolutePath, "utf8");
  const { content } = parseCommandFrontmatter(body);
  return { command: publicCommand(command), arguments: String(args.arguments || ""), prompt: renderTemplate(content.trim(), {}, String(args.arguments || "")) };
}

async function commandRead(context: ToolExecutionContext, args: JsonObject): Promise<Record<string, unknown>> {
  const command = await findCommand(context.repoRoot, args.name);
  const result = await readLimitedFile(command.absolutePath, boundedLimit(args.max_bytes, 20000, 200000));
  const parsed = parseCommandFrontmatter(result.content);
  return { command: publicCommand(command), metadata: parsed.metadata, content: parsed.content, path: command.path, bytes: result.bytes, truncated: result.truncated };
}

async function commandSave(context: ToolExecutionContext, args: JsonObject): Promise<Record<string, unknown>> {
  const commandName = commandNameFromValue(args.name);
  const filePath = commandMarkdownPath(context.repoRoot, commandName);
  if (!args.overwrite && await commandFileExists(filePath)) throw new Error(`command already exists: ${commandName}`);
  const content = commandFileContent(commandName, args);
  await mkdir(commandDirectoryPath(filePath), { recursive: true });
  await writeFile(filePath, content);
  return { name: commandName, path: relativeCommandPath(context.repoRoot, filePath), bytes: Buffer.byteLength(content) };
}

async function commandDelete(context: ToolExecutionContext, args: JsonObject): Promise<Record<string, unknown>> {
  const commandName = commandNameFromValue(args.name);
  let filePath = commandMarkdownPath(context.repoRoot, commandName);
  try {
    filePath = (await findCommand(context.repoRoot, commandName)).absolutePath;
  } catch {
    // Deleting a missing command should still be idempotent.
  }
  await rm(filePath, { force: true });
  return { name: commandName, path: relativeCommandPath(context.repoRoot, filePath), deleted: true, result: { deleted: true } };
}

function boundedLimit(value: unknown, fallback: number, maximum = 100): number {
  const limit = Number(value || fallback);
  if (!Number.isFinite(limit)) return fallback;
  return Math.max(1, Math.min(maximum, limit));
}
