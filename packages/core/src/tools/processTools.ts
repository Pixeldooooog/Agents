import { spawn } from "node:child_process";
import type { JsonObject } from "../types/jsonTypes.js";
import type { ToolDefinition, ToolExecutionContext } from "./toolContracts.js";
import { numberArg, stringArg } from "./toolInputs.js";
import {
  shellBackgrounds,
  shellKill,
  shellOutput,
  startBackgroundCommand
} from "./shellBackgroundTools.js";

export const processToolDefinitions: ToolDefinition[] = [
  {
    name: "shell.run",
    description: "Run a shell command in the workspace.",
    risk: "high",
    handler: runShell
  },
  {
    name: "shell.output",
    description: "Read output from a background shell command.",
    risk: "low",
    handler: shellOutput
  },
  {
    name: "shell.backgrounds",
    description: "List background shell commands.",
    risk: "low",
    handler: shellBackgrounds
  },
  {
    name: "shell.kill",
    description: "Stop a background shell command.",
    risk: "medium",
    handler: shellKill
  },
  {
    name: "test.discover",
    description: "Suggest likely project test commands.",
    risk: "low",
    handler: discoverTests
  },
  {
    name: "test.run",
    description: "Run a test command in the workspace.",
    risk: "high",
    handler: runShell
  },
  {
    name: "sleep.wait",
    description: "Wait for a bounded duration.",
    risk: "low",
    parameters: {
      type: "object",
      properties: {
        duration_seconds: { type: "number", minimum: 0, maximum: 600 },
        seconds: { type: "number", minimum: 0, maximum: 600 },
        reason: { type: "string" }
      }
    },
    handler: sleepWait
  }
];

async function runShell(context: ToolExecutionContext, args: JsonObject) {
  const command = stringArg(args.command);
  if (!command) throw new Error("command is required");
  if (args.dangerouslyDisableSandbox) throw new Error("dangerouslyDisableSandbox is not supported by this runtime");
  const timeoutMs = shellTimeoutMs(args);
  if (args.run_in_background) {
    return startBackgroundCommand(command, context.repoRoot, timeoutMs, stringArg(args.description, command));
  }
  const result = await executeCommand(command, context.repoRoot, timeoutMs);
  return { command, timeout_ms: timeoutMs, background: false, ...result };
}

async function discoverTests() {
  return {
    commands: [
      "bun test",
      "bun run typecheck",
      "bun run --cwd apps/terminal app-flow-smoke"
    ]
  };
}

async function sleepWait(context: ToolExecutionContext, args: JsonObject) {
  const requestedSeconds = Math.max(0, Math.min(600, numberArg(args.duration_seconds ?? args.seconds, 1)));
  const startedAt = performance.now();
  const wokeForNotification = requestedSeconds > 0
    ? await waitForSleepOrWake(context, requestedSeconds * 1000)
    : false;
  return {
    requested_seconds: requestedSeconds,
    slept_seconds: Math.max(0, (performance.now() - startedAt) / 1000),
    reason: stringArg(args.reason),
    woke_for_notification: wokeForNotification
  };
}

async function waitForSleepOrWake(context: ToolExecutionContext, milliseconds: number): Promise<boolean> {
  if (context.sleepWake?.isWakeRequested()) return true;
  if (context.sleepWake) return context.sleepWake.wait(milliseconds);
  await new Promise((resolve) => setTimeout(resolve, milliseconds));
  return false;
}

function executeCommand(
  command: string,
  cwd: string,
  timeoutMs: number
): Promise<{ exit_code: number | null; stdout: string; stderr: string }> {
  return new Promise((resolve, reject) => {
    const child = spawn(command, { cwd, shell: true });
    const timer = setTimeout(() => {
      child.kill("SIGTERM");
      reject(new Error(`command timed out after ${timeoutMs}ms`));
    }, timeoutMs);
    const stdout: Buffer[] = [];
    const stderr: Buffer[] = [];
    child.stdout.on("data", (chunk) => stdout.push(Buffer.from(chunk)));
    child.stderr.on("data", (chunk) => stderr.push(Buffer.from(chunk)));
    child.on("error", (error) => {
      clearTimeout(timer);
      reject(error);
    });
    child.on("close", (code) => {
      clearTimeout(timer);
      resolve({
        exit_code: code,
        stdout: Buffer.concat(stdout).toString("utf8"),
        stderr: Buffer.concat(stderr).toString("utf8")
      });
    });
  });
}

function shellTimeoutMs(args: JsonObject): number {
  return Math.max(1, numberArg(args.timeout_ms, 30000));
}
