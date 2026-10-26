import { gitSchemas } from "./gitSchemas.js";
import type { JsonObject } from "../types/jsonTypes.js";
import { defineTool, type RegisteredTool, type ToolContext } from "./toolContracts.js";
import { stringArg } from "./toolInputs.js";
import { runShell } from "./processTools.js";

export const gitToolDefinitions: RegisteredTool[] = [
  gitTool("git.status", "git status --short", "Show Git working tree status."),
  gitTool("git.diff", "git diff --stat && git diff --", "Show Git diff."),
  gitTool("git.log", "git log --oneline -20", "Show recent Git history."),
  gitTool("git.show", "", "Show a Git revision."),
  gitTool("git.add", "", "Stage Git paths.", "high"),
  gitTool("git.commit", "", "Create a Git commit.", "high")
];

function gitTool(name: string, command: string, description: string, risk: "low" | "medium" | "high" = name === "git.add" || name === "git.commit" ? "high" : "low"): RegisteredTool {
  return defineTool({
    name,
    parameters: gitSchemas[name],
    description,
    risk,
    requires: [],
    uses: ["commandExecutor"],
    handler: async (context, args) => runGit(context, args, name, command)
  });
}

async function runGit(context: ToolContext<never, "commandExecutor">, args: JsonObject, name: string, defaultCommand: string) {
  const command = gitCommand(name, args, defaultCommand);
  return runShell(context, { command, timeout_ms: args.timeout_ms ?? 30000 });
}

function gitCommand(name: string, args: JsonObject, fallback: string): string {
  if (name === "git.show") return `git show --stat --patch --end-of-options ${shellQuote(stringArg(args.revision ?? args.ref, "HEAD"))}`;
  if (name === "git.add") {
    const paths = Array.isArray(args.paths) ? args.paths.map(String) : [stringArg(args.path, ".")];
    return `git add -- ${paths.map(shellQuote).join(" ")}`;
  }
  if (name === "git.commit") return `git commit -m ${shellQuote(stringArg(args.message))}`;
  return fallback;
}

function shellQuote(value: string): string {
  return `'${value.replace(/'/g, "'\\''")}'`;
}
