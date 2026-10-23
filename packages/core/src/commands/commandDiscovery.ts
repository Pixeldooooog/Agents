import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import { resolveWorkspacePath } from "../workspace/workspacePaths.js";
import {
  commandNameFromValue,
  parseCommandFrontmatter,
  relativeCommandPath
} from "./commandFiles.js";
import type { CommandRecord, PublicCommandRecord } from "./commandRecords.js";

const commandDirectories = [".agents/commands", "commands"];

export async function discoverCommands(repoRoot: string): Promise<CommandRecord[]> {
  const commands: CommandRecord[] = [];
  for (const directory of commandDirectories) {
    const directoryPath = resolveWorkspacePath(repoRoot, directory);
    try {
      const entries = await readdir(directoryPath, { withFileTypes: true });
      for (const entry of entries.filter((item) => item.isFile() && item.name.endsWith(".md"))) {
        commands.push(await commandRecordFromFile(repoRoot, directoryPath, entry.name));
      }
    } catch {
      continue;
    }
  }
  return commands.sort((a, b) => a.name.localeCompare(b.name));
}

export async function findCommand(repoRoot: string, name: unknown): Promise<CommandRecord> {
  const commandName = commandNameFromValue(name);
  const command = (await discoverCommands(repoRoot)).find((item) => item.name === commandName || item.aliases.includes(commandName));
  if (!command) throw new Error(`command not found: ${commandName}`);
  return command;
}

export function publicCommand(command: CommandRecord): PublicCommandRecord {
  const { absolutePath: _absolutePath, ...publicPayload } = command;
  return publicPayload;
}

export function commandMatchesQuery(command: CommandRecord, query: string): boolean {
  return commandHaystack(command).includes(query.trim().toLowerCase());
}

async function commandRecordFromFile(repoRoot: string, directoryPath: string, fileName: string): Promise<CommandRecord> {
  const absolutePath = path.join(directoryPath, fileName);
  const raw = await readFile(absolutePath, "utf8");
  const { metadata, content } = parseCommandFrontmatter(raw);
  return {
    name: commandNameFromValue(metadata.name || fileName.slice(0, -3)),
    description: String(metadata.description || descriptionFromBody(content)),
    argumentHint: String(metadata.argument_hint || metadata.argumentHint || ""),
    aliases: csv(metadata.aliases).map(commandNameFromValue),
    source: "workspace",
    category: String(metadata.category || "custom"),
    path: relativeCommandPath(repoRoot, absolutePath),
    absolutePath
  };
}

function commandHaystack(command: CommandRecord): string {
  return [command.name, command.description, command.argumentHint, command.aliases.join(" "), command.category].join(" ").toLowerCase();
}

function descriptionFromBody(body: string): string {
  return body.split(/\r?\n/).map((line) => line.trim().replace(/^#+/, "").trim()).find(Boolean)?.slice(0, 160) || "";
}

function csv(value: unknown): string[] {
  return String(value || "").split(",").map((item) => item.trim()).filter(Boolean);
}
